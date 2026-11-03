"""Multimodal anchors: stable pointers to a precise place inside a file revision.

Pure functions over file bytes. ``capture`` validates a selector against one
revision and records what was there; ``resolve`` re-finds that place in a later
revision and reports ``intact``, ``moved``, ``changed`` or ``lost``. Nothing here
touches the database or the filesystem; the store reads the bytes and persists
the outcome. Only the standard library is required. ``pypdf`` is used, when
installed, to read text positions in PDFs.
"""
from __future__ import annotations

import ast
import bisect
import csv
import difflib
import hashlib
import io
import json
import posixpath
import re
import struct
import wave
import xml.etree.ElementTree as ET
import zipfile

KINDS = ("text", "cell", "pdf", "image", "time", "mesh", "code")
STATUSES = ("intact", "moved", "changed", "lost")
MAX_ANCHOR_BYTES = 64 * 1024 * 1024
NEEDS_BYTES = {"text", "cell", "pdf", "mesh", "code"}
MAX_QUOTE = 4000
FUZZY_THRESHOLD = 0.6


class AnchorError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _int(value, name, low=0, high=10**9):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise AnchorError(f"{name} must be an integer between {low} and {high}")
    return value


def _num(value, name, low=0.0, high=1e9):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise AnchorError(f"{name} must be a number between {low} and {high}")
    return float(value)


def _suffix(name):
    return posixpath.splitext(str(name).replace("\\", "/").lower())[1]


def _norm_ws(value):
    return " ".join(value.split())


def _hash(value):
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:24]


# ----------------------------------------------------------------- text ----

def _decode(data):
    return data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _line_starts(text):
    starts = [0]
    starts.extend(i + 1 for i, c in enumerate(text) if c == "\n")
    return starts


def _line_of(starts, offset):
    return bisect.bisect_right(starts, offset) - 1 + 1


def _find_all(text, quote):
    hits, at = [], text.find(quote)
    while at != -1 and len(hits) < 5000:
        hits.append(at)
        at = text.find(quote, at + 1)
    return hits


def _common_suffix(a, b):
    n = 0
    while n < len(a) and n < len(b) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _common_prefix(a, b):
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    return n


def _best_hit(text, hits, quote, prefix, suffix):
    def score(h):
        return _common_suffix(text[max(0, h - len(prefix)):h], prefix) + _common_prefix(text[h + len(quote):h + len(quote) + len(suffix)], suffix)
    return max(hits, key=lambda h: (score(h), -h))


def _text_location(text, starts, start, end):
    quote = text[start:end]
    return {"start": start, "end": end, "line_start": _line_of(starts, start), "line_end": _line_of(starts, max(start, end - 1)), "quote": quote}


def _text_capture(sel, data):
    text = _decode(data)
    starts = _line_starts(text)
    if isinstance(sel.get("quote"), str) and sel["quote"]:
        quote = sel["quote"].replace("\r\n", "\n")
        hits = _find_all(text, quote)
        if not hits:
            raise AnchorError("quote not found in the current revision")
        start = _best_hit(text, hits, quote, str(sel.get("prefix", ""))[-80:], str(sel.get("suffix", ""))[:80])
        end = start + len(quote)
    elif "start" in sel and "end" in sel:
        start, end = _int(sel["start"], "start", 0, len(text)), _int(sel["end"], "end", 0, len(text))
    elif "line_start" in sel:
        total = len(starts) - (1 if text.endswith("\n") else 0)
        first = _int(sel["line_start"], "line_start", 1, max(total, 1))
        last = _int(sel.get("line_end", first), "line_end", first, max(total, 1))
        start = starts[first - 1] + (_int(sel["char_start"], "char_start", 0, 10**7) if "char_start" in sel else 0)
        if "char_end" in sel:
            end = starts[last - 1] + _int(sel["char_end"], "char_end", 0, 10**7)
        else:
            end = (starts[last] - 1) if last < len(starts) else len(text)
    else:
        raise AnchorError("text selector needs quote, start+end, or line_start (optional line_end, char_start, char_end)")
    if not 0 <= start < end <= len(text):
        raise AnchorError("text range is empty or outside the file")
    if end - start > MAX_QUOTE:
        raise AnchorError(f"text range is longer than {MAX_QUOTE} characters; anchor a shorter place")
    loc = _text_location(text, starts, start, end)
    lo, hi = loc["line_start"], loc["line_end"]
    region_end = starts[hi] if hi < len(starts) else len(text)
    region = text[starts[lo - 1]:region_end].rstrip("\n")
    selector = {**loc, "prefix": text[max(0, start - 48):start], "suffix": text[end:end + 48]}
    return selector, {"region": region[:8000], "region_lines": hi - lo + 1}


