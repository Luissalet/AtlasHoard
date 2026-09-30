"""Enrichers run against fakes; every run is undoable exactly; private persons are never sent anywhere."""
from __future__ import annotations

import pytest

from atlas_hoard import cases, enrich, entities, relations, sources
from atlas_hoard.config import Config
from atlas_hoard.enrichers import geocode as geocode_mod
from atlas_hoard.errors import AtlasError, Refused
from atlas_hoard.services import Services
from conftest import ARTICLE, FakeFamily, FakeFetcher, FakeGeocoder, FakeLink, FakeWikidata, Recorder, T0, make_services

URL = "https://news.example.com/acme"


def snapshot(svc, case_id):
    tables = ("sources", "entities", "relations", "evidence")
    data = {t: [dict(r) for r in svc.db.query(f"SELECT * FROM {t} WHERE case_id = ? ORDER BY id", (case_id,))] for t in tables}
    return data


@pytest.fixture
def c(services):
    return cases.create(services, title="Case")["case"]


def test_unknown_enricher_and_missing_target(services, c):
    with pytest.raises(AtlasError):
        enrich.run(services, case_id=c["id"], enricher="crystal_ball")
    with pytest.raises(AtlasError):
        enrich.run(services, enricher="wikidata")


def test_wikidata_dry_run_writes_nothing(services, c):
    e = entities.upsert(services, case_id=c["id"], type="organization", name="Acme Corp")["entity"]
    before = snapshot(services, c["id"])
    res = enrich.run(services, enricher="wikidata", entity_id=e["id"], dry_run=True)
    assert res["status"] == "dry_run" and res["run_id"] is None and res["planned"]
    assert snapshot(services, c["id"]) == before
    assert enrich.list_runs(services, c["id"])["items"] == []


def test_wikidata_run_creates_claimed_sourced_facts_and_undo_is_exact(services, c):
    e = entities.upsert(services, case_id=c["id"], type="organization", name="Acme Corp", description="mine")["entity"]
    before = snapshot(services, c["id"])
    res = enrich.run(services, enricher="wikidata", entity_id=e["id"])
    assert res["status"] == "ok" and res["qid"] == "Q100" and res["run_id"]
    rels = relations.list_views(services, c["id"], with_evidence=True)
    assert {r["predicate"] for r in rels} == {"headquartered_in", "ceo_of"}
    assert all(r["status"] == "claimed" and r["evidence"] for r in rels)  # one Wikidata source: never corroborated by itself
    src = sources.get(services, res["source_id"])
    assert src["origin"] == "www.wikidata.org" or "wikidata" in src["origin"]
    assert src["grade"] == "C3"
    got = entities.get(services, e["id"])
    assert got["wikidata_qid"] == "Q100" and got["description"] == "mine"  # an existing description is not overwritten
    assert "website" in got["attributes"] and got["attributes"]["website"]["source_ids"] == [res["source_id"]]
    # undo restores the exact previous state
    out = enrich.undo(services, res["run_id"])
    assert out["undone"] and sorted(out["removed"]["relations"]) == sorted(res["relations_added"])
    after = snapshot(services, c["id"])
    assert [r["id"] for r in after["relations"]] == [] and [r["id"] for r in after["sources"]] == []
    assert [r["id"] for r in after["entities"]] == [r["id"] for r in before["entities"]]
    restored = entities.get(services, e["id"])
    assert restored["wikidata_qid"] == "" and restored["attributes"] == {} and restored["description"] == "mine"
    assert enrich.list_runs(services, c["id"])["items"][0]["undone_ts"] is not None
    with pytest.raises(AtlasError):
        enrich.undo(services, res["run_id"])  # already undone


def test_undo_keeps_what_was_edited_afterwards(services, c):
    e = entities.upsert(services, case_id=c["id"], type="organization", name="Acme Corp")["entity"]
    res = enrich.run(services, enricher="wikidata", entity_id=e["id"])
    entities.upsert(services, case_id=c["id"], entity_id=e["id"], description="edited by hand")
    entities.upsert(services, case_id=c["id"], entity_id=e["id"], attributes={"website": "https://changed.example"})
    enrich.undo(services, res["run_id"])
    now = entities.get(services, e["id"])
    assert now["description"] == "edited by hand"  # only restored when still equal to what the run wrote
    assert now["attributes"]["website"]["value"] == "https://changed.example"


