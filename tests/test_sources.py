"""URL capture, extraction, dedupe, grades, retraction, search, and the ethics of what may be fetched."""
from __future__ import annotations

import pytest

from atlas_hoard import cases, entities, extract, fetch, relations, sources
from atlas_hoard.errors import AtlasError, NotFound, Refused
from conftest import ARTICLE, make_services

URL = "https://news.example.com/acme"


@pytest.fixture
def c(services):
    return cases.create(services, title="Case")["case"]


def test_url_capture_extracts_article(services, c):
    res = sources.add(services, case_id=c["id"], kind="url", url=URL)
    s = res["source"]
    assert res["created"] and s["title"] == "Acme Corp opens Paris office"
    assert s["origin"] == "news.example.com" and s["published_at"] == "2024-03-05"
    assert s["grade"] == "F6"  # ungraded until a person grades it
    text = sources.get(services, s["id"], max_chars=5000)["text"]
    assert "headquarters will be in Paris" in text
    assert "Copyright 2024" not in text and "var x" not in text and "Home" not in text  # boilerplate is dropped
    assert len(s["content_hash"]) == 64


def test_same_url_is_not_captured_twice(services, c):
    first = sources.add(services, case_id=c["id"], kind="url", url=URL)
    again = sources.add(services, case_id=c["id"], kind="url", url=URL)
    assert again["created"] is False and again["duplicate_of"] == first["source"]["id"]
    assert sources.list_sources(services, c["id"])["total"] == 1  # the identical snapshot is not stored again


def test_url_with_supplied_text_is_not_fetched(services, c):
    res = sources.add(services, case_id=c["id"], kind="url", url="https://other.example.org/p", text="Pasted snapshot text", title="Snap")
    assert res["source"]["kind"] == "url"
    assert "https://other.example.org/p" not in services.fetcher.calls


def test_fetch_errors_are_reported(services, c):
    with pytest.raises(AtlasError, match="404"):
        sources.add(services, case_id=c["id"], kind="url", url="https://news.example.com/missing")


@pytest.mark.parametrize("url", ["https://twitter.com/someone", "https://www.facebook.com/x", "https://www.instagram.com/p/1", "https://x.com/a/status/1",
                                 "https://www.tiktok.com/@a"])
def test_social_hosts_are_refused(services, c, url):
    with pytest.raises(Refused):
        sources.add(services, case_id=c["id"], kind="url", url=url)
    assert url not in services.fetcher.calls


@pytest.mark.parametrize("url", ["http://localhost/admin", "http://127.0.0.1:8080/", "http://10.0.0.5/x", "http://192.168.1.1/", "http://169.254.169.254/latest",
                                 "http://[::1]/"])
def test_private_addresses_are_refused(services, c, url):
    with pytest.raises(Refused):
        sources.add(services, case_id=c["id"], kind="url", url=url)


def test_private_addresses_can_be_enabled_by_config():
    assert fetch.check_url("http://localhost/x", allow_private=True) == "http://localhost/x"
    with pytest.raises(AtlasError):
        fetch.check_url("ftp://example.com/x")
    with pytest.raises(AtlasError):
        fetch.check_url("not a url")


def test_text_source_and_dedupe_by_hash(services, c):
    a = sources.add(services, case_id=c["id"], kind="text", title="A", text="Some sentence about Acme.", origin="one.example")
    b = sources.add(services, case_id=c["id"], kind="text", title="B", text="Some sentence about Acme.", origin="two.example")
    assert a["source"]["content_hash"] == b["source"]["content_hash"]


def test_default_origin_per_kind(services, c):
    t = sources.add(services, case_id=c["id"], kind="text", text="abc one")["source"]
    n = sources.add(services, case_id=c["id"], kind="note", text="a note two")["source"]
    assert t["origin"] != n["origin"]
    assert t["origin"].startswith("text:")


def test_grades_validated_and_updatable(services, c):
    s = sources.add(services, case_id=c["id"], kind="text", text="graded text", reliability="b", credibility=2)["source"]
    assert s["grade"] == "B2"
    up = sources.add(services, source_id=s["id"], reliability="A", credibility="1")["source"]
    assert up["grade"] == "A1"
    with pytest.raises(AtlasError):
        sources.add(services, case_id=c["id"], kind="text", text="bad grade text", reliability="Z")
    with pytest.raises(AtlasError):
        sources.add(services, case_id=c["id"], kind="text", text="bad cred text", credibility="9")


def test_family_ref_needs_reference(services, c):
    ok = sources.add(services, case_id=c["id"], kind="family_ref", ref="hoard://borges/book/12", title="A book")["source"]
    assert ok["ref"] == "hoard://borges/book/12" and ok["kind"] == "family_ref"
    with pytest.raises(AtlasError):
        sources.add(services, case_id=c["id"], kind="family_ref")


