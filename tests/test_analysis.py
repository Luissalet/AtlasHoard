"""ACH, map layers, graph, and reports with their citation check."""
from __future__ import annotations

import json

import pytest

from atlas_hoard import ach, cases, entities, relations, reports, sources, timeline
from atlas_hoard.errors import AtlasError, NotFound
from conftest import FakeLink, make_services


@pytest.fixture
def lab(services):
    """One case, three evidence items, two hypotheses."""
    c = cases.create(services, title="Who built it")["case"]
    s = sources.add(services, case_id=c["id"], kind="text", text="Alpha. Beta. Gamma.", origin="x.example", title="Doc")["source"]
    h1 = ach.hypothesis(services, case_id=c["id"], statement="The firm built it")["hypothesis"]
    h2 = ach.hypothesis(services, case_id=c["id"], statement="The city built it")["hypothesis"]
    ids = []
    for q in ("Alpha", "Beta", "Gamma"):
        r = ach.rate(services, hypothesis_id=h1["id"], evidence={"source_id": s["id"], "quote": q}, rating="N")
        ids.append(r["evidence_id"])
    return {"case": c, "source": s, "h1": h1["id"], "h2": h2["id"], "ev": ids}


def rate(svc, lab, h, e, rating):
    return ach.rate(svc, hypothesis_id=lab[h], evidence_id=lab["ev"][e], rating=rating)


# ---------- ACH ----------

def test_scores_penalise_inconsistency_only(services, lab):
    rate(services, lab, "h1", 0, "CC")
    rate(services, lab, "h2", 0, "II")
    rate(services, lab, "h1", 1, "I")
    rate(services, lab, "h2", 1, "C")
    rate(services, lab, "h1", 2, "NA")
    m = ach.matrix(services, lab["case"]["id"])
    score = {h["id"]: h["score"] for h in m["hypotheses"]}
    assert score[lab["h1"]] == 1 and score[lab["h2"]] == 2  # I=1, II=2, consistent and neutral add nothing
    assert m["least_contradicted"] == [lab["h1"]]
    top = [h for h in m["hypotheses"] if h["least_contradicted"]]
    assert [h["id"] for h in top] == [lab["h1"]]


def test_output_never_claims_proof(services, lab):
    rate(services, lab, "h1", 0, "CC")
    rate(services, lab, "h2", 0, "II")
    m = ach.matrix(services, lab["case"]["id"])
    assert "least contradicted so far" in m["note"] and "not proof" in m["note"].lower()
    assert "not proven" in m["disclaimer"].lower()
    for word in ("proven", "proves", "certain", "true hypothesis", "correct hypothesis"):
        assert word not in m["note"].lower()


def test_diagnosticity_and_non_diagnostic_evidence(services, lab):
    rate(services, lab, "h1", 0, "CC")
    rate(services, lab, "h2", 0, "II")  # spread of 4 on the -2..2 scale: fully diagnostic
    rate(services, lab, "h1", 1, "C")
    rate(services, lab, "h2", 1, "C")  # same rating for both: says nothing
    m = ach.matrix(services, lab["case"]["id"])
    diag = {e["id"]: e["diagnosticity"] for e in m["evidence"]}
    assert diag[lab["ev"][0]] == 1.0 and diag[lab["ev"][1]] == 0.0
    assert next(e for e in m["evidence"] if e["id"] == lab["ev"][1])["diagnostic"] is False
    assert "do not discriminate" in m["note"] or "does not discriminate" in m["note"]


def test_pivotal_evidence_is_named(services, lab):
    rate(services, lab, "h1", 0, "I")
    rate(services, lab, "h2", 0, "C")
    rate(services, lab, "h1", 1, "C")
    rate(services, lab, "h2", 1, "II")
    m = ach.matrix(services, lab["case"]["id"])
    # h1: 1, h2: 2 -> h1 leads; removing E1 (h2 II) makes h2 lead 0 vs 1
    assert m["least_contradicted"] == [lab["h1"]]
    assert lab["ev"][1] in m["pivotal_evidence_ids"]
    assert next(e for e in m["evidence"] if e["id"] == lab["ev"][1])["pivotal"] is True
    assert "hinges on" in m["note"]