def test_undo_keeps_relations_that_gained_other_evidence(services, c):
    e = entities.upsert(services, case_id=c["id"], type="organization", name="Acme Corp")["entity"]
    res = enrich.run(services, enricher="wikidata", entity_id=e["id"])
    hq = [r for r in relations.list_views(services, c["id"]) if r["predicate"] == "headquartered_in"][0]
    mine = sources.add(services, case_id=c["id"], kind="text", text="Acme is headquartered in Paris.", origin="mine.example")["source"]
    relations.update(services, hq["id"], add_evidence=[{"source_id": mine["id"], "quote": "headquartered in Paris"}])
    out = enrich.undo(services, res["run_id"])
    assert hq["id"] in out["kept"]["relations"]
    assert relations.get(services, hq["id"])["evidence_count"] == 1


def test_wikidata_refuses_to_guess_between_candidates(services, c):
    e = entities.upsert(services, case_id=c["id"], type="place", name="Springfield")["entity"]
    res = enrich.run(services, enricher="wikidata", entity_id=e["id"])
    assert res["status"] == "ambiguous" and len(res["candidates"]) == 2 and res["run_id"] is None
    assert relations.list_views(services, c["id"]) == []


def test_wikidata_with_explicit_qid_and_not_found(services, c):
    e = entities.upsert(services, case_id=c["id"], type="event", name="Landing")["entity"]
    res = enrich.run(services, enricher="wikidata", entity_id=e["id"], qid="Q500")
    assert res["status"] == "ok" and entities.get(services, e["id"])["date_start"] == "1969-07-20"
    ghost = entities.upsert(services, case_id=c["id"], type="organization", name="Nonexistent Holdings")["entity"]
    assert enrich.run(services, enricher="wikidata", entity_id=ghost["id"])["status"] == "not_found"


def test_private_person_is_refused_by_every_enricher(services, c):
    bob = entities.upsert(services, case_id=c["id"], type="person", name="Bob Smith")["entity"]
    assert bob["private_person"]
    for name in ("wikidata", "geocode", "family_search"):
        with pytest.raises(Refused):
            enrich.run(services, enricher=name, entity_id=bob["id"])
    assert services.wikidata.calls == [] and services.geocoder.inner.calls == [] and services.fake_family.calls == []
    assert enrich.list_runs(services, c["id"])["items"] == []


def test_person_enrichment_needs_public_figure(services, c):
    jane = entities.upsert(services, case_id=c["id"], type="person", name="Jane Doe", public_figure=True)["entity"]
    res = enrich.run(services, enricher="wikidata", entity_id=jane["id"])
    assert res["status"] == "not_found"  # allowed to run; the fake simply has no such person
    hidden = entities.upsert(services, case_id=c["id"], type="person", name="Not Public")["entity"]
    with pytest.raises(Refused):
        enrich.run(services, enricher="wikidata", entity_id=hidden["id"], qid="Q777")


def test_geocode_sets_coordinates_with_source_and_undoes(services, c):
    p = entities.upsert(services, case_id=c["id"], type="place", name="Paris")["entity"]
    res = enrich.run(services, enricher="geocode", entity_id=p["id"])
    got = entities.get(services, p["id"])
    assert (got["lat"], got["lon"]) == (48.8566, 2.3522) and got["geo_precision"] == "locality"
    assert res["alternatives"] and "Texas" in res["alternatives"][0]["display_name"]  # ambiguity is shown, not hidden
    assert "Nominatim" in sources.get(services, res["source_id"])["title"] or "OpenStreetMap" in sources.get(services, res["source_id"])["title"]
    enrich.undo(services, res["run_id"])
    back = entities.get(services, p["id"])
    assert back["lat"] is None and back["lon"] is None


def test_geocode_does_not_overwrite_without_flag_and_respects_switches(services, c):
    p = entities.upsert(services, case_id=c["id"], type="place", name="Paris", lat=1.0, lon=2.0)["entity"]
    res = enrich.run(services, enricher="geocode", entity_id=p["id"])
    assert res["status"] in ("skipped", "has_coordinates") or res.get("run_id") is None
    assert entities.get(services, p["id"])["lat"] == 1.0
    enrich.run(services, enricher="geocode", entity_id=p["id"], overwrite=True)
    assert entities.get(services, p["id"])["lat"] == 48.8566
    services.update_settings({"geocode_enabled": False})
    q = entities.upsert(services, case_id=c["id"], type="place", name="Lyon")["entity"]
    n = len(services.geocoder.inner.calls)
    res = enrich.run(services, enricher="geocode", entity_id=q["id"])
    assert res["status"] == "disabled" and len(services.geocoder.inner.calls) == n


