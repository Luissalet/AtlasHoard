"""Entities (private rule, duplicates, merge) and relations (evidence, derived status, cascade, dates)."""
from __future__ import annotations

import pytest

from atlas_hoard import cases, entities, relations, sources, timeline
from atlas_hoard.errors import AtlasError, NotFound


@pytest.fixture
def c(services):
    return cases.create(services, title="Case")["case"]


def src(svc, c, text, origin, **kw):
    return sources.add(svc, case_id=c["id"], kind="text", text=text, origin=origin, title=kw.pop("title", text[:30]), **kw)["source"]


def ent(svc, c, name, type_="organization", **kw):
    return entities.upsert(svc, case_id=c["id"], type=type_, name=name, **kw)["entity"]


# ---------- entities ----------

def test_person_is_private_unless_public_figure(services, c):
    assert ent(services, c, "Bob Smith", "person")["private_person"] is True
    assert ent(services, c, "Jane Doe", "person", public_figure=True)["private_person"] is False
    assert ent(services, c, "Acme", "organization")["private_person"] is False
    bob = entities.upsert(services, case_id=c["id"], name="Bob Smith", type="person", public_figure=True)["entity"]
    assert bob["private_person"] is False  # flipping the flag is a deliberate, recorded act


def test_upsert_matches_name_and_type_and_aliases(services, c):
    a = ent(services, c, "Acme Corp", aliases=["Acme"])
    again = entities.upsert(services, case_id=c["id"], type="organization", name="acme corp", description="Maker of anvils")
    assert again["created"] is False and again["entity"]["id"] == a["id"] and again["entity"]["description"] == "Maker of anvils"
    assert entities.resolve(services, c["id"], "Acme")["id"] == a["id"]
    with pytest.raises(NotFound):
        entities.resolve(services, c["id"], "Nobody")


def test_same_name_different_type_is_a_different_entity(services, c):
    a = ent(services, c, "Mercury", "place")
    b = ent(services, c, "Mercury", "concept")
    assert a["id"] != b["id"]


def test_attributes_keep_per_attribute_sources(services, c):
    s = src(services, c, "Acme was founded in 1949.", "a.example")
    e = ent(services, c, "Acme", attributes={"founded": {"value": "1949", "source_id": s["id"], "quote": "founded in 1949"}, "motto": "Anvils!"})
    attrs = entities.get(services, e["id"])["attributes"]
    assert attrs["founded"]["value"] == "1949" and attrs["founded"]["source_ids"] == [s["id"]]
    assert attrs["motto"].get("source_ids", []) == []  # stored, but flagged as unsourced
    sources.retract(services, s["id"], reason="wrong")
    after = entities.get(services, e["id"])["attributes"]["founded"]
    assert after["value"] == "1949"  # never deleted, only reported


def test_entity_validation(services, c):
    with pytest.raises(AtlasError):
        entities.upsert(services, case_id=c["id"], type="spaceship", name="X")
    with pytest.raises(AtlasError):
        entities.upsert(services, case_id=c["id"], type="place", name="P", lat=123, lon=0)
    with pytest.raises(AtlasError):
        entities.upsert(services, case_id=c["id"], type="event", name="E", date_start="not-a-date")


def test_entity_search_uses_fts_and_type(services, c):
    ent(services, c, "Borealis Industries", aliases=["Borealis"])
    ent(services, c, "Paris", "place")
    names = [x["name"] for x in entities.search(services, query="boreal", case_id=c["id"])["items"]]
    assert names == ["Borealis Industries"]
    assert [x["name"] for x in entities.search(services, case_id=c["id"], type="place")["items"]] == ["Paris"]


def test_duplicates_are_suggested_never_merged(services, c):
    a = ent(services, c, "Acme Corporation")
    b = ent(services, c, "ACME", aliases=["Acme Corporation"])
    ent(services, c, "Zenith Labs")
    ent(services, c, "Acme Corporation", "place")  # other type: never a candidate
    dups = entities.suggest_duplicates(services, c["id"])["suggestions"]
    pair = [d for d in dups if {d["a"]["id"], d["b"]["id"]} == {a["id"], b["id"]}]
    assert pair and pair[0]["reasons"][0]["kind"] == "alias_overlap"
    assert len(dups) == 1
    assert entities.get(services, a["id"])["merged_into"] is None
    assert entities.get(services, b["id"])["merged_into"] is None