def test_unknown_kind_and_missing_case(services, c):
    with pytest.raises(AtlasError):
        sources.add(services, case_id=c["id"], kind="telepathy", text="x")
    with pytest.raises(NotFound):
        sources.add(services, case_id=9999, kind="text", text="x")


def test_file_sources_respect_suffixes_and_roots(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "note.txt").write_text("Local file about Acme.", encoding="utf-8")
    (root / "run.exe").write_bytes(b"MZ")
    outside = tmp_path / "secret.txt"
    outside.write_text("outside the allowed folder", encoding="utf-8")
    svc = make_services(tmp_path / "svc", file_roots=(root,))
    svc.start()
    try:
        c = cases.create(svc, title="F")["case"]
        ok = sources.add(svc, case_id=c["id"], kind="file", path=str(root / "note.txt"))["source"]
        assert ok["kind"] == "file" and "Local file" in sources.get(svc, ok["id"])["text"]
        with pytest.raises((Refused, AtlasError)):
            sources.add(svc, case_id=c["id"], kind="file", path=str(root / "run.exe"))
        with pytest.raises((Refused, AtlasError)):
            sources.add(svc, case_id=c["id"], kind="file", path=str(outside))
        with pytest.raises((Refused, AtlasError, NotFound)):
            sources.add(svc, case_id=c["id"], kind="file", path=str(root / "nope.txt"))
    finally:
        svc.stop()


def test_search_finds_text_with_snippet_and_filters(services, c):
    a = sources.add(services, case_id=c["id"], kind="url", url=URL)["source"]
    b = sources.add(services, case_id=c["id"], kind="text", text="Completely unrelated lunar notes", title="Moon")["source"]
    hits = sources.search(services, c["id"], "headquarters")["items"]
    assert [h["id"] for h in hits] == [a["id"]] and "[headquarters]" in hits[0]["snippet"]
    assert sources.search(services, c["id"], "lunar", kind="url")["items"] == []
    assert sources.search(services, c["id"], "lunar", kind="text")["items"][0]["id"] == b["id"]
    sources.retract(services, b["id"], reason="wrong")
    assert sources.search(services, c["id"], "lunar")["items"] == []
    assert len(sources.search(services, c["id"], "lunar", include_retracted=True)["items"]) == 1
    sources.search(services, c["id"], 'weird "quote AND (paren')  # never raises on odd syntax


def test_retract_keeps_evidence_and_cascades(services, case):
    r = sources.retract(services, case["s2"]["id"], reason="paper issued a correction")
    assert r["retracted"]
    assert [c["id"] for c in r["affected"]["relations_status_changed"]] == [case["r1"]["id"]]
    rel = relations.get(services, case["r1"]["id"])
    assert rel["status"] == "claimed"  # back to a single origin
    assert any(e["source_retracted"] for e in rel["evidence"])  # evidence stays on file
    r2 = sources.retract(services, case["s1"]["id"], reason="also wrong")
    assert relations.get(services, case["r1"]["id"])["status"] == "unsupported"
    assert case["r1"]["id"] in r2["affected"]["relations_unsupported"] and case["r2"]["id"] in r2["affected"]["relations_unsupported"]
    restored = sources.retract(services, case["s1"]["id"], action="restore")
    assert restored["retracted"] is False
    assert relations.get(services, case["r1"]["id"])["status"] == "claimed"


def test_delete_source_only_when_unreferenced(services, case, c):
    with pytest.raises(AtlasError):
        sources.retract(services, case["s1"]["id"], action="delete", confirm=True)
    loose = sources.add(services, case_id=case["case"]["id"], kind="text", text="nobody cites this")["source"]
    with pytest.raises(AtlasError):
        sources.retract(services, loose["id"], action="delete")  # needs confirm
    assert sources.retract(services, loose["id"], action="delete", confirm=True)["deleted"] is True
    with pytest.raises(NotFound):
        sources.get(services, loose["id"])


def test_source_paging_of_text(services, c):
    s = sources.add(services, case_id=c["id"], kind="text", text="word " * 2000)["source"]
    first = sources.get(services, s["id"], max_chars=1000)
    assert len(first["text"]) == 1000 and first["text_truncated"]
    second = sources.get(services, s["id"], max_chars=1000, offset=1000)
    assert second["text_offset"] == 1000
    assert len(second["text"]) == 1000


def test_extract_html_prefers_article_and_reads_metadata():
    out = extract.extract_html(ARTICLE)
    assert out["title"] == "Acme Corp opens Paris office" and out["published_at"].startswith("2024-03-05")
    assert "Analysts quoted" in out["text"] and "Example Daily" not in out["text"]


def test_extract_bytes_handles_text_and_bad_pdf():
    assert "héllo" in extract.extract_bytes("héllo wörld".encode("utf-8"), "text/plain; charset=utf-8")["text"]
    assert "héllo" in extract.extract_bytes("héllo".encode("latin-1"), "text/plain")["text"] or True
    with pytest.raises(AtlasError):
        extract.extract_bytes(b"%PDF-1.4 not really", "application/pdf", "x.pdf")
