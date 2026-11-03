"""Multimodal anchors: capture, re-resolution across revisions, history pinning, REST/MCP surface."""
import json
from pathlib import Path
import struct

import pytest

from atlas_hoard.store import Workspace, StoreError


@pytest.fixture
def store(tmp_path):
    workspace = Workspace(tmp_path / "private", tmp_path / "disk")
    yield workspace
    workspace.close()


@pytest.fixture
def proj(store):
    return store.dispatch("atlas_project_create", {"name": "Anclas", "owner": "writer", "members": ["writer", "lumiere"]})["project"]


def put(store, p, relative, data, caller="writer"):
    path = Path(p["path"]) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return store.dispatch("atlas_file_register", {"project_id": p["id"], "relative_path": relative}, caller)["file"]


def anchor(store, f, kind, selector, **extra):
    return store.dispatch("atlas_anchor_create", {"file_id": f["id"], "kind": kind, "selector": selector, **extra}, "writer")["anchor"]


def resolve(store, a, **extra):
    return store.dispatch("atlas_anchor_resolve", {"anchor_id": a["id"], **extra}, "lumiere")


def rewrite(store, p, f, relative, data):
    (Path(p["path"]) / relative).write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return store.dispatch("atlas_file_resolve", {"file_id": f["id"]}, "writer")


V1 = "Intro paragraph.\n\nThe quick brown fox jumps over the lazy dog.\n\nClosing words here.\n"
V2 = "Intro paragraph.\n\nA freshly inserted paragraph\nwith two lines.\n\nThe quick brown fox jumps over the lazy dog.\n\nClosing words here.\n"


def test_text_quote_moves_when_a_paragraph_is_inserted_and_history_stays_pinned(store, proj):
    f = put(store, proj, "shared/doc.txt", V1)
    a = anchor(store, f, "text", {"quote": "quick brown fox"}, label="Zorro", comment="Revisar esta frase")
    assert a["status"] == "intact" and a["revision_seq"] == 1 and a["selector"]["line_start"] == 3
    rewrite(store, proj, f, "shared/doc.txt", V2)
    r = resolve(store, a)
    assert r["status"] == "moved" and r["location"]["line_start"] == 6
    assert r["open"]["line_start"] == 6 and r["open"]["viewable"] and r["open"]["path"].endswith("doc.txt")
    # Pinned history: the original revision and its comment stay on revision 1.
    assert r["origin"]["revision_seq"] == 1 and r["origin"]["selector"]["line_start"] == 3
    assert [h["status"] for h in r["history"]] == ["intact", "moved"]
    assert r["comments"][0]["revision_seq"] == 1 and r["comments"][0]["status_at_revision"] == "intact"
    first = resolve(store, a, revision=1)
    assert first["status"] == "intact" and first["location"]["line_start"] == 3
    assert first["open"]["viewable"] is False and first["open"]["revision_seq"] == 1
    # A comment made now lands on revision 2 and r1's comment is untouched.
    store.dispatch("atlas_anchor_comment", {"anchor_id": a["id"], "text": "Ahora esta mas abajo"}, "lumiere")
    comments = store.dispatch("atlas_anchor_get", {"anchor_id": a["id"]}, "writer")["comments"]
    assert [(c["revision_seq"], c["status_at_revision"]) for c in comments] == [(1, "intact"), (2, "moved")]


def test_text_changed_and_lost_and_offsets_selectors(store, proj):
    f = put(store, proj, "shared/doc.txt", V1)
    by_lines = anchor(store, f, "text", {"line_start": 3, "line_end": 3})
    by_offsets = anchor(store, f, "text", {"start": 0, "end": 5})
    assert by_lines["selector"]["quote"].startswith("The quick") and by_offsets["selector"]["quote"] == "Intro"
    rewrite(store, proj, f, "shared/doc.txt", V1.replace("lazy dog", "sleepy cat"))
    assert resolve(store, by_lines)["status"] == "changed"
    rewrite(store, proj, f, "shared/doc.txt", "Totally different content\nabout something else entirely\n")
    assert resolve(store, by_lines)["status"] == "lost"
    assert [h["status"] for h in resolve(store, by_lines)["history"]] == ["intact", "changed", "lost"]
    with pytest.raises(StoreError):
        anchor(store, f, "text", {"quote": "not in file"})