def test_merge_previews_then_moves_everything(services, c):
    s1, s2 = src(services, c, "Acme HQ is Paris", "a.example"), src(services, c, "Acme Corp HQ Paris", "b.example")
    keep, gone = ent(services, c, "Acme Corporation"), ent(services, c, "Acme Corp.", aliases=["ACME"])
    paris = ent(services, c, "Paris", "place")
    r1 = relations.add(services, case_id=c["id"], subject=keep["id"], predicate="headquartered_in", object=paris["id"], valid_from="2024",
                       evidence=[{"source_id": s1["id"], "locator": "p1"}])["relation"]
    r2 = relations.add(services, case_id=c["id"], subject=gone["id"], predicate="headquartered_in", object=paris["id"], valid_from="2024",
                       evidence=[{"source_id": s2["id"], "locator": "p1"}])["relation"]
    preview = entities.merge(services, keep["id"], gone["id"])
    assert preview.get("preview", True) and entities.get(services, gone["id"])["merged_into"] is None
    assert preview["relations_moved"] >= 1
    entities.merge(services, keep["id"], gone["id"], confirm=True)
    assert entities.get(services, gone["id"])["merged_into"] == keep["id"]
    merged = entities.get(services, keep["id"])
    assert "ACME" in merged["aliases"] or "Acme Corp." in merged["aliases"]
    # the two identical relations collapse into one that now has two independent origins
    live = relations.list_views(services, c["id"], statuses=["claimed", "corroborated"])
    assert len(live) == 1 and live[0]["status"] == "corroborated" and live[0]["independent_sources"] == 2
    with pytest.raises(AtlasError):
        entities.merge(services, keep["id"], keep["id"], confirm=True)


def test_delete_entity_needs_confirm(services, c):
    e = ent(services, c, "Gone Inc")
    with pytest.raises(AtlasError):
        entities.delete(services, e["id"], confirm=False)
    entities.delete(services, e["id"], confirm=True)
    with pytest.raises(NotFound):
        entities.get(services, e["id"])


# ---------- relations ----------

def test_relation_needs_evidence_and_a_real_source(services, case):
    base = dict(case_id=case["case"]["id"], subject=case["acme"]["id"], predicate="founded_by", object=case["jane"]["id"])
    with pytest.raises(AtlasError):
        relations.add(services, evidence=[], **base)
    with pytest.raises(AtlasError):
        relations.add(services, evidence=[{"source_id": case["s1"]["id"]}], **base)  # no quote and no locator
    with pytest.raises((AtlasError, NotFound)):
        relations.add(services, evidence=[{"source_id": 9999, "quote": "x"}], **base)


def test_evidence_must_belong_to_the_same_case(services, case):
    other = cases.create(services, title="Other")["case"]
    foreign = sources.add(services, case_id=other["id"], kind="text", text="elsewhere")["source"]
    with pytest.raises(AtlasError):
        relations.add(services, case_id=case["case"]["id"], subject=case["acme"]["id"], predicate="owns", object=case["paris"]["id"],
                      evidence=[{"source_id": foreign["id"], "quote": "elsewhere"}])


def test_status_is_derived_from_independent_origins(services, c):
    a, b = ent(services, c, "A"), ent(services, c, "B")
    s1 = src(services, c, "A owns B according to one.", "one.example")
    s2 = src(services, c, "A owns B according to two.", "two.example")
    same = src(services, c, "A owns B, syndicated copy.", "one.example")
    rel = relations.add(services, case_id=c["id"], subject=a["id"], predicate="owns", object=b["id"], evidence=[{"source_id": s1["id"], "quote": "A owns B"}])["relation"]
    assert rel["status"] == "claimed" and rel["independent_sources"] == 1
    relations.update(services, rel["id"], add_evidence=[{"source_id": same["id"], "quote": "A owns B"}])
    v = relations.get(services, rel["id"])
    assert v["evidence_count"] == 2 and v["independent_sources"] == 1 and v["status"] == "claimed"  # same origin counts once
    relations.update(services, rel["id"], add_evidence=[{"source_id": s2["id"], "quote": "A owns B"}])
    assert relations.get(services, rel["id"])["status"] == "corroborated"


def test_identical_content_counts_once_even_from_different_origins(services, c):
    a, b = ent(services, c, "A"), ent(services, c, "B")
    s1 = src(services, c, "A controls B.", "one.example")
    s2 = src(services, c, "A controls B.", "two.example")  # same content hash
    rel = relations.add(services, case_id=c["id"], subject=a["id"], predicate="controls", object=b["id"],
                        evidence=[{"source_id": s1["id"], "quote": "A controls B"}, {"source_id": s2["id"], "quote": "A controls B"}])["relation"]
    assert rel["independent_sources"] == 1 and rel["status"] == "claimed"


