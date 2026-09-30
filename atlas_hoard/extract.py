"""Readable text out of HTML, PDF and plain text: a small readability-style extractor (no JavaScript)."""

from __future__ import annotations

import io
import json
import re
from typing import Any

from bs4 import BeautifulSoup

from .dates import normalize
from .errors import AtlasError

MAX_TEXT_CHARS = 400_000
_DROP = ["script", "style", "noscript", "template", "iframe", "svg", "form", "nav", "footer", "aside", "button",
         "select", "canvas", "dialog"]
_BLOCKS = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "figcaption", "td", "dd", "dt"]


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name}) \
            or soup.find("meta", attrs={"itemprop": name})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return ""


def _published(soup: BeautifulSoup) -> str | None:
    candidates = [_meta(soup, "article:published_time", "og:article:published_time", "datePublished", "date",
                        "pubdate", "DC.date", "DC.date.issued", "dcterms.created")]
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data: Any = json.loads(script.string or "")
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("datePublished"):
                candidates.append(str(item["datePublished"]))
    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        candidates.append(str(time_tag["datetime"]))
    for raw in candidates:
        if raw:
            try:
                return normalize(raw[:10])
            except AtlasError:
                continue
    return None


def _score(element) -> float:
    text = element.get_text(" ", strip=True)
    if not text:
        return 0.0
    links = sum(len(a.get_text(" ", strip=True)) for a in element.find_all("a"))
    density = links / max(len(text), 1)
    return len(text) * (1 - density) + 60 * len(element.find_all("p"))


def extract_html(html: str) -> dict[str, Any]:
    """Title, main text and published date of an HTML document."""
    soup = BeautifulSoup(html or "", "html.parser")
    title = _meta(soup, "og:title", "twitter:title") or (soup.title.get_text(" ", strip=True) if soup.title else "")
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else ""
    published = _published(soup)
    lang = (soup.html.get("lang") if soup.html else "") or ""
    for tag in soup(_DROP):
        tag.decompose()
    for tag in soup.find_all(attrs={"aria-hidden": "true"}):
        tag.decompose()
    best = None
    for selector in ("article", "main", "[role=main]"):
        found = soup.select(selector)
        if found:
            top = max(found, key=_score)
            if _score(top) > 300:
                best = top
                break
    if best is None:
        pool = soup.find_all(["div", "section", "td"])
        best = max(pool, key=_score) if pool else None
        if best is None or _score(best) < 80:
            best = soup.body or soup
    lines: list[str] = []
    blocks = best.find_all(_BLOCKS)
    if blocks:
        for block in blocks:
            if block.find(_BLOCKS):  # its children will be visited on their own
                continue
            line = re.sub(r"\s+", " ", block.get_text(" ", strip=True))
            if len(line) >= 2 and (not lines or lines[-1] != line):
                lines.append(line)
    else:
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in best.get_text("\n").splitlines() if len(ln.strip()) >= 2]
    return {"title": re.sub(r"\s+", " ", title).strip()[:300], "text": "\n\n".join(lines)[:MAX_TEXT_CHARS],
            "published_at": published, "lang": lang[:10]}


def extract_pdf(data: bytes) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - pypdf is optional
        raise AtlasError("Reading PDFs needs pypdf (pip install pypdf).") from error
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages[:400]]
        meta = reader.metadata
    except Exception as error:  # noqa: BLE001 - pypdf raises many types on damaged files
        raise AtlasError(f"The PDF could not be read: {error}") from error
    title = str(getattr(meta, "title", "") or "") if meta else ""
    text = "\n\n".join(f"[page {i + 1}]\n{t}" for i, t in enumerate(pages) if t)
    return {"title": title.strip()[:300], "text": text[:MAX_TEXT_CHARS], "published_at": None, "lang": ""}


def decode_text(data: bytes, content_type: str = "") -> str:
    match = re.search(r"charset=([\w-]+)", content_type or "", flags=re.I)
    for encoding in ([match.group(1)] if match else []) + ["utf-8-sig", "latin-1"]:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def extract_bytes(data: bytes, content_type: str = "", name: str = "") -> dict[str, Any]:
    """Dispatch on content type / file name; always returns title, text, published_at."""
    lower = (content_type or "").lower()
    suffix = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if "pdf" in lower or suffix == "pdf" or data[:5] == b"%PDF-":
        return extract_pdf(data)
    text = decode_text(data, content_type)
    if "html" in lower or suffix in ("html", "htm") or re.search(r"<\s*(html|body|p|div)\b", text[:2000], flags=re.I):
        return extract_html(text)
    return {"title": "", "text": text[:MAX_TEXT_CHARS], "published_at": None, "lang": ""}
