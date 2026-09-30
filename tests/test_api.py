"""REST routes (the UI's side of the same tools), agent auth, PWA, SPA fallback, events, manifest and the bridge."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest

from atlas_hoard import SERVICE, __version__
from atlas_hoard.agent_tools import TOOLS
from atlas_hoard.config import DEFAULT_PORT
from conftest import BANNED_WORDS

ROOT = Path(__file__).resolve().parent.parent
URL = "https://news.example.com/acme"


def seeded(client):
    c = client.post("/api/cases", json={"title": "API case", "question": "Q?"}).json()["case"]
    cid = c["id"]
    s1 = client.post(f"/api/cases/{cid}/sources", json={"kind": "text", "text": "Acme owns Borealis.", "origin": "one.example", "title": "One"}).json()["source"]
    s2 = client.post(f"/api/cases/{cid}/sources", json={"kind": "url", "url": URL}).json()["source"]
    client.post(f"/api/cases/{cid}/entities", json={"type": "organization", "name": "Acme"})
    client.post(f"/api/cases/{cid}/entities", json={"type": "place", "name": "Paris", "lat": 48.85, "lon": 2.35})
    r = client.post(f"/api/cases/{cid}/relations", json={"subject": "Acme", "predicate": "headquartered_in", "object": "Paris", "valid_from": "2024",
                                                          "evidence": [{"source_id": s1["id"], "quote": "Acme owns"}, {"source_id": s2["id"], "locator": "p1"}]})
    return {"cid": cid, "s1": s1["id"], "s2": s2["id"], "rid": r.json()["relation"]["id"]}


def test_health_and_status(client):
    h = client.get("/api/health").json()
    assert h["service"] == SERVICE == "atlas-hoard" and h["version"] == __version__ and "counts" in h and "hoard_link" in h
    assert client.get("/api/status").status_code == 200


def test_cases_crud_over_rest(client):
    c = client.post("/api/cases", json={"title": "T", "tags": ["a"]})
    assert c.status_code == 201 and c.json()["case"]["ref"] == f"hoard://atlas/case/{c.json()['case']['id']}"
    cid = c.json()["case"]["id"]
    assert client.get("/api/cases").json()["items"][0]["id"] == cid
    got = client.get(f"/api/cases/{cid}").json()
    assert got["counts"]["sources"] == 0 and "dashboard" in got
    assert client.put(f"/api/cases/{cid}", json={"status": "paused", "open_questions": ["Who?"]}).json()["case"]["status"] == "paused"
    assert client.put(f"/api/cases/{cid}", json={"status": "weird"}).status_code in (400, 422)
    assert client.delete(f"/api/cases/{cid}").status_code == 400  # confirm required
    assert client.delete(f"/api/cases/{cid}", params={"confirm": "true"}).status_code == 200
    assert client.get(f"/api/cases/{cid}").status_code == 404


def test_full_rest_flow(client):
    ids = seeded(client)
    cid = ids["cid"]
    assert client.get(f"/api/cases/{cid}/sources").json()["total"] == 2
    assert client.get(f"/api/cases/{cid}/sources/search", params={"q": "headquarters"}).json()["items"][0]["id"] == ids["s2"]
    assert client.get(f"/api/sources/{ids['s1']}", params={"max_chars": 200}).json()["text"].startswith("Acme")
    assert len(client.get(f"/api/cases/{cid}/entities").json()["items"]) == 2
    rel = client.get(f"/api/relations/{ids['rid']}").json()
    assert rel["status"] == "corroborated" and rel["independent_sources"] == 2
    assert client.get(f"/api/cases/{cid}/relations", params={"status": "corroborated"}).json()["items"][0]["id"] == ids["rid"]
    assert client.get("/api/predicates").json()["items"]
    tl = client.get(f"/api/cases/{cid}/timeline", params={"as_of": "2025"}).json()
    assert tl["total"] >= 1
    assert client.get(f"/api/cases/{cid}/map").json()["layers"][0]["features"][0]["name"] == "Paris"
    g = client.get(f"/api/cases/{cid}/graph", params={"status": "corroborated"}).json()
    assert len(g["edges"]) == 1
    assert client.get(f"/api/cases/{cid}/evidence").json()["items"]
    h = client.post(f"/api/cases/{cid}/hypotheses", json={"statement": "H one"}).json()["hypothesis"]["id"]
    client.post(f"/api/cases/{cid}/hypotheses", json={"statement": "H two"})
    ev = client.get(f"/api/cases/{cid}/ach", params={"include_unrated": "true"}).json()["evidence"][0]["id"]
    assert client.put("/api/ach", json={"hypothesis_id": h, "evidence_id": ev, "rating": "CC"}).json()["rated"] is True
    rep = client.get(f"/api/cases/{cid}/report", params={"lang": "en", "use_model": "false"}).json()
    assert "Acme" in rep["markdown"] and rep["citation_check"]["ok"]
    raw = client.get(f"/api/cases/{cid}/report", params={"raw": "true", "use_model": "false"})
    assert raw.headers["content-type"].startswith("text/markdown") and "attachment" in raw.headers["content-disposition"]
    hist = client.get(f"/api/cases/{cid}/history").json()
    assert hist["items"] and {i["caller"] for i in hist["items"]} == {"ui"}


def test_ui_errors_map_to_http_codes(client):
    assert client.get("/api/cases/999").status_code == 404
    assert client.get("/api/relations/999").status_code == 404
    ids = seeded(client)
    bad = client.post(f"/api/cases/{ids['cid']}/relations", json={"subject": "Acme", "predicate": "owns", "object": "Paris", "evidence": []})
    assert bad.status_code in (400, 422)
    social = client.post(f"/api/cases/{ids['cid']}/sources", json={"kind": "url", "url": "https://twitter.com/x"})
    assert social.status_code == 403 and "error" in social.json()
    assert client.post(f"/api/cases/{ids['cid']}/relations", json={"subject": "Nobody", "predicate": "owns", "object": "Paris",
                                                                   "evidence": [{"source_id": ids["s1"], "quote": "x"}]}).status_code == 404


def test_retract_and_enrich_over_rest(client):
    ids = seeded(client)
    cid = ids["cid"]
    out = client.post(f"/api/sources/{ids['s1']}/retract", json={"reason": "wrong"}).json()
    assert out["retracted"] and client.get(f"/api/relations/{ids['rid']}").json()["status"] == "claimed"
    acme = client.get(f"/api/cases/{cid}/entities", params={"q": "Acme"}).json()["items"][0]["id"]
    run = client.post(f"/api/cases/{cid}/enrich", json={"enricher": "wikidata", "entity_id": acme, "qid": "Q100"}).json()
    assert run["status"] == "ok" and run["run_id"]
    assert client.get(f"/api/cases/{cid}/enrichment").json()["items"][0]["id"] == run["run_id"]
    assert client.post(f"/api/enrichment/{run['run_id']}/undo").json()["undone"] is True
    bob = client.post(f"/api/cases/{cid}/entities", json={"type": "person", "name": "Bob Smith"}).json()["entity"]
    assert client.post(f"/api/cases/{cid}/enrich", json={"enricher": "wikidata", "entity_id": bob["id"]}).status_code == 403


def test_settings_over_rest(client):
    s = client.get("/api/settings").json()
    assert s["geocode"]["enabled"] is True and s["family_sources"] == ["borges", "links"] and s["stale_days"] == 730
    out = client.put("/api/settings", json={"geocode_enabled": False, "family_sources": ["borges"], "family_tools": {"borges": "library_search"}}).json()
    assert out["geocode"]["enabled"] is False and out["family_sources"] == ["borges"]
    assert client.put("/api/settings", json={"family_sources": [""]}).status_code == 400


# ---------- agent bridge endpoints ----------

def test_agent_tools_listing_is_public_and_matches_catalogue(client):
    body = client.get("/api/agent/tools").json()
    assert {t["name"] for t in body["tools"]} == {t.name for t in TOOLS} and body["instructions"]


def test_agent_call_requires_the_token(client):
    payload = {"name": "atlas_status", "arguments": {}}
    assert client.post("/api/agent/call", json=payload).status_code == 401
    assert client.post("/api/agent/call", json=payload, headers={"Authorization": "Bearer nope"}).status_code == 401
    ok = client.post("/api/agent/call", json=payload, headers={"Authorization": f"Bearer {client.svc.token}"})
    assert ok.status_code == 200 and ok.json()["service"] == "atlas-hoard"


def test_agent_call_errors_and_caller(client):
    auth = {"Authorization": f"Bearer {client.svc.token}"}
    call = lambda name, args=None, caller=None: client.post("/api/agent/call", json={"name": name, "arguments": args or {}, "caller": caller}, headers=auth)  # noqa: E731
    assert call("nope").status_code == 404
    assert call("case_get", {}).status_code == 400
    assert call("case_get", {"case_id": 99}).status_code == 404
    cid = call("case_create", {"title": "Agent case"}, caller="my-agent").json()["case"]["id"]
    assert call("source_add", {"case_id": cid, "kind": "url", "url": "https://www.instagram.com/x"}).status_code == 403
    items = call("history", {"case_id": cid}).json()["items"]
    assert items[0]["caller"] == "agent" or items[0]["caller"] == "my-agent"


def test_token_is_persistent_and_private(tmp_path):
    from atlas_hoard.services import write_token
    from conftest import make_config
    cfg = make_config(tmp_path)
    first = write_token(cfg)
    assert len(first) == 64 and write_token(cfg) == first
    assert cfg.token_path.read_text(encoding="utf-8").strip() == first


# ---------- PWA, SPA, events ----------

def test_pwa_manifest_and_service_worker(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["name"] == "Atlas's Hoard" and m["short_name"] == "Atlas" and m["start_url"] == "/" and m["display"] == "standalone"
    assert {"192x192", "512x512"} <= {i["sizes"] for i in m["icons"]}
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and sw.headers["content-type"].startswith("application/javascript") and sw.headers["service-worker-allowed"] == "/"
    assert "skipWaiting" in sw.text and "clients.claim" in sw.text and "/api/" in sw.text and "/assets/" in sw.text


def test_spa_is_served_with_fallback_but_api_404s_stay_json(client):
    home = client.get("/")
    assert home.status_code == 200 and "text/html" in home.headers["content-type"] and "Atlas" in home.text
    assert client.get("/case/1/graph").status_code == 200  # deep links fall back to the app shell
    missing = client.get("/api/nothing-here")
    assert missing.status_code == 404 and missing.headers["content-type"].startswith("application/json")
    assert client.get("/icon-192.png").headers["content-type"] == "image/png"


def test_built_ui_has_no_raw_html_injection_and_default_language_es():
    html = (ROOT / "atlas_hoard" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'lang="es"' in html and "<title>Atlas's Hoard</title>" in html
    for js in (ROOT / "client" / "src").rglob("*.jsx"):
        assert "dangerouslySetInnerHTML" not in js.read_text(encoding="utf-8"), js.name


def test_events_are_emitted_for_the_hub(client):
    ids = seeded(client)
    client.post(f"/api/sources/{ids['s1']}/retract", json={"reason": "x"})
    types = client.svc._emit.__self__.types() if hasattr(client.svc._emit, "__self__") else [t for t, _ in client.svc._emit.events]
    assert "atlas.case.created" in types and "atlas.relation.added" in types
    assert "atlas.source.retracted" in types and "atlas.relation.status_changed" in types
    payload = dict(next(d for t, d in client.svc._emit.events if t == "atlas.case.created"))
    assert payload["ref"].startswith("hoard://atlas/case/")


# ---------- manifest of the plugin ----------

def test_plugin_manifest_matches_code_and_uses_only_template_keys():
    manifest = json.loads((ROOT / "faustus-plugin.json").read_text(encoding="utf-8"))
    assert set(manifest) <= {"schema", "id", "name", "purpose", "capabilities", "placeholders", "defaults", "app", "mcp", "notes"}
    assert manifest["id"] == "atlas" and manifest["name"] == "Atlas's Hoard"
    assert manifest["app"]["health"]["expect"]["service"] == SERVICE
    assert manifest["app"]["url_default"].endswith(f":{DEFAULT_PORT}")
    assert manifest["app"]["launch_hint"]["env"]["PORT_STRICT"] == "1"
    text = json.dumps(manifest).lower()
    for banned in BANNED_WORDS:
        assert banned not in text


def test_readmes_document_every_tool_and_no_slogans():
    readme = (ROOT / "README.md").read_text(encoding="utf-8") + (ROOT / "README.es.md").read_text(encoding="utf-8")
    for tool in TOOLS:
        assert f"`{tool.name}`" in readme, tool.name
    assert "## Responsible use" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Uso responsable" in (ROOT / "README.es.md").read_text(encoding="utf-8")


def test_no_other_product_names_in_the_repository():
    banned = re.compile("|".join(re.escape(w) for w in BANNED_WORDS), re.I)
    skip = {"node_modules", ".git", "venv", ".venv", "data", "static", "__pycache__", "dist-icons", ".pytest_cache", "hoard_link"}  # hoard_link is the shared library, vendored unchanged
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in (".png", ".ico", ".lock", ".pyc", ".db") or path.name == "package-lock.json":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if banned.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


# ---------- the stdio bridge ----------

def test_bridge_lists_the_app_catalogue_and_proxies_calls(monkeypatch, client):
    sys.path.insert(0, str(ROOT))
    import httpx
    import mcp_server

    catalog = client.get("/api/agent/tools").json()
    bridge = mcp_server.AtlasBridge(catalog["tools"], catalog["instructions"])
    listed = asyncio.run(bridge.list_tools())
    assert {t.name for t in listed} == {t.name for t in TOOLS}
    assert all(t.annotations is not None for t in listed)

    monkeypatch.setenv("ATLAS_TOKEN", client.svc.token)

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            r = client.post(url.replace(mcp_server.BASE_URL, ""), json=json, headers=headers)
            return r

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    out = asyncio.run(bridge.call_tool("case_create", {"title": "Via bridge"}))
    assert json.loads(out[0].text)["case"]["title"] == "Via bridge"
    err = asyncio.run(bridge.call_tool("case_get", {"case_id": 12345}))
    assert "error" in json.loads(err[0].text)
    assert mcp_server._token() == client.svc.token


def test_bridge_refuses_non_local_urls():
    sys.path.insert(0, str(ROOT))
    import mcp_server
    with pytest.raises(SystemExit):
        mcp_server._check_local("http://evil.example:5193")
    mcp_server._check_local("http://127.0.0.1:5193")