def test_confirm_needs_two_origins_and_dispute_is_manual(services, case):
    with pytest.raises(AtlasError, match="independent"):
        relations.update(services, case["r2"]["id"], status="confirmed")
    relations.update(services, case["r1"]["id"], status="confirmed")
    assert relations.get(services, case["r1"]["id"])["status"] == "confirmed"
    relations.update(services, case["r1"]["id"], status="disputed", reason="sources disagree")
    v = relations.get(services, case["r1"]["id"])
    assert v["status"] == "disputed" and v["manual_reason"] == "sources disagree"
    relations.update(services, case["r1"]["id"], status="clear")  # clear the manual flag
    assert relations.get(services, case["r1"]["id"])["status"] == "corroborated"


def test_retract_is_sticky_until_restored(services, case):
    relations.retract(services, case["r1"]["id"], reason="mistaken")
    assert relations.get(services, case["r1"]["id"])["status"] == "retracted"
    sources.add(services, source_id=case["s1"]["id"], reliability="A")  # unrelated change does not revive it
    assert relations.get(services, case["r1"]["id"])["status"] == "retracted"
    relations.retract(services, case["r1"]["id"], action="restore")
    assert relations.get(services, case["r1"]["id"])["status"] == "corroborated"


def test_same_triple_and_dates_merges_evidence(services, case):
    s3 = src(services, case["case"], "Acme HQ Paris third", "third.example")
    again = relations.add(services, case_id=case["case"]["id"], subject=case["acme"]["id"], predicate="headquartered_in", object=case["paris"]["id"],
                          valid_from="2024", evidence=[{"source_id": s3["id"], "quote": "Acme HQ Paris"}])
    assert again["merged_into_existing"] is True and again["relation"]["id"] == case["r1"]["id"]
    assert again["relation"]["evidence_count"] == 3


def test_predicates_are_normalised_and_free(services, case):
    r = relations.add(services, case_id=case["case"]["id"], subject=case["jane"]["id"], predicate="Is Friend Of", object=case["acme"]["id"],
                      evidence=[{"source_id": case["s1"]["id"], "locator": "p3"}])["relation"]
    assert r["predicate"] == "is_friend_of" and r["in_vocabulary"] is False


def test_symmetric_predicates_match_either_way(services, c):
    a, b = ent(services, c, "A"), ent(services, c, "B")
    s = src(services, c, "A and B are partners", "x.example")
    relations.predicate_upsert(services, "partner_of", symmetric=True)
    one = relations.add(services, case_id=c["id"], subject=a["id"], predicate="partner_of", object=b["id"], evidence=[{"source_id": s["id"], "locator": "1"}])
    two = relations.add(services, case_id=c["id"], subject=b["id"], predicate="partner_of", object=a["id"], evidence=[{"source_id": s["id"], "locator": "2"}])
    assert two["merged_into_existing"] and two["relation"]["id"] == one["relation"]["id"]


def test_quote_verification_against_stored_text(services, case):
    s = case["s1"]
    r = relations.add(services, case_id=case["case"]["id"], subject=case["jane"]["id"], predicate="works_for", object=case["acme"]["id"],
                      evidence=[{"source_id": s["id"], "quote": "Acme Corp moved its headquarters"}, {"source_id": s["id"], "quote": "never said this"}])
    verdicts = {e["quote"]: e["quote_in_source"] for e in relations.get(services, r["relation"]["id"])["evidence"]}
    assert verdicts["Acme Corp moved its headquarters"] is True and verdicts["never said this"] is False


def test_unsupported_when_every_source_is_retracted_and_derived_flags(services, c):
    a, b, d = ent(services, c, "A"), ent(services, c, "B"), ent(services, c, "D")
    s1, s2 = src(services, c, "A owns B", "one.example"), src(services, c, "B owns D", "two.example")
    base = relations.add(services, case_id=c["id"], subject=a["id"], predicate="owns", object=b["id"], evidence=[{"source_id": s1["id"], "quote": "A owns B"}])["relation"]
    derived = relations.add(services, case_id=c["id"], subject=a["id"], predicate="controls", object=d["id"], derived_from=[base["id"]],
                            evidence=[{"source_id": s2["id"], "quote": "B owns D"}])["relation"]
    assert relations.get(services, derived["id"])["flags"] == []
    out = sources.retract(services, s1["id"], reason="forged")
    assert relations.get(services, base["id"])["status"] == "unsupported"
    assert [x["relation_id"] for x in out["affected"]["derived_flagged"]] == [derived["id"]]
    assert relations.get(services, derived["id"])["status"] == "claimed"  # still has its own evidence, but flagged
    assert relations.get(services, derived["id"])["flags"]


def test_update_can_move_dates_and_clear_them(services, case):
    relations.update(services, case["r1"]["id"], valid_to="2030")
    v = relations.get(services, case["r1"]["id"])
    assert (v["valid_from"], v["valid_to"]) == ("2024", "2030")
    relations.update(services, case["r1"]["id"], clear_dates=["valid_to"])
    assert relations.get(services, case["r1"]["id"])["valid_to"] is None
    with pytest.raises(AtlasError):
        relations.update(services, case["r1"]["id"], valid_from="2031", valid_to="2020")