def _text_resolve(sel, snap, data):
    text = _decode(data)
    starts = _line_starts(text)
    quote, start, end = sel["quote"], sel["start"], sel["end"]
    if text[start:end] == quote:
        return "intact", _text_location(text, starts, start, end), "same text at the same place"
    hits = _find_all(text, quote)
    if hits:
        at = _best_hit(text, hits, quote, sel.get("prefix", ""), sel.get("suffix", ""))
        loc = _text_location(text, starts, at, at + len(quote))
        return "moved", loc, f"same text now at line {loc['line_start']}"
    region, n = snap.get("region", ""), max(1, int(snap.get("region_lines", 1)))
    lines = text.split("\n")
    if len(lines) > 40000 or not region:
        return "lost", None, "text not found"
    best, best_ratio = None, 0.0
    matcher = difflib.SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(region)
    for width in sorted({n, max(1, n - 1), n + 1}):
        for i in range(0, max(1, len(lines) - width + 1)):
            window = "\n".join(lines[i:i + width])
            if not window.strip():
                continue
            matcher.set_seq1(window)
            if matcher.real_quick_ratio() < FUZZY_THRESHOLD or matcher.quick_ratio() < FUZZY_THRESHOLD or matcher.quick_ratio() < best_ratio:
                continue
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best, best_ratio = (i, width, window), ratio
    if best is None or best_ratio < FUZZY_THRESHOLD:
        return "lost", None, "text not found"
    i, width, window = best
    start = starts[i]
    end = start + len(window)
    return "changed", _text_location(text, starts, start, end), f"similar text at line {i + 1} (similarity {best_ratio:.2f}); content differs"


# ---------------------------------------------------------------- cells ----

def _col_number(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _col_letters(n):
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


_CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")


def _parse_range(text):
    parts = text.replace("$", "").split(":")
    if len(parts) > 2:
        raise AnchorError("cell range must look like A1 or A1:B3")
    corners = []
    for part in parts:
        m = _CELL.match(part.strip())
        if not m:
            raise AnchorError("cell range must look like A1 or A1:B3")
        corners.append((int(m.group(2)), _col_number(m.group(1).upper())))
    r0, c0 = corners[0]
    r1, c1 = corners[-1]
    r0, r1, c0, c1 = min(r0, r1), max(r0, r1), min(c0, c1), max(c0, c1)
    if (r1 - r0 + 1) * (c1 - c0 + 1) > 10000:
        raise AnchorError("anchor at most 10000 cells")
    return r0, c0, r1, c1


def _range_text(r0, c0, r1, c1):
    a = f"{_col_letters(c0)}{r0}"
    return a if (r0, c0) == (r1, c1) else f"{a}:{_col_letters(c1)}{r1}"


def _split_ref(sel):
    if isinstance(sel.get("ref"), str):
        ref = sel["ref"].strip()
        sheet, _, rng = ref.rpartition("!")
        sheet = sheet[1:-1].replace("''", "'") if sheet.startswith("'") and sheet.endswith("'") else sheet
        return sheet or None, rng
    if not isinstance(sel.get("range"), str):
        raise AnchorError("cell selector needs ref ('Sheet1!A1:B3') or sheet + range")
    sheet = sel.get("sheet")
    return (str(sheet) if sheet else None), sel["range"]


def _xlsx_sheets(data):
    try:
        from .hoard_link.docs.readers_lite import check_zip
        z = zipfile.ZipFile(io.BytesIO(data))
        check_zip(z)
    except Exception as exc:
        raise AnchorError(f"workbook cannot be read: {exc}") from None
    return z


def _xlsx_sheet_names(z):
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels}
    out = {}
    for el in wb.iter():
        if el.tag.endswith("}sheet"):
            rid = next((v for k, v in el.attrib.items() if k.endswith("}id")), None)
            target = targets.get(rid, "")
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            out[el.get("name")] = target
    return out


def _xlsx_cells(data, sheet):
    z = _xlsx_sheets(data)
    names = _xlsx_sheet_names(z)
    if sheet is None:
        sheet = next(iter(names), None)
    if sheet not in names:
        return sheet, list(names), None
    strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
            strings.append("".join(t.text or "" for t in si.iter() if t.tag.endswith("}t")))
    cells = {}
    for _, el in ET.iterparse(io.BytesIO(z.read(names[sheet])), events=("end",)):
        if not el.tag.endswith("}c"):
            continue
        m = _CELL.match(el.get("r", ""))
        if not m:
            continue
        kind = el.get("t")
        v = next((c for c in el if c.tag.endswith("}v")), None)
        if kind == "inlineStr":
            value = "".join(t.text or "" for t in el.iter() if t.tag.endswith("}t"))
        elif v is None or v.text is None:
            value = ""
        elif kind == "s":
            idx = int(v.text)
            value = strings[idx] if idx < len(strings) else ""
        else:
            value = v.text
        if value != "":
            cells[(int(m.group(2)), _col_number(m.group(1).upper()))] = value
        el.clear()
    return sheet, list(names), cells