def test_ties_are_reported_as_ties(services, lab):
    rate(services, lab, "h1", 0, "C")
    rate(services, lab, "h2", 0, "C")
    m = ach.matrix(services, lab["case"]["id"])
    assert sorted(m["least_contradicted"]) == sorted([lab["h1"], lab["h2"]]) and "tied" in m["note"]


def test_no_hypotheses_or_ratings_notes(services):
    c = cases.create(services, title="Empty")["case"]
    assert "add at least two" in ach.matrix(services, c["id"])["note"].lower()
    ach.hypothesis(services, case_id=c["id"], statement="Only one")
    ach.hypothesis(services, case_id=c["id"], statement="Second")
    assert "no ratings" in ach.matrix(services, c["id"])["note"].lower()


def test_retracted_source_evidence_is_inactive_and_ignored(services, lab):
    rate(services, lab, "h1", 0, "II")
    rate(services, lab, "h2", 0, "C")
    before = {h["id"]: h["score"] for h in ach.matrix(services, lab["case"]["id"])["hypotheses"]}
    assert before[lab["h1"]] == 2
    out = sources.retract(services, lab["source"]["id"], reason="forged")
    assert lab["h1"] in out["affected"]["ach"]["hypotheses_affected"]
    m = ach.matrix(services, lab["case"]["id"])
    assert {h["id"]: h["score"] for h in m["hypotheses"]}[lab["h1"]] == 0
    assert all(e["active"] is False for e in m["evidence"])
    assert all(r["inactive"] for r in m["ratings"])  # the ratings stay on file, greyed out


def test_rating_validation_and_delete(services, lab):
    with pytest.raises(AtlasError):
        rate(services, lab, "h1", 0, "maybe")
    rate(services, lab, "h1", 0, "C")
    assert any(r["hypothesis_id"] == lab["h1"] and r["evidence_id"] == lab["ev"][0] for r in ach.matrix(services, lab["case"]["id"])["ratings"])
    ach.rate(services, hypothesis_id=lab["h1"], evidence_id=lab["ev"][0], action="delete")
    assert not any(r["hypothesis_id"] == lab["h1"] and r["evidence_id"] == lab["ev"][0] and r["rating"] == "C"
                   for r in ach.matrix(services, lab["case"]["id"])["ratings"])
    with pytest.raises(AtlasError):
        ach.rate(services, hypothesis_id=lab["h1"])  # needs evidence_id or evidence
    other = cases.create(services, title="Other")["case"]
    foreign = sources.add(services, case_id=other["id"], kind="text", text="foreign text")["source"]
    with pytest.raises(AtlasError):
        ach.rate(services, hypothesis_id=lab["h1"], evidence={"source_id": foreign["id"], "quote": "foreign"}, rating="C")


def test_discarded_hypotheses_leave_the_ranking(services, lab):
    rate(services, lab, "h1", 0, "II")
    rate(services, lab, "h2", 0, "C")
    ach.hypothesis(services, hypothesis_id=lab["h2"], status="discarded")
    m = ach.matrix(services, lab["case"]["id"])
    row = next(h for h in m["hypotheses"] if h["id"] == lab["h2"])
    assert row["score"] is None and row["rank"] is None and row["status"] == "discarded"
    with pytest.raises(AtlasError):
        ach.hypothesis(services, hypothesis_id=lab["h2"], action="delete")  # confirm needed
    assert ach.hypothesis(services, hypothesis_id=lab["h2"], action="delete", confirm=True)


# ---------- map and graph ----------