def test_staleness(services, c):
    a, b = ent(services, c, "A"), ent(services, c, "B")
    s = src(services, c, "A is at B", "x.example", published_at="2019-01-01")
    old = relations.add(services, case_id=c["id"], subject=a["id"], predicate="located_in", object=b["id"], observed_at="2019-01-01",
                        evidence=[{"source_id": s["id"], "locator": "1"}])["relation"]
    assert relations.get(services, old["id"])["stale"] is True and relations.get(services, old["id"])["stale_reason"]
    ended = relations.add(services, case_id=c["id"], subject=b["id"], predicate="located_in", object=a["id"], valid_to="2020", observed_at="2026-09-01",
                          evidence=[{"source_id": s["id"], "locator": "2"}])["relation"]
    v = relations.get(services, ended["id"])
    assert v["ended"] is True and v["stale"] is False and v["current"] is False  # history is not staleness
    old_history = relations.add(services, case_id=c["id"], subject=a["id"], predicate="owns", object=b["id"], valid_from="1881", valid_to="1889",
                                observed_at="2001-01-01", evidence=[{"source_id": s["id"], "locator": "h"}])["relation"]
    v = relations.get(services, old_history["id"])
    assert v["ended"] is True and v["stale"] is False  # built 1881-1889, observed long ago: still not stale
    future = relations.add(services, case_id=c["id"], subject=b["id"], predicate="owns", object=a["id"], valid_to="2040", observed_at="2015-01-01",
                           evidence=[{"source_id": s["id"], "locator": "f"}])["relation"]
    v = relations.get(services, future["id"])
    assert v["ended"] is False and v["stale"] is True  # meant to be current, never refreshed
    dash = cases.get(services, c["id"])["dashboard"]["stale_facts"]
    assert {x["id"] for x in dash} == {old["id"], future["id"]}
    recent = relations.add(services, case_id=c["id"], subject=a["id"], predicate="owns", object=b["id"], observed_at="2026-09-01",
                           evidence=[{"source_id": s["id"], "locator": "3"}])["relation"]
    assert relations.get(services, recent["id"])["stale"] is False


def test_delete_relation_needs_confirm(services, case):
    with pytest.raises(AtlasError):
        relations.delete(services, case["r2"]["id"], confirm=False)
    relations.delete(services, case["r2"]["id"], confirm=True)
    with pytest.raises(NotFound):
        relations.get(services, case["r2"]["id"])


def test_functional_predicate_conflict_and_timeline_gaps(services, c):
    acme, paris, lyon = ent(services, c, "Acme"), ent(services, c, "Paris", "place"), ent(services, c, "Lyon", "place")
    s1, s2 = src(services, c, "HQ Paris", "a.example"), src(services, c, "HQ Lyon", "b.example")
    relations.add(services, case_id=c["id"], subject=acme["id"], predicate="headquartered_in", object=paris["id"], valid_from="2000", valid_to="2010",
                  evidence=[{"source_id": s1["id"], "locator": "1"}])
    relations.add(services, case_id=c["id"], subject=acme["id"], predicate="headquartered_in", object=lyon["id"], valid_from="2008", valid_to="2012",
                  evidence=[{"source_id": s2["id"], "locator": "1"}])
    conflicts = [k for k in timeline.contradictions(services, c["id"]) if k["kind"] == "functional_conflict"]
    assert len(conflicts) == 1 and "Acme" in conflicts[0]["note"]
    relations.add(services, case_id=c["id"], subject=acme["id"], predicate="founded_in", object=paris["id"], valid_from="1950", evidence=[{"source_id": s1["id"], "locator": "2"}])
    tl = timeline.timeline(services, c["id"], gap_days=365)
    assert any(g["days"] > 365 for g in tl["gaps"])
    assert [e["date"] for e in tl["entries"]] == sorted((e["date"] for e in tl["entries"]))
    lyon_only = timeline.timeline(services, c["id"], as_of="2011")
    active = [e["label"] for e in lyon_only["entries"] if e.get("active_at_as_of")]
    assert any("Lyon" in x for x in active) and not any("Paris" in x and "headquartered" in x for x in active)


def test_attribute_keys_cannot_carry_the_privacy_switch(services, c):
    for key in ("public_figure", "Private Person", "private-person"):
        with pytest.raises(AtlasError, match="public_figure=true"):
            entities.upsert(services, case_id=c["id"], type="person", name="X Y", attributes={key: True})
    ok = entities.upsert(services, case_id=c["id"], type="person", name="X Y", public_figure=True)["entity"]
    assert ok["private_person"] is False and "public_figure" not in ok["attributes"]