def _csv_cells(data):
    text = data.decode("utf-8-sig", errors="replace")
    head = text.split("\n", 1)[0]
    delimiter = max(",;\t|", key=head.count) if head else ","
    cells = {}
    for r, row in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter), 1):
        for c, value in enumerate(row, 1):
            if value != "":
                cells[(r, c)] = value
    return "csv", ["csv"], cells


def _cells_for(data, name, sheet):
    ext = _suffix(name)
    if ext in (".csv", ".tsv"):
        return _csv_cells(data)
    if ext in (".xlsx", ".xlsm"):
        return _xlsx_cells(data, sheet)
    raise AnchorError("cell anchors need a .csv, .tsv or .xlsx file")


def _grid(cells, r0, c0, r1, c1):
    return [[cells.get((r, c), "") for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]


def _cell_capture(sel, data, name):
    sheet, rng = _split_ref(sel)
    r0, c0, r1, c1 = _parse_range(rng)
    sheet, names, cells = _cells_for(data, name, sheet)
    if cells is None:
        raise AnchorError(f"sheet not found; available: {', '.join(map(str, names))}")
    selector = {"sheet": sheet, "range": _range_text(r0, c0, r1, c1), "ref": f"{sheet}!{_range_text(r0, c0, r1, c1)}"}
    return selector, {"values": _grid(cells, r0, c0, r1, c1)}


def _cell_resolve(sel, snap, data, name):
    r0, c0, r1, c1 = _parse_range(sel["range"])
    sheet, names, cells = _cells_for(data, name, sel["sheet"])
    if cells is None:
        return "lost", None, f"sheet '{sel['sheet']}' no longer exists"
    old = snap["values"]
    here = _grid(cells, r0, c0, r1, c1)
    loc = {"sheet": sheet, "range": sel["range"], "ref": f"{sheet}!{sel['range']}", "values": here}
    if here == old:
        return "intact", loc, "same values at the same address"
    h, w = len(old), len(old[0])
    if any(v for row in old for v in row):
        first = next((v for v in old[0] if v), None)
        matches = []
        if first is not None:
            for (r, c), v in cells.items():
                if v != first:
                    continue
                c_start = c - next(i for i, x in enumerate(old[0]) if x)
                if c_start < 1 or (r, c_start) == (r0, c0):
                    continue
                if _grid(cells, r, c_start, r + h - 1, c_start + w - 1) == old:
                    matches.append((r, c_start))
                if len(matches) > 1:
                    break
        if len(matches) == 1:
            r, c = matches[0]
            rng = _range_text(r, c, r + h - 1, c + w - 1)
            return "moved", {"sheet": sheet, "range": rng, "ref": f"{sheet}!{rng}", "values": old}, f"same values now at {rng}"
    return "changed", loc, "values at this address differ from the anchored ones"


# ----------------------------------------------------------------- code ----

_BRACE_DEF = [
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\*?|class|interface|struct|enum|trait|impl|namespace|module|def|fn|func|fun)\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>)"),
    re.compile(r"^\s*(?:(?:public|private|protected|static|final|abstract|virtual|override|async|inline|extern)\s+)*[\w<>\[\],.*&]+\s+([A-Za-z_]\w*)\s*\([^;{)]*\)\s*(?:const\s*)?(?:throws\s[^{]*)?\{"),
]
_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "else", "do", "new", "sizeof"}