def test_map_layers_by_type_with_sources_and_unplaced(services, case):
    cid = case["case"]["id"]
    entities.upsert(services, case_id=cid, type="place", name="Lyon", lat=45.76, lon=4.83, date_start="1990")
    entities.upsert(services, case_id=cid, type="place", name="Nowhere-yet")
    m = timeline.map_layers(services, cid)
    [layer] = [l for l in m["layers"] if l["type"] == "place"]
    assert layer["count"] == 2 and {f["name"] for f in layer["features"]} == {"Paris", "Lyon"}
    paris = next(f for f in layer["features"] if f["name"] == "Paris")
    assert paris["source_count"] == 2 and layer["source_count"] >= 2
    assert any(u["name"] == "Nowhere-yet" for u in m["unplaced"])
    assert "OpenStreetMap" in m["attribution"]
    assert m["time_range"]["from"] is not None


def test_map_as_of_and_type_filter(services, case):
    cid = case["case"]["id"]
    entities.upsert(services, case_id=cid, type="event", name="Old fair", lat=45.0, lon=5.0, date_start="1990")
    entities.upsert(services, case_id=cid, type="event", name="Future fair", lat=46.0, lon=6.0, date_start="2040")
    names = lambda m: {f["name"] for l in m["layers"] for f in l["features"]}  # noqa: E731
    assert "Future fair" in names(timeline.map_layers(services, cid))
    assert "Future fair" not in names(timeline.map_layers(services, cid, as_of="2000"))
    assert [l["type"] for l in timeline.map_layers(services, cid, types=["event"])["layers"]] == ["event"]


def test_graph_nodes_edges_and_neighbourhood(services, case):
    cid = case["case"]["id"]
    g = timeline.graph(services, cid)
    assert {n["name"] for n in g["nodes"]} == {"Acme Corp", "Paris", "Jane Doe"}
    by_pred = {e["predicate"]: e for e in g["edges"]}
    assert by_pred["headquartered_in"]["status"] == "corroborated" and by_pred["ceo_of"]["status"] == "claimed"
    assert set(g["status_legend"]) >= {"claimed", "corroborated", "confirmed", "disputed", "unsupported", "retracted"}
    far = entities.upsert(services, case_id=cid, type="place", name="Far", lat=1, lon=1)["entity"]
    s = case["s1"]
    relations.add(services, case_id=cid, subject=case["paris"]["id"], predicate="located_in", object=far["id"], evidence=[{"source_id": s["id"], "locator": "x"}])
    one = timeline.graph(services, cid, entity_id=case["jane"]["id"], depth=1)
    two = timeline.graph(services, cid, entity_id=case["jane"]["id"], depth=2)
    three = timeline.graph(services, cid, entity_id=case["jane"]["id"], depth=3)
    assert {n["name"] for n in one["nodes"]} == {"Jane Doe", "Acme Corp"}
    assert {n["name"] for n in two["nodes"]} == {"Jane Doe", "Acme Corp", "Paris"} and "Far" in {n["name"] for n in three["nodes"]}
    assert next(n for n in one["nodes"] if n["center"])["name"] == "Jane Doe"
    with pytest.raises(AtlasError):
        timeline.graph(services, cid, depth=9)


def test_graph_status_filter_and_retracted(services, case):
    cid = case["case"]["id"]
    only = timeline.graph(services, cid, statuses=["corroborated"])
    assert [e["predicate"] for e in only["edges"]] == ["headquartered_in"]
    relations.retract(services, case["r2"]["id"], reason="x")
    assert "ceo_of" not in [e["predicate"] for e in timeline.graph(services, cid)["edges"]]
    assert "ceo_of" in [e["predicate"] for e in timeline.graph(services, cid, include_retracted=True)["edges"]]


