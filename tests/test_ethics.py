"""The ethics guard in code: private persons, redaction, merges, and what settings may change."""
from __future__ import annotations

import pytest

from atlas_hoard import cases, entities, ethics, reports, relations, sources
from atlas_hoard.errors import AtlasError, Refused


@pytest.fixture
def c(services):
    return cases.create(services, title="Ethics")["case"]


def test_check_enrichable_rules(services, c):
    row = lambda e: services.db.one("SELECT * FROM entities WHERE id = ?", (e["id"],))  # noqa: E731
    org = entities.upsert(services, case_id=c["id"], type="organization", name="Acme")["entity"]
    person = entities.upsert(services, case_id=c["id"], type="person", name="Bob Smith")["entity"]
    figure = entities.upsert(services, case_id=c["id"], type="person", name="Jane Doe", public_figure=True)["entity"]
    doc = entities.upsert(services, case_id=c["id"], type="document", name="A report")["entity"]
    ethics.check_enrichable(row(org), "wikidata")
    ethics.check_enrichable(row(figure), "wikidata")
    ethics.check_enrichable(None, "family_search")
    for enricher in ("wikidata", "geocode", "family_search", "url_capture"):
        with pytest.raises(Refused):
            ethics.check_enrichable(row(person), enricher)
    with pytest.raises(Refused):
        ethics.check_enrichable(row(doc), "wikidata")
    with pytest.raises(Refused):
        ethics.check_enrichable(row(figure), "geocode")  # people are not geocoded


def test_redaction_removes_full_names_and_aliases_only(services, c):
    entities.upsert(services, case_id=c["id"], type="person", name="Bob Smith", aliases=["Bobby S"])
    entities.upsert(services, case_id=c["id"], type="person", name="Jane Doe", public_figure=True)
    clean, removed = ethics.redact_query(services, c["id"], "Bob Smith and Jane Doe at Acme, also Bobby S")
    assert "bob" not in clean and "smith" not in clean and "bobby" not in clean
    assert "jane doe" in clean and "acme" in clean  # public figures and organisations stay searchable
    assert {"bob smith", "bobby s"} <= set(removed)
    same, none = ethics.redact_query(services, c["id"], "just Smith here")
    assert "smith" in same and none == []  # a lone surname is not the registered name


def test_private_flag_survives_merge_and_public_needs_both(services, c):
    a = entities.upsert(services, case_id=c["id"], type="person", name="Sam Roe")["entity"]
    b = entities.upsert(services, case_id=c["id"], type="person", name="Samuel Roe", public_figure=True)["entity"]
    assert a["private_person"] and not b["private_person"]
    entities.merge(services, b["id"], a["id"], confirm=True)
    assert entities.get(services, b["id"])["private_person"] is True  # the stricter flag wins


def test_reports_mark_private_people(services, c):
    s = sources.add(services, case_id=c["id"], kind="text", text="Bob Smith works for Acme.", origin="x.example")["source"]
    bob = entities.upsert(services, case_id=c["id"], type="person", name="Bob Smith")["entity"]
    acme = entities.upsert(services, case_id=c["id"], type="organization", name="Acme")["entity"]
    relations.add(services, case_id=c["id"], subject=bob["id"], predicate="works_for", object=acme["id"], evidence=[{"source_id": s["id"], "quote": "Bob Smith works"}])
    md = reports.report(services, c["id"], lang="en", use_model=False)["markdown"]
    assert "private person" in md.lower()


def test_model_prompt_never_asks_for_more_about_private_people(tmp_path):
    from conftest import FakeLink, make_services
    link = FakeLink(chat_text="Bob Smith works for Acme [S1].")
    svc = make_services(tmp_path, link=link)
    svc.start()
    try:
        c = cases.create(svc, title="P")["case"]
        s = sources.add(svc, case_id=c["id"], kind="text", text="Bob Smith works for Acme.", origin="x.example")["source"]
        bob = entities.upsert(svc, case_id=c["id"], type="person", name="Bob Smith")["entity"]
        acme = entities.upsert(svc, case_id=c["id"], type="organization", name="Acme")["entity"]
        relations.add(svc, case_id=c["id"], subject=bob["id"], predicate="works_for", object=acme["id"], evidence=[{"source_id": s["id"], "quote": "Bob Smith works"}])
        reports.report(svc, c["id"], use_model=True)
        prompt = link.chat_calls[0][0][0]["content"]
        assert "private person" in prompt.lower()
    finally:
        svc.stop()


def test_settings_validation_and_defaults(services):
    assert services.family_tools() == {"borges": "library_search", "links": "search_links"}
    out = services.update_settings({"family_sources": ["borges"], "family_tools": {"borges": "library_search_v2"}})
    assert out["family_sources"] == ["borges"] and services.family_tools()["borges"] == "library_search_v2"
    with pytest.raises(AtlasError):
        services.update_settings({"family_sources": "borges"})
    with pytest.raises(AtlasError):
        services.update_settings({"family_tools": {"borges": ""}})


def test_status_reports_model_and_counts(services, case):
    st = services.status()
    assert st["service"] == "atlas-hoard" and st["counts"]["relations"] == 2 and st["model"]["llm"]["state"] == "resolved"
    assert st["geocode"]["enabled"] is True