def _block_end(lines, i):
    """Last 0-based line of the block starting at line i (brace or indent based)."""
    depth, seen = 0, False
    for j in range(i, min(len(lines), i + 4000)):
        stripped = re.sub(r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`[^`]*`)", "", lines[j])
        stripped = re.sub(r"//.*$|#.*$", "", stripped)
        for ch in stripped:
            if ch == "{":
                depth += 1
                seen = True
            elif ch == "}":
                depth -= 1
        if seen and depth <= 0:
            return j
        if not seen and j >= i + 3:
            break
    indent = len(lines[i]) - len(lines[i].lstrip())
    end = i
    for j in range(i + 1, len(lines)):
        if lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) <= indent:
            break
        if lines[j].strip():
            end = j
    return end


def _symbols(text, name):
    lines = text.split("\n")
    out = []
    if _suffix(name) == ".py" or _suffix(name) == ".pyw":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            def walk(node, prefix):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        qual = prefix + child.name
                        start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                        out.append({"name": qual, "simple": child.name, "line_start": start, "line_end": child.end_lineno})
                        if isinstance(child, ast.ClassDef):
                            walk(child, qual + ".")
                        else:
                            walk(child, qual + ".")
                    else:
                        walk(child, prefix)
            walk(tree, "")
    if not out:
        stack = []
        for i, line in enumerate(lines):
            for pat in _BRACE_DEF:
                m = pat.match(line)
                if m and m.group(1) not in _KEYWORDS:
                    end = _block_end(lines, i)
                    while stack and stack[-1][1] < i:
                        stack.pop()
                    qual = ".".join([s[0] for s in stack] + [m.group(1)])
                    out.append({"name": qual, "simple": m.group(1), "line_start": i + 1, "line_end": end + 1})
                    if end > i:
                        stack.append((m.group(1), end))
                    break
    for s in out:
        s["body"] = _norm_ws("\n".join(lines[s["line_start"] - 1:s["line_end"]]))
    return out


def _code_capture(sel, data, name):
    text = _decode(data)
    syms = _symbols(text, name)
    wanted = sel.get("symbol")
    if isinstance(wanted, str) and wanted.strip():
        wanted = wanted.strip()
        cands = [s for s in syms if s["name"] == wanted] or [s for s in syms if s["simple"] == wanted]
        if not cands:
            raise AnchorError("symbol not found in the current revision")
        hint = sel.get("line_start")
        cand = min(cands, key=lambda s: abs(s["line_start"] - hint) if isinstance(hint, int) else s["line_start"])
    elif "line_start" in sel:
        line = _int(sel["line_start"], "line_start", 1, max(1, text.count("\n") + 1))
        inside = [s for s in syms if s["line_start"] <= line <= s["line_end"]]
        if not inside:
            raise AnchorError("no symbol contains that line; give a symbol name")
        cand = min(inside, key=lambda s: s["line_end"] - s["line_start"])
    else:
        raise AnchorError("code selector needs symbol (optional line_start as a hint)")
    selector = {"symbol": cand["name"], "line_start": cand["line_start"], "line_end": cand["line_end"]}
    return selector, {"body_hash": _hash(cand["body"]), "body": cand["body"][:4000]}


def _code_resolve(sel, snap, data, name):
    syms = _symbols(_decode(data), name)
    cands = [s for s in syms if s["name"] == sel["symbol"]] or [s for s in syms if s["simple"] == sel["symbol"].rsplit(".", 1)[-1]]
    if not cands:
        return "lost", None, f"symbol '{sel['symbol']}' not found"
    cand = min(cands, key=lambda s: abs(s["line_start"] - sel["line_start"]))
    loc = {"symbol": cand["name"], "line_start": cand["line_start"], "line_end": cand["line_end"]}
    if _hash(cand["body"]) != snap["body_hash"]:
        return "changed", loc, "symbol body differs"
    if (cand["line_start"], cand["line_end"]) == (sel["line_start"], sel["line_end"]):
        return "intact", loc, "same symbol at the same lines"
    return "moved", loc, f"symbol now at lines {cand['line_start']}-{cand['line_end']}"


# ------------------------------------------------------------------ pdf ----

def _pdf_pages(data):
    """[{"count"}...] -> list of pages: {"chunks": [(text, x, y)]} in normalised top-left coordinates."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            box = page.mediabox
            left, bottom = float(box.left), float(box.bottom)
            w, h = float(box.width) or 1.0, float(box.height) or 1.0
            chunks = []

            def visit(text, cm, tm, font, size, chunks=chunks, left=left, bottom=bottom, w=w, h=h):
                if not text or not text.strip():
                    return
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                chunks.append((text.strip(), round((x - left) / w, 4), round(1 - (y - bottom) / h, 4)))
            page.extract_text(visitor_text=visit)
            pages.append({"chunks": chunks})
        return pages
    except Exception as exc:
        raise AnchorError(f"PDF cannot be read: {exc}") from None


def _pdf_count(data):
    pages = _pdf_pages(data)
    if pages is not None:
        return len(pages)
    counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data)]
    return max(counts) if counts else None


def _rect(sel):
    raw = sel.get("rect")
    if isinstance(raw, dict):
        raw = [raw.get("x0"), raw.get("y0"), raw.get("x1"), raw.get("y1")]
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise AnchorError("rect must be [x0, y0, x1, y1] in 0..1 page coordinates (origin top-left)")
    x0, y0, x1, y1 = (round(_num(v, "rect", 0.0, 1.0), 4) for v in raw)
    if x0 >= x1 or y0 >= y1:
        raise AnchorError("rect must have x0<x1 and y0<y1")
    return [x0, y0, x1, y1]


def _inside(chunk, rect, pad=0.0):
    _, x, y = chunk
    return rect[0] - pad <= x <= rect[2] + pad and rect[1] - pad <= y <= rect[3] + pad


def _near(chunks, rect, margin=0.12):
    out = [c for c in chunks if _inside(c, rect, margin) and not _inside(c, rect)]
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    return sorted(out, key=lambda c: (c[1] - cx) ** 2 + (c[2] - cy) ** 2)[:8]


def _pdf_capture(sel, data):
    page = _int(sel.get("page"), "page", 1, 100000)
    rect = _rect(sel)
    pages = _pdf_pages(data)
    if pages is None:
        count = _pdf_count(data)
        if count is not None and page > count:
            raise AnchorError(f"page {page} does not exist; the PDF has {count} pages")
        return {"page": page, "rect": rect}, {"inside": [], "near": [], "text_available": False}
    if page > len(pages):
        raise AnchorError(f"page {page} does not exist; the PDF has {len(pages)} pages")
    chunks = pages[page - 1]["chunks"]
    inside = [c for c in chunks if _inside(c, rect)]
    return {"page": page, "rect": rect}, {"inside": inside[:40], "near": _near(chunks, rect) if not inside else [], "text_available": True,
                                          "page_count": len(pages)}


def _find_shift(key, pages, order, fraction):
    """Find (page_index, dx, dy, matched) where >=fraction of key chunks reappear with one consistent shift."""
    tol = 0.006
    best = None
    for pi in order:
        chunks = pages[pi]["chunks"]
        for anchor in (k for k in key if True):
            for c in chunks:
                if c[0] != anchor[0]:
                    continue
                dx, dy = c[1] - anchor[1], c[2] - anchor[2]
                matched = sum(1 for k in key if any(o[0] == k[0] and abs(o[1] - (k[1] + dx)) <= tol and abs(o[2] - (k[2] + dy)) <= tol for o in chunks))
                if matched / len(key) >= fraction and (best is None or matched > best[3] or (matched == best[3] and abs(dx) + abs(dy) < abs(best[1]) + abs(best[2]) and pi == best[0])):
                    best = (pi, dx, dy, matched)
        if best and best[3] == len(key):
            return best
    return best


def _shift_rect(rect, dx, dy):
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    x0 = min(max(rect[0] + dx, 0.0), 1.0 - w)
    y0 = min(max(rect[1] + dy, 0.0), 1.0 - h)
    return [round(x0, 4), round(y0, 4), round(x0 + w, 4), round(y0 + h, 4)]


def _pdf_resolve(sel, snap, data):
    page, rect = sel["page"], sel["rect"]
    pages = _pdf_pages(data)
    if pages is None:
        count = _pdf_count(data)
        if count is not None and page > count:
            return "lost", None, f"page {page} no longer exists"
        return "intact", {"page": page, "rect": rect}, "page exists; text position check needs the pypdf package"
    if page > len(pages):
        return _pdf_elsewhere(sel, snap, pages)
    chunks = pages[page - 1]["chunks"]
    inside = [tuple(c) for c in snap.get("inside", [])]
    near = [tuple(c) for c in snap.get("near", [])]
    now = [c for c in chunks if _inside(c, rect)]
    if inside:
        if sorted(c[0] for c in now) == sorted(c[0] for c in inside):
            return "intact", {"page": page, "rect": rect}, "same text inside the rectangle"
        order = [page - 1] + [i for i in range(len(pages)) if i != page - 1]
        hit = _find_shift(inside, pages, order, 1.0)
        if hit:
            pi, dx, dy, _ = hit
            return "moved", {"page": pi + 1, "rect": _shift_rect(rect, dx, dy)}, f"same text now on page {pi + 1}"
        fallback = near or _near(chunks, rect)
    else:
        fallback = near
        if not fallback and not now:
            return "intact", {"page": page, "rect": rect}, "page exists; the rectangle has no text to compare"
    if fallback:
        hit = _find_shift(fallback, pages, [page - 1], 0.5)
        if hit and hit[0] == page - 1:
            _, dx, dy, _ = hit
            loc = {"page": page, "rect": _shift_rect(rect, dx, dy)}
            if not inside and abs(dx) < 0.004 and abs(dy) < 0.004:
                return "intact", loc, "surrounding text unchanged"
            if not inside:
                return "moved", loc, "surrounding text moved with the region"
            return "changed", loc, "text inside the rectangle differs"
    return "lost" if not now else "changed", ({"page": page, "rect": rect} if now else None), "text around the anchor was not found"


def _pdf_elsewhere(sel, snap, pages):
    inside = [tuple(c) for c in snap.get("inside", [])] or [tuple(c) for c in snap.get("near", [])]
    hit = _find_shift(inside, pages, range(len(pages)), 1.0) if inside else None
    if hit:
        pi, dx, dy, _ = hit
        return "moved", {"page": pi + 1, "rect": _shift_rect(sel["rect"], dx, dy)}, f"same text now on page {pi + 1}"
    return "lost", None, f"page {sel['page']} no longer exists"


# ---------------------------------------------------------- image / time ----

def _image_size(data):
    if not data:
        return None
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", data[6:10])
        if data[:2] == b"BM":
            w, h = struct.unpack("<ii", data[18:26])
            return w, abs(h)
        if data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                size = struct.unpack(">H", data[i + 2:i + 4])[0]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                i += 2 + size
    except Exception:
        return None
    return None


def _image_capture(sel, data):
    if sel.get("rect") is None:
        x, y, w, h = (_num(sel.get(k), k, 0.0, 1.0) for k in ("x", "y", "w", "h"))
        rect = [x, y, x + w, y + h]
        if rect[2] > 1.0001 or rect[3] > 1.0001:
            raise AnchorError("image region exceeds the image")
        rect = [round(v, 4) for v in (rect[0], rect[1], min(rect[2], 1.0), min(rect[3], 1.0))]
        if rect[0] >= rect[2] or rect[1] >= rect[3]:
            raise AnchorError("image region must have a positive size")
    else:
        rect = _rect(sel)
    size = _image_size(data)
    return {"rect": rect, "x": rect[0], "y": rect[1], "w": round(rect[2] - rect[0], 4), "h": round(rect[3] - rect[1], 4)}, \
        {"size": list(size) if size else None}


def _image_resolve(sel, snap, data):
    loc = {k: sel[k] for k in ("rect", "x", "y", "w", "h")}
    now, old = _image_size(data), snap.get("size")
    if now and old and list(now) != list(old):
        return "changed", loc, f"image size changed from {old[0]}x{old[1]} to {now[0]}x{now[1]}; the normalised region now covers different pixels"
    return "intact", loc, "image size unchanged" if now else "image size could not be read; region kept"


def _duration(data, name):
    if not data:
        return None
    try:
        if data[:4] == b"RIFF":
            with wave.open(io.BytesIO(data)) as w:
                return round(w.getnframes() / float(w.getframerate()), 3)
        at = data.find(b"mvhd")
        if at > 0:
            version = data[at + 4]
            if version == 1:
                scale, dur = struct.unpack(">IQ", data[at + 24:at + 36])
            else:
                scale, dur = struct.unpack(">II", data[at + 16:at + 24])
            return round(dur / scale, 3) if scale else None
    except Exception:
        return None
    return None


def _time_capture(sel, data, name):
    start = round(_num(sel.get("start"), "start"), 3)
    end = round(_num(sel.get("end", start), "end"), 3)
    if end < start:
        raise AnchorError("end must not be before start")
    duration = _duration(data, name)
    if duration is None and sel.get("duration") is not None:
        duration = round(_num(sel["duration"], "duration"), 3)
    if duration is not None and start >= duration:
        raise AnchorError(f"start is beyond the media duration ({duration}s)")
    return {"start": start, "end": end}, {"duration": duration}


def _time_resolve(sel, snap, data, name):
    loc = {"start": sel["start"], "end": sel["end"]}
    now, old = _duration(data, name), snap.get("duration")
    if now is None or old is None:
        return "intact", loc, "duration could not be compared; range kept"
    if abs(now - old) < 0.05:
        return "intact", loc, "same duration"
    if sel["start"] >= now:
        return "lost", None, f"range starts after the new end ({now}s)"
    return "changed", loc, f"duration changed from {old}s to {now}s"


# ----------------------------------------------------------------- mesh ----

def _mesh_parts(data, name):
    ext = _suffix(name)
    if ext in (".glb", ".gltf"):
        if ext == ".glb":
            if data[:4] != b"glTF" or len(data) < 20:
                raise AnchorError("not a valid GLB file")
            length, kind = struct.unpack("<II", data[12:20])
            doc = json.loads(data[20:20 + length].decode("utf-8"))
        else:
            doc = json.loads(data.decode("utf-8-sig"))
        acc, meshes = doc.get("accessors", []), doc.get("meshes", [])
        parts = []
        for i, node in enumerate(doc.get("nodes", [])):
            tri, shape = 0, []
            if isinstance(node.get("mesh"), int) and node["mesh"] < len(meshes):
                for prim in meshes[node["mesh"]].get("primitives", []):
                    idx = prim.get("indices")
                    pos = prim.get("attributes", {}).get("POSITION")
                    a = acc[idx] if isinstance(idx, int) and idx < len(acc) else None
                    p = acc[pos] if isinstance(pos, int) and pos < len(acc) else None
                    tri += (a["count"] if a else p["count"] if p else 0) // 3
                    shape.append([a and a.get("count"), p and p.get("count"), p and p.get("min"), p and p.get("max")])
            parts.append({"name": node.get("name"), "index": i, "faces": tri, "fingerprint": _hash(json.dumps([shape, node.get("translation"), node.get("scale"), node.get("rotation")], sort_keys=True))})
        return parts
    if ext == ".obj":
        text = data.decode("utf-8", errors="replace")
        verts, parts, cur = [], [], None
        for line in text.splitlines():
            tag, _, rest = line.strip().partition(" ")
            if tag == "v":
                verts.append(rest.strip())
            elif tag in ("o", "g"):
                cur = {"name": rest.strip() or None, "index": len(parts), "faces": 0, "geo": []}
                parts.append(cur)
            elif tag == "f":
                if cur is None:
                    cur = {"name": None, "index": 0, "faces": 0, "geo": []}
                    parts.append(cur)
                cur["faces"] += 1
                for tok in rest.split():
                    try:
                        i = int(tok.split("/")[0])
                        cur["geo"].append(verts[i - 1] if i > 0 else verts[i])
                    except (ValueError, IndexError):
                        cur["geo"].append(tok)
        for p in parts:
            p["fingerprint"] = _hash("|".join(p.pop("geo")))
        return [p for p in parts if p["faces"]]
    if ext == ".stl":
        head = data[:5].lower() == b"solid" and b"facet" in data[:2000]
        if head:
            parts, cur = [], None
            for line in data.decode("utf-8", errors="replace").splitlines():
                s = line.strip()
                if s.lower().startswith("solid"):
                    cur = {"name": s[5:].strip() or None, "index": len(parts), "faces": 0, "geo": []}
                    parts.append(cur)
                elif s.lower().startswith("facet") and cur:
                    cur["faces"] += 1
                elif s.lower().startswith("vertex") and cur:
                    cur["geo"].append(s)
            for p in parts:
                p["fingerprint"] = _hash("|".join(p.pop("geo")))
            return parts
        if len(data) < 84:
            raise AnchorError("not a valid STL file")
        count = struct.unpack("<I", data[80:84])[0]
        return [{"name": None, "index": 0, "faces": count, "fingerprint": hashlib.sha256(data[84:]).hexdigest()[:24]}]
    raise AnchorError("mesh anchors need a .glb, .gltf, .obj or .stl file")


def _mesh_find(parts, sel):
    name, index = sel.get("node"), sel.get("node_index")
    if isinstance(name, str) and name not in ("", "*"):
        found = [p for p in parts if p["name"] == name]
        if found:
            return min(found, key=lambda p: abs(p["index"] - index) if isinstance(index, int) else p["index"])
        return None
    if isinstance(index, int) and 0 <= index < len(parts):
        return parts[index]
    if len(parts) == 1 and (name in (None, "", "*")) and index is None:
        return parts[0]
    return None


def _mesh_capture(sel, data, name):
    parts = _mesh_parts(data, name)
    node, index = sel.get("node"), sel.get("node_index")
    if node is not None and not isinstance(node, str):
        raise AnchorError("node must be the node name")
    if index is not None:
        _int(index, "node_index", 0, 10**7)
    if node in (None, "", "*") and index is None and len(parts) != 1:
        raise AnchorError("give node (name) or node_index; parts: " + ", ".join(str(p["name"] or p["index"]) for p in parts[:20]))
    part = _mesh_find(parts, sel)
    if part is None:
        raise AnchorError("part not found; parts: " + ", ".join(str(p["name"] or p["index"]) for p in parts[:20]))
    faces = sel.get("faces")
    if faces is not None:
        if not isinstance(faces, list) or len(faces) > 10000:
            raise AnchorError("faces must be a list of at most 10000 triangle indices")
        faces = sorted({_int(f, "face", 0, max(part["faces"] - 1, 0)) for f in faces})
    selector = {"node": part["name"], "node_index": part["index"], "faces": faces}
    return selector, {"face_count": part["faces"], "fingerprint": part["fingerprint"]}


def _mesh_resolve(sel, snap, data, name):
    parts = _mesh_parts(data, name)
    part = _mesh_find(parts, sel) if sel.get("node") else (parts[sel["node_index"]] if sel.get("node_index") is not None and sel["node_index"] < len(parts) else None)
    label = sel.get("node") or sel.get("node_index")
    if part is None:
        return "lost", None, f"part '{label}' not found (a renamed part is reported lost)"
    loc = {"node": part["name"], "node_index": part["index"], "faces": sel.get("faces")}
    faces = sel.get("faces") or []
    if part["fingerprint"] != snap["fingerprint"] or part["faces"] != snap["face_count"] or (faces and faces[-1] >= part["faces"]):
        return "changed", loc, "geometry of the part differs"
    if part["index"] != sel.get("node_index"):
        return "moved", loc, f"part now at index {part['index']}"
    return "intact", loc, "same part, same geometry"


# ------------------------------------------------------------- dispatch ----

_EXT = {"pdf": (".pdf",), "cell": (".csv", ".tsv", ".xlsx", ".xlsm"), "mesh": (".glb", ".gltf", ".obj", ".stl")}


def capture(kind, selector, data, name):
    """Validate ``selector`` on one revision; return (normalised selector, snapshot)."""
    if kind not in KINDS:
        raise AnchorError("kind must be one of " + ", ".join(KINDS))
    if not isinstance(selector, dict):
        raise AnchorError("selector must be an object")
    if kind in _EXT and _suffix(name) not in _EXT[kind]:
        raise AnchorError(f"{kind} anchors need a {'/'.join(_EXT[kind])} file")
    if data is None and kind in NEEDS_BYTES:
        raise AnchorError("file is too large to anchor (limit 64 MiB)", 413)
    if kind == "text":
        return _text_capture(selector, data)
    if kind == "cell":
        return _cell_capture(selector, data, name)
    if kind == "code":
        return _code_capture(selector, data, name)
    if kind == "pdf":
        return _pdf_capture(selector, data)
    if kind == "image":
        return _image_capture(selector, data)
    if kind == "time":
        return _time_capture(selector, data, name)
    return _mesh_capture(selector, data, name)


def resolve(kind, selector, snapshot, data, name):
    """Find the anchored place in another revision: (status, location|None, detail)."""
    if data is None and kind in NEEDS_BYTES:
        return "lost", None, "file is too large to inspect"
    try:
        if kind == "text":
            return _text_resolve(selector, snapshot, data)
        if kind == "cell":
            return _cell_resolve(selector, snapshot, data, name)
        if kind == "code":
            return _code_resolve(selector, snapshot, data, name)
        if kind == "pdf":
            return _pdf_resolve(selector, snapshot, data)
        if kind == "image":
            return _image_resolve(selector, snapshot, data)
        if kind == "time":
            return _time_resolve(selector, snapshot, data, name)
        return _mesh_resolve(selector, snapshot, data, name)
    except AnchorError as exc:
        return "lost", None, str(exc)
    except Exception as exc:  # corrupt or unsupported content: honest, not a crash
        return "lost", None, f"revision could not be read ({type(exc).__name__})"


def open_block(kind, location):
    """Everything a client needs to jump to the place, beyond the file path."""
    if not location:
        return {}
    keep = {"text": ("start", "end", "line_start", "line_end", "quote"), "cell": ("sheet", "range", "ref"),
            "code": ("symbol", "line_start", "line_end"), "pdf": ("page", "rect"), "image": ("rect", "x", "y", "w", "h"),
            "time": ("start", "end"), "mesh": ("node", "node_index", "faces")}[kind]
    block = {k: location[k] for k in keep if k in location}
    if kind == "text":
        block = {**block, "char_start": block.pop("start"), "char_end": block.pop("end")}
    if kind == "time":
        block = {"time_start": block["start"], "time_end": block["end"]}
    fragment = {"pdf": lambda: f"page={location['page']}", "time": lambda: f"t={location['start']},{location['end']}",
                "text": lambda: f"L{location['line_start']}-L{location['line_end']}", "code": lambda: f"L{location['line_start']}-L{location['line_end']}",
                "cell": lambda: location["ref"], "mesh": lambda: f"node={location.get('node') or location.get('node_index')}",
                "image": lambda: "xywh=pixel:" + ",".join(str(location[k]) for k in ("x", "y", "w", "h"))}[kind]()
    return {"kind": kind, **block, "fragment": fragment}