def test_graph_truncation(services):
    c = cases.create(services, title="Big")["case"]
    s = sources.add(services, case_id=c["id"], kind="text", text="hub and spokes")["source"]
    hub = entities.upsert(services, case_id=c["id"], type="organization", name="Hub")["entity"]
    for i in range(12):
        e = entities.upsert(services, case_id=c["id"], type="organization", name=f"Spoke {i}")["entity"]
        relations.add(services, case_id=c["id"], subject=hub["id"], predicate="owns", object=e["id"], evidence=[{"source_id": s["id"], "locator": str(i)}])
    g = timeline.graph(services, c["id"], max_nodes=5)
    assert g["truncated"] is True and len(g["nodes"]) == 5 and any(n["name"] == "Hub" for n in g["nodes"])


# ---------- reports ----------

def test_split_and_cite_helpers():
    assert reports.cited_ids("Acme is in Paris [S1][S2]. Also [S12].") == [1, 2, 12]
    parts = reports.split_sentences("First claim here [S1]. Second claim without a citation. Third [S2].")
    assert len(parts) == 3


def test_citation_check_flags_uncited_invalid_and_retracted(services, case):
    cid = case["case"]["id"]
    ok = reports.check_citations(services, cid, "Acme Corp moved its headquarters to Paris [S1]. The firm is now in Paris [S2].")
    assert ok["ok"] and ok["uncited"] == [] and ok["cited"] == ok["claims"] == 2
    bad = reports.check_citations(services, cid, "Acme Corp is in Paris [S1]. Jane Doe runs the company without any source. It employs 200 people [S99].")
    assert not bad["ok"] and bad["invalid_citations"] == [99] and any("Jane Doe" in s for s in bad["uncited"])
    sources.retract(services, case["s2"]["id"], reason="x")
    ret = reports.check_citations(services, cid, "Acme is based in Paris [S2].")
    assert ret["retracted_citations"] == [2]


def test_report_markdown_has_sections_quotes_and_citations(services, case):
    r = reports.report(services, case["case"]["id"], format="markdown", lang="en", use_model=False)
    md = r["markdown"]
    assert r["summary_source"] == "deterministic" and r["citation_check"]["ok"]
    assert "Acme Corp headquartered in Paris" in md and "[S1]" in md and "[S2]" in md
    assert "Press release" in md and "Acme Corp moved its headquarters" in md
    assert r["total_chars"] >= len(md) and r["next_offset"] is None


def test_report_uses_model_summary_only_when_cited(tmp_path):
    from atlas_hoard import entities as _e
    link = FakeLink(chat_text="Acme Corp is headquartered in Paris [S1]. It was founded by aliens [S1].")
    svc = make_services(tmp_path, link=link)
    svc.start()
    try:
        c = cases.create(svc, title="R")["case"]
        s = sources.add(svc, case_id=c["id"], kind="text", text="Acme Corp moved its headquarters to Paris.", origin="a.example")["source"]
        a = _e.upsert(svc, case_id=c["id"], type="organization", name="Acme Corp")["entity"]
        p = _e.upsert(svc, case_id=c["id"], type="place", name="Paris")["entity"]
        relations.add(svc, case_id=c["id"], subject=a["id"], predicate="headquartered_in", object=p["id"], evidence=[{"source_id": s["id"], "quote": "headquarters to Paris"}])
        r = reports.report(svc, c["id"], format="json", lang="en", use_model=True)
        assert r["summary_source"] == "model" and r["report"]["summary"]["text"].startswith("Acme Corp is headquartered")
        assert link.chat_calls and "Acme Corp headquartered in Paris" in link.chat_calls[0][0][0]["content"]
        assert r["citation_check"]["ok"]  # both sentences carry a valid id (whether the claim is true is for a human to check)
    finally:
        svc.stop()


