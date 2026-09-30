"""The tool catalogue: shape, descriptions, annotations, result cap, and a call to every tool."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from atlas_hoard import agent_tools as at
from atlas_hoard import history as history_mod
from atlas_hoard.errors import AtlasError, NotFound, Refused

REQUIRED = {"atlas_status", "case_create", "case_list", "case_get", "case_update", "source_add", "source_get", "source_retract", "sources_search",
            "entity_upsert", "entity_get", "entity_search", "entity_merge", "duplicates_suggest", "relation_add", "relation_update", "relation_retract",
            "timeline", "map_layers", "graph", "hypothesis_add", "ach_rate", "ach_matrix", "enrich", "enrichment_undo", "case_report", "history"}
from conftest import BANNED_WORDS as BANNED  # noqa: E402


def test_catalogue_has_every_required_tool():
    names = [t.name for t in at.TOOLS]
    assert REQUIRED <= set(names) and len(names) == len(set(names))
    assert "relation_get" in names


def test_descriptions_are_short_first_lines_and_neutral():
    for spec in at.tool_catalog():
        first = spec["description"].splitlines()[0]
        assert 0 < len(first) <= 110, spec["name"]
        assert spec["inputSchema"]["type"] == "object"
        low = (spec["description"] + json.dumps(spec["inputSchema"])).lower()
        assert not any(b in low for b in BANNED), spec["name"]
    assert not any(b in at.AGENT_INSTRUCTIONS.lower() for b in BANNED)


def test_annotations_mark_read_only_and_destructive_tools():
    ann = {t.name: t.annotations for t in at.TOOLS}
    for name in ("atlas_status", "case_list", "case_get", "source_get", "sources_search", "entity_get", "entity_search", "duplicates_suggest", "timeline",
                 "map_layers", "graph", "ach_matrix", "case_report", "history", "relation_get"):
        assert ann[name]["readOnlyHint"] is True, name
    for name in ("case_create", "source_add", "entity_upsert", "relation_add", "relation_update", "relation_retract", "hypothesis_add", "ach_rate", "enrich"):
        assert ann[name]["readOnlyHint"] is False, name
    assert ann["enrich"]["openWorldHint"] is True and ann["timeline"]["openWorldHint"] is False
    for spec in at.tool_catalog():
        assert set(spec["annotations"]) >= {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}


def test_unknown_tool_and_bad_arguments(services):
    with pytest.raises(KeyError):
        at.call_tool(services, "teleport", {})
    with pytest.raises(ValidationError):
        at.call_tool(services, "case_get", {})  # case_id is required
    with pytest.raises(ValidationError):
        at.call_tool(services, "relation_add", {"case_id": 1, "subject": "a", "predicate": "p", "object": "b", "evidence": []})


def test_every_tool_returns_a_dict_and_full_flow(services):
    call = lambda _tool, **a: at.call_tool(services, _tool, a, caller="test")  # noqa: E731
    assert call("atlas_status")["service"] == "atlas-hoard"
    cid = call("case_create", title="Flow", question="Who owns B?", tags=["t"])["case"]["id"]
    assert call("case_list")["items"][0]["id"] == cid
    s1 = call("source_add", case_id=cid, kind="text", text="A owns B according to the register.", origin="reg.example", reliability="B", credibility="2")["source"]["id"]
    s2 = call("source_add", case_id=cid, kind="url", url="https://news.example.com/acme")["source"]["id"]
    assert call("source_get", source_id=s1, max_chars=200)["text"].startswith("A owns")
    assert call("sources_search", case_id=cid, query="register")["items"][0]["id"] == s1
    a = call("entity_upsert", case_id=cid, type="organization", name="A")["entity"]["id"]
    b = call("entity_upsert", case_id=cid, type="organization", name="B", aliases=["Bee"])["entity"]["id"]
    assert call("entity_get", entity_id=a)["name"] == "A"
    assert call("entity_search", case_id=cid, query="Bee")["items"][0]["id"] == b
    rel = call("relation_add", case_id=cid, subject="A", predicate="owns", object="B", valid_from="2020", evidence=[{"source_id": s1, "quote": "A owns B"}])
    rid = rel["relation"]["id"]
    assert call("relation_get", relation_id=rid)["status"] == "claimed"
    call("relation_update", relation_id=rid, add_evidence=[{"source_id": s2, "locator": "para 1"}])
    assert call("relation_get", relation_id=rid)["status"] == "corroborated"
    assert call("duplicates_suggest", case_id=cid)["suggestions"] == []
    assert call("timeline", case_id=cid)["total"] == 1
    assert call("map_layers", case_id=cid)["layers"] == []
    assert len(call("graph", case_id=cid)["nodes"]) == 2
    h1 = call("hypothesis_add", case_id=cid, statement="A controls B")["hypothesis"]["id"]
    h2 = call("hypothesis_add", case_id=cid, statement="B is independent")["hypothesis"]["id"]
    ev = call("ach_matrix", case_id=cid, include_unrated=True)["evidence"][0]["id"]
    assert call("ach_rate", hypothesis_id=h1, evidence_id=ev, rating="CC")["rated"] is True
    call("ach_rate", hypothesis_id=h2, evidence_id=ev, rating="II")
    assert call("ach_matrix", case_id=cid)["least_contradicted"] == [h1]
    assert call("case_get", case_id=cid)["counts"]["relations"] == 1
    assert "A owns B" in call("case_report", case_id=cid, use_model=False)["markdown"]
    events = call("history", case_id=cid)["items"]
    assert {e["caller"] for e in events} == {"test"} and any(e["action"].startswith("relation") for e in events)
    e = call("enrich", enricher="wikidata", case_id=cid, entity_id=a, dry_run=True)
    assert e["status"] in ("dry_run", "not_found", "ambiguous")
    m = call("entity_merge", keep_id=a, merge_id=b)
    assert m["preview"] is True
    call("relation_retract", relation_id=rid, reason="test")
    assert call("relation_get", relation_id=rid)["status"] == "retracted"
    out = call("source_retract", source_id=s1, reason="test")
    assert out["retracted"] is True
    call("case_update", case_id=cid, status="closed")
    for name in ("enrichment_undo",):
        assert name in {t.name for t in at.TOOLS}


def test_tool_results_are_always_json_serialisable(services, case):
    cid = case["case"]["id"]
    for name, args in (("case_get", {"case_id": cid}), ("timeline", {"case_id": cid}), ("graph", {"case_id": cid}), ("map_layers", {"case_id": cid}),
                       ("ach_matrix", {"case_id": cid}), ("case_report", {"case_id": cid, "use_model": False, "format": "json"}),
                       ("history", {"case_id": cid}), ("duplicates_suggest", {"case_id": cid})):
        assert json.dumps(at.call_tool(services, name, args))


def test_agent_results_are_capped_but_ui_results_are_not(services):
    c = at.call_tool(services, "case_create", {"title": "Big"})["case"]
    big = "lorem ipsum dolor sit amet " * 4000
    s = at.call_tool(services, "source_add", {"case_id": c["id"], "kind": "text", "text": big})["source"]
    for i in range(80):
        at.call_tool(services, "source_add", {"case_id": c["id"], "kind": "text", "text": f"distinct source number {i} " + "filler " * 60, "title": f"Source {i} " + "t" * 100})
    raw = at.call_tool(services, "case_report", {"case_id": c["id"], "use_model": False, "format": "json"}, cap=False)
    capped = at.call_tool(services, "case_report", {"case_id": c["id"], "use_model": False, "format": "json"}, cap=True)
    assert len(json.dumps(capped)) <= 21_000 and capped.get("truncated") is True and "hint" in capped
    assert len(json.dumps(raw)) > len(json.dumps(capped))
    page = at.call_tool(services, "source_get", {"source_id": s["id"], "max_chars": 12_000}, cap=True)
    assert len(json.dumps(page)) <= 21_000


def test_history_records_the_caller(services):
    at.call_tool(services, "case_create", {"title": "H"}, caller="agent-x")
    items = history_mod.list_history(services, limit=5)["items"]
    assert items[0]["caller"] == "agent-x" and items[0]["action"].startswith("case")


def test_refusals_surface_as_refused(services):
    c = at.call_tool(services, "case_create", {"title": "R"})["case"]
    with pytest.raises(Refused):
        at.call_tool(services, "source_add", {"case_id": c["id"], "kind": "url", "url": "https://www.facebook.com/someone"})
    bob = at.call_tool(services, "entity_upsert", {"case_id": c["id"], "type": "person", "name": "Bob Smith"})["entity"]
    with pytest.raises(Refused):
        at.call_tool(services, "enrich", {"enricher": "wikidata", "entity_id": bob["id"]})


def test_deletes_need_confirm(services, case):
    with pytest.raises(AtlasError):
        at.call_tool(services, "case_update", {"case_id": case["case"]["id"], "action": "delete"})
    lone = at.call_tool(services, "entity_upsert", {"case_id": case["case"]["id"], "type": "concept", "name": "Loose end"})["entity"]
    with pytest.raises(AtlasError):
        at.call_tool(services, "entity_upsert", {"case_id": case["case"]["id"], "entity_id": lone["id"], "action": "delete"})
    with pytest.raises(AtlasError, match="relation"):  # entities in relations are not deletable
        at.call_tool(services, "entity_upsert", {"case_id": case["case"]["id"], "entity_id": case["jane"]["id"], "action": "delete", "confirm": True})
    out = at.call_tool(services, "entity_upsert", {"case_id": case["case"]["id"], "entity_id": lone["id"], "action": "delete", "confirm": True})
    assert out["deleted"] is True