def test_geocode_only_for_places_events_orgs(services, c):
    d = entities.upsert(services, case_id=c["id"], type="concept", name="Justice")["entity"]
    with pytest.raises(Refused):
        enrich.run(services, enricher="geocode", entity_id=d["id"])


def test_cached_geocoder_hits_the_network_once(tmp_path):
    svc = make_services(tmp_path)
    svc.start()
    try:
        inner = FakeGeocoder()
        cached = geocode_mod.CachedGeocoder(svc.db, inner)
        assert cached.lookup("Paris")[0]["lat"] == 48.8566
        assert cached.lookup("  paris ")[0]["lat"] == 48.8566
        assert inner.calls == ["Paris"]
        assert svc.db.one("SELECT COUNT(*) c FROM geocode_cache")["c"] == 1
    finally:
        svc.stop()


def test_url_capture_enricher_is_undoable(services, c):
    res = enrich.run(services, enricher="url_capture", case_id=c["id"], url=URL, reliability="B", credibility="2")
    assert res["status"] == "ok" and sources.get(services, res["source_id"])["grade"] == "B2"
    dup = enrich.run(services, enricher="url_capture", case_id=c["id"], url=URL)
    assert dup["status"] == "duplicate"
    enrich.undo(services, res["run_id"])
    assert sources.list_sources(services, c["id"])["total"] == 0
    with pytest.raises(Refused):
        enrich.run(services, enricher="url_capture", case_id=c["id"], url="https://twitter.com/x")


def test_failed_run_rolls_itself_back(services, c):
    class Boom(FakeWikidata):
        def fetch(self, qid, *, language="en"):
            raise RuntimeError("wikidata is down")
    services.wikidata = Boom()
    e = entities.upsert(services, case_id=c["id"], type="organization", name="Acme Corp")["entity"]
    before = snapshot(services, c["id"])
    with pytest.raises(RuntimeError):
        enrich.run(services, enricher="wikidata", entity_id=e["id"])
    assert snapshot(services, c["id"]) == before
    runs = services.db.query("SELECT status FROM enrichment_runs")
    assert [r["status"] for r in runs] == ["error"]


def test_family_search_keeps_references_and_degrades_per_app(tmp_path):
    family = {"borges": {"ok": True, "app": "borges", "tool": "library_search", "status": 200,
                         "result": {"items": [{"id": "12", "title": "Acme: a history", "snippet": "Acme was founded in 1949 in Lyon."}]}},
              "links": RuntimeError("links exploded")}
    svc = make_services(tmp_path, family_apps=family)
    svc.start()
    try:
        c = cases.create(svc, title="F")["case"]
        res = enrich.run(svc, enricher="family_search", case_id=c["id"], query="Acme")
        assert res["apps"]["borges"]["status"] == "ok" and res["apps"]["links"]["status"] == "unavailable"
        [ref] = sources.list_sources(svc, c["id"])["items"]
        assert ref["kind"] == "family_ref" and ref["ref"] == "hoard://borges/document/12" and ref["origin"] == ref["ref"]
        assert svc.fake_family.calls[0][:2] == ("borges", "library_search")
        again = enrich.run(svc, enricher="family_search", case_id=c["id"], query="Acme")
        assert again["sources_added"] == [] and again["apps"]["borges"]["already_present"]
    finally:
        svc.stop()


def test_family_search_reports_when_nothing_is_reachable(services, c):
    res = enrich.run(services, enricher="family_search", case_id=c["id"], query="Acme")
    assert res["status"] == "unavailable" and res["run_id"] is None


def test_family_search_redacts_private_names(tmp_path):
    svc = make_services(tmp_path, family_apps={"borges": {"ok": True, "result": {"items": []}}, "links": {"ok": True, "result": []}})
    svc.start()
    try:
        c = cases.create(svc, title="F")["case"]
        entities.upsert(svc, case_id=c["id"], type="person", name="Bob Smith", aliases=["Bobby"])
        res = enrich.run(svc, enricher="family_search", case_id=c["id"], query="contract between Acme and Bob Smith")
        assert "bob smith" not in svc.fake_family.calls[0][2]["q"].lower() and "bob smith" in " ".join(res["redacted"]).lower()
        enrich.run(svc, enricher="family_search", case_id=c["id"], query="Bob Smith", include_private=True)
        assert any("bob smith" in call[2]["q"].lower() for call in svc.fake_family.calls)
        with pytest.raises(Refused):
            enrich.run(svc, enricher="family_search", case_id=c["id"], query="Bobby")  # nothing is left after redaction
    finally:
        svc.stop()