def test_report_falls_back_when_model_unavailable_or_uncited(tmp_path):
    svc = make_services(tmp_path, link=FakeLink(available=False))
    svc.start()
    try:
        c = cases.create(svc, title="R")["case"]
        s = sources.add(svc, case_id=c["id"], kind="text", text="Acme Corp is in Paris.", origin="a.example")["source"]
        a = entities.upsert(svc, case_id=c["id"], type="organization", name="Acme Corp")["entity"]
        p = entities.upsert(svc, case_id=c["id"], type="place", name="Paris")["entity"]
        relations.add(svc, case_id=c["id"], subject=a["id"], predicate="headquartered_in", object=p["id"], evidence=[{"source_id": s["id"], "quote": "in Paris"}])
        r = reports.report(svc, c["id"], use_model=True)
        assert r["summary_source"] == "deterministic" and "no model" in r["model_note"]
        svc.link_sync = FakeLink(chat_text="Acme rules the world with no citation at all.")
        r2 = reports.report(svc, c["id"], use_model=True)
        assert r2["citation_check"]["ok"] is False and r2["citation_check"]["uncited"]
        assert "⚠" in r2["markdown"]  # uncited sentences are visibly marked in the report
    finally:
        svc.stop()


def test_report_json_sections_paging_and_language(services, case):
    cid = case["case"]["id"]
    sec = reports.report(services, cid, format="json", section="relations", use_model=False)
    assert sec["section"] == "relations" and "corroborated" in sec["relations"]
    with pytest.raises(ValueError):
        reports.report(services, cid, format="json", section="nope", use_model=False)
    full = reports.report(services, cid, format="markdown", use_model=False, max_chars=200)
    assert len(full["markdown"]) == 200 and full["next_offset"] == 200
    es = reports.report(services, cid, format="markdown", lang="es", use_model=False)
    en = reports.report(services, cid, format="markdown", lang="en", use_model=False)
    assert es["lang"] == "es" and es["markdown"] != en["markdown"]
    assert json.dumps(reports.report(services, cid, format="json", use_model=False))  # serialisable


def test_report_separates_ended_from_stale(services):
    c = cases.create(services, title="Historia")["case"]
    s = sources.add(services, case_id=c["id"], kind="text", text="The bridge was built between 1881 and 1889.", origin="h.example", published_at="1999-01-01")["source"]
    a = entities.upsert(services, case_id=c["id"], type="organization", name="Builders")["entity"]
    b = entities.upsert(services, case_id=c["id"], type="place", name="Bridge")["entity"]
    relations.add(services, case_id=c["id"], subject=a["id"], predicate="built", object=b["id"], valid_from="1881", valid_to="1889", observed_at="1999-01-01",
                  evidence=[{"source_id": s["id"], "quote": "built between 1881 and 1889"}])
    es = reports.report(services, c["id"], lang="es", use_model=False)["markdown"]
    en = reports.report(services, c["id"], lang="en", use_model=False)["markdown"]
    assert "terminado" in es and "desactualizado" not in es and "ended" in en and "stale" not in en
    g = timeline.graph(services, c["id"])
    assert g["edges"][0]["ended"] is True and g["edges"][0]["stale"] is False
    tl = timeline.timeline(services, c["id"])
    assert all(e["stale"] is False for e in tl["entries"] if e["kind"] != "event")


def test_status_does_not_block_on_a_slow_model_probe(tmp_path):
    import time
    from conftest import FakeLink, make_services

    class Slow(FakeLink):
        calls = 0

        def status(self):
            Slow.calls += 1
            time.sleep(2.0)
            return super().status()

    svc = make_services(tmp_path, link=Slow())
    svc.start()
    try:
        t0 = time.monotonic()
        first = svc.status()
        assert time.monotonic() - t0 < 1.5 and first["model"]["state"] == "probing"
        time.sleep(2.3)  # the probe finishes in the background and fills the cache
        t0 = time.monotonic()
        second = svc.status()
        assert time.monotonic() - t0 < 0.2 and second["model"]["llm"]["state"] == "resolved"
        svc.status()
        assert Slow.calls == 1  # cached for 60 s
    finally:
        svc.stop()