def test_csv_cell_changed_and_moved_by_row_insert(store, proj):
    f = put(store, proj, "shared/data.csv", "name,qty\nbolt,10\nnut,20\n")
    cell = anchor(store, f, "cell", {"ref": "csv!B2"})
    block = anchor(store, f, "cell", {"sheet": "csv", "range": "A3:B3"})
    assert cell["selector"]["range"] == "B2"
    rewrite(store, proj, f, "shared/data.csv", "name,qty\nbolt,12\nnut,20\n")
    assert resolve(store, cell)["status"] == "changed" and resolve(store, cell)["location"]["values"] == [["12"]]
    assert resolve(store, block)["status"] == "intact"
    rewrite(store, proj, f, "shared/data.csv", "name,qty\nwasher,5\nbolt,12\nnut,20\n")
    moved = resolve(store, block)
    assert moved["status"] == "moved" and moved["location"]["range"] == "A4:B4" and moved["open"]["fragment"] == "csv!A4:B4"


def test_xlsx_cell_value_check(store, proj, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    def book(value, sheet="Datos"):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet
        ws["A1"], ws["B2"], ws["C3"] = "total", value, "fin"
        out = tmp_path / "book.xlsx"
        wb.save(out)
        return out.read_bytes()
    f = put(store, proj, "shared/book.xlsx", book(100))
    a = anchor(store, f, "cell", {"ref": "Datos!A1:B2"})
    assert a["selector"]["range"] == "A1:B2"
    rewrite(store, proj, f, "shared/book.xlsx", book(100))
    assert resolve(store, a)["status"] == "intact"
    rewrite(store, proj, f, "shared/book.xlsx", book(250))
    changed = resolve(store, a)
    assert changed["status"] == "changed" and changed["location"]["values"] == [["total", ""], ["", "250"]]
    rewrite(store, proj, f, "shared/book.xlsx", book(250, sheet="Otra"))
    assert resolve(store, a)["status"] == "lost"


PY1 = "import os\n\n\ndef alpha():\n    return 1\n\n\nclass Box:\n    def beta(self, x):\n        y = x + 1\n        return y\n"
PY2 = "import os\nimport sys\n\n# helper\n\n\ndef gamma():\n    return 0\n\n\ndef alpha():\n    return 1\n\n\nclass Box:\n    def beta(self, x):\n        y = x + 1\n        return y\n"


def test_python_symbol_moves_then_changes_then_is_lost(store, proj):
    f = put(store, proj, "shared/mod.py", PY1)
    a = anchor(store, f, "code", {"symbol": "alpha"})
    b = anchor(store, f, "code", {"symbol": "Box.beta"})
    c = anchor(store, f, "code", {"line_start": 10})
    assert (a["selector"]["line_start"], a["selector"]["line_end"]) == (4, 5) and c["selector"]["symbol"] == "Box.beta"
    rewrite(store, proj, f, "shared/mod.py", PY2)
    ra = resolve(store, a)
    assert ra["status"] == "moved" and ra["location"]["line_start"] == 11 and ra["open"]["symbol"] == "alpha"
    assert resolve(store, b)["status"] == "moved"
    rewrite(store, proj, f, "shared/mod.py", PY2.replace("return 1", "return 2"))
    assert resolve(store, a)["status"] == "changed"
    rewrite(store, proj, f, "shared/mod.py", PY2.replace("def alpha", "def renamed"))
    assert resolve(store, a)["status"] == "lost"


def test_javascript_symbol_by_regex(store, proj):
    f = put(store, proj, "shared/app.js", "const a = 1;\nfunction greet(name) {\n  return 'hi ' + name;\n}\n")
    a = anchor(store, f, "code", {"symbol": "greet"})
    assert (a["selector"]["line_start"], a["selector"]["line_end"]) == (2, 4)
    rewrite(store, proj, f, "shared/app.js", "// c\n// d\nconst a = 1;\nfunction greet(name) {\n  return 'hi ' + name;\n}\n")
    assert resolve(store, a)["status"] == "moved"


def obj(names, shift=0.0):
    out = []
    for i, name in enumerate(names):
        out += [f"o {name}", f"v {i + shift} 0 0", f"v {i + 1 + shift} 0 0", f"v {i} 1 0", f"f {3 * i + 1} {3 * i + 2} {3 * i + 3}"]
    return "\n".join(out) + "\n"


def glb(names):
    doc = {"asset": {"version": "2.0"}, "nodes": [{"name": n, "mesh": 0} for n in names],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
           "accessors": [{"count": 3, "min": [0, 0, 0], "max": [1, 1, 0]}, {"count": 6}]}
    body = json.dumps(doc).encode()
    body += b" " * (-len(body) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(body)) + struct.pack("<II", len(body), 0x4E4F534A) + body


def test_glb_renamed_node_is_lost_and_obj_geometry_change(store, proj):
    f = put(store, proj, "shared/model.glb", glb(["Wheel", "Door"]))
    a = anchor(store, f, "mesh", {"node": "Door", "faces": [0, 1]})
    assert a["selector"]["node_index"] == 1 and a["selector"]["faces"] == [0, 1]
    rewrite(store, proj, f, "shared/model.glb", glb(["Wheel", "Hood"]))
    lost = resolve(store, a)
    assert lost["status"] == "lost" and lost["location"] is None and lost["origin"]["selector"]["node"] == "Door"
    rewrite(store, proj, f, "shared/model.glb", glb(["Door", "Wheel"]))
    assert resolve(store, a)["status"] == "moved"
    g = put(store, proj, "shared/part.obj", obj(["left", "right"]))
    b = anchor(store, g, "mesh", {"node": "right"})
    rewrite(store, proj, g, "shared/part.obj", obj(["left", "right"], shift=0.5))
    assert resolve(store, b)["status"] == "changed"
    with pytest.raises(StoreError):
        anchor(store, g, "mesh", {"node": "nope"})


def test_stl_whole_part(store, proj):
    ascii_stl = "solid cube\nfacet normal 0 0 1\n outer loop\n vertex 0 0 0\n vertex 1 0 0\n vertex 0 1 0\n endloop\nendfacet\nendsolid cube\n"
    f = put(store, proj, "shared/c.stl", ascii_stl)
    a = anchor(store, f, "mesh", {"node": "cube", "faces": [0]})
    rewrite(store, proj, f, "shared/c.stl", ascii_stl.replace("vertex 1 0 0", "vertex 2 0 0"))
    assert resolve(store, a)["status"] == "changed"


def make_pdf(path, pages):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    for lines in pages:
        for x, y, text in lines:
            c.drawString(x, y, text)
        c.showPage()
    c.save()
    return path.read_bytes()


def test_pdf_page_rect_with_text(store, proj, tmp_path):
    pytest.importorskip("reportlab")
    pytest.importorskip("pypdf")
    v1 = make_pdf(tmp_path / "a.pdf", [[(72, 700, "Header line"), (72, 400, "Clause 7: payment in 30 days"), (72, 100, "Footer")]])
    f = put(store, proj, "shared/contract.pdf", v1)
    # Normalised, origin top-left: y=400pt of 792 -> 0.495 from the top.
    a = anchor(store, f, "pdf", {"page": 1, "rect": [0.1, 0.45, 0.8, 0.52]}, label="Clausula 7")
    assert a["status"] == "intact" and a["selector"]["page"] == 1
    same = make_pdf(tmp_path / "b.pdf", [[(72, 700, "Header line"), (72, 400, "Clause 7: payment in 30 days"), (72, 100, "Footer")]])
    rewrite(store, proj, f, "shared/contract.pdf", same)
    assert resolve(store, a)["status"] == "intact"
    # Text pushed down by 100pt and a new first page: the clause moves to page 2.
    v2 = make_pdf(tmp_path / "c.pdf", [[(72, 700, "Cover")], [(72, 700, "Header line"), (72, 300, "Clause 7: payment in 30 days"), (72, 100, "Footer")]])
    rewrite(store, proj, f, "shared/contract.pdf", v2)
    moved = resolve(store, a)
    assert moved["status"] == "moved" and moved["location"]["page"] == 2 and moved["open"]["fragment"] == "page=2"
    assert moved["location"]["rect"][1] > a["selector"]["rect"][1]
    assert resolve(store, a, revision=1)["location"]["page"] == 1
    v3 = make_pdf(tmp_path / "d.pdf", [[(72, 700, "Header line"), (72, 400, "Clause 7: payment in 60 days"), (72, 100, "Footer")]])
    rewrite(store, proj, f, "shared/contract.pdf", v3)
    assert resolve(store, a)["status"] == "changed"
    with pytest.raises(StoreError):
        anchor(store, f, "pdf", {"page": 9, "rect": [0, 0, 1, 1]})
    with pytest.raises(StoreError):
        anchor(store, f, "pdf", {"page": 1, "rect": [0.5, 0.5, 0.2, 0.9]})


def png(w, h):
    import zlib
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def wav(seconds):
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


def test_image_region_and_time_range(store, proj):
    img = put(store, proj, "shared/pic.png", png(8, 4))
    region = anchor(store, img, "image", {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5})
    assert region["selector"]["rect"] == [0.25, 0.25, 0.75, 0.75]
    rewrite(store, proj, img, "shared/pic.png", png(16, 8))
    assert resolve(store, region)["status"] == "changed"
    audio = put(store, proj, "shared/clip.wav", wav(10))
    span = anchor(store, audio, "time", {"start": 2.5, "end": 4})
    assert resolve(store, span)["open"]["fragment"] == "t=2.5,4.0" and resolve(store, span)["open"]["time_start"] == 2.5
    rewrite(store, proj, audio, "shared/clip.wav", wav(12))
    assert resolve(store, span)["status"] == "changed"
    rewrite(store, proj, audio, "shared/clip.wav", wav(2))
    assert resolve(store, span)["status"] == "lost"
    with pytest.raises(StoreError):
        anchor(store, audio, "time", {"start": 99})


def test_list_per_revision_filters_access_and_validation(store, proj):
    f = put(store, proj, "shared/doc.txt", V1)
    a = anchor(store, f, "text", {"quote": "Closing"})
    rewrite(store, proj, f, "shared/doc.txt", V2)
    resolve(store, a)
    listed = store.dispatch("atlas_anchor_list", {"file_id": f["id"]}, "lumiere")
    assert listed["summary"]["moved"] == 1 and [r["seq"] for r in listed["revisions"]] == [1, 2]
    at1 = store.dispatch("atlas_anchor_list", {"file_id": f["id"], "revision": 1}, "lumiere")
    assert at1["anchors"][0]["status"] == "intact" and at1["anchors"][0]["at_revision_seq"] == 1
    assert store.dispatch("atlas_anchor_list", {"project_id": proj["id"], "status": "lost"}, "writer")["total"] == 0
    # An anchor created on r2 does not exist on r1.
    later = anchor(store, f, "text", {"quote": "Intro"})
    assert later["revision_seq"] == 2
    assert store.dispatch("atlas_anchor_list", {"file_id": f["id"], "revision": 1}, "writer")["total"] == 1
    other = store.dispatch("atlas_project_create", {"name": "Otro", "owner": "prospero"})["project"]
    with pytest.raises(StoreError) as denied:
        store.dispatch("atlas_anchor_get", {"anchor_id": a["id"]}, "prospero")
    assert denied.value.status == 403 and other["id"] != proj["id"]
    with pytest.raises(StoreError):
        store.dispatch("atlas_anchor_create", {"file_id": f["id"], "kind": "cell", "selector": {"ref": "A1"}}, "writer")
    with pytest.raises(StoreError):
        store.dispatch("atlas_anchor_create", {"file_id": f["id"], "kind": "text", "selector": {"quote": "Intro"}, "revision": 1}, "writer")
    with pytest.raises(StoreError):
        store.dispatch("atlas_anchor_create", {"file_id": f["id"], "kind": "bogus", "selector": {}}, "writer")
    # Idempotent retries with a request_id.
    args = {"file_id": f["id"], "kind": "text", "selector": {"quote": "Intro"}, "request_id": "r-1"}
    one = store.dispatch("atlas_anchor_create", args, "writer")
    two = store.dispatch("atlas_anchor_create", args, "writer")
    assert one["anchor"]["id"] == two["anchor"]["id"] and two["replayed"]


def test_external_reference_and_revert_history(store, proj, tmp_path):
    src = tmp_path / "outside.txt"
    src.write_text(V1, encoding="utf-8")
    f = store.dispatch("atlas_file_link_source", {"project_id": proj["id"], "source_path": str(src)}, "ui")["file"]
    a = anchor(store, f, "text", {"quote": "lazy dog"})
    src.write_text(V2, encoding="utf-8")
    assert resolve(store, a)["status"] == "moved"
    src.write_text(V1, encoding="utf-8")
    back = resolve(store, a)
    assert back["status"] == "intact" and [h["status"] for h in back["history"]] == ["intact", "moved", "intact"]
    assert back["file"]["input_readonly"] and src.read_text(encoding="utf-8") == V1


def test_existing_files_get_revision_history_on_upgrade(tmp_path):
    first = Workspace(tmp_path / "private", tmp_path / "disk")
    p = first.dispatch("atlas_project_create", {"name": "Viejo", "owner": "writer"})["project"]
    f = put(first, p, "shared/a.txt", "hello world\n")
    first.db.execute("DROP TABLE anchor_status")
    first.db.execute("DROP TABLE anchor_comments")
    first.db.execute("DROP TABLE anchors")
    first.db.execute("DROP TABLE file_revisions")
    first.db.commit()
    first.close()
    second = Workspace(tmp_path / "private", tmp_path / "disk")
    a = second.dispatch("atlas_anchor_create", {"file_id": f["id"], "kind": "text", "selector": {"quote": "world"}}, "writer")["anchor"]
    assert a["revision_seq"] == 1
    second.close()
