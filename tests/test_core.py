"""Dates, helpers, config, database and the request guard."""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from atlas_hoard import dates, util
from atlas_hoard.config import DEFAULT_PORT, Config
from atlas_hoard.db import Database
from atlas_hoard.errors import AtlasError
from atlas_hoard.guard import is_allowed_host, parse_allowed_hosts


def test_partial_dates_are_day_ranges():
    assert dates.parse_partial("2024") == (date(2024, 1, 1), date(2024, 12, 31))
    assert dates.parse_partial("2024-02") == (date(2024, 2, 1), date(2024, 2, 29))
    assert dates.parse_partial("2024-02-10") == (date(2024, 2, 10), date(2024, 2, 10))
    assert dates.parse_partial("") is None and dates.parse_partial(None) is None


@pytest.mark.parametrize("bad", ["2024-13", "2024-02-30", "abc", "0000", "2024/01"])
def test_invalid_dates_are_rejected(bad):
    with pytest.raises(AtlasError):
        dates.parse_partial(bad)


def test_normalize_pads():
    assert dates.normalize("800-3") == "0800-03"
    assert dates.normalize(" 2024-1-5 ") == "2024-01-05"
    assert dates.normalize(None) is None


def test_contains_uses_valid_time():
    assert dates.contains("2010", "2016", "2012")
    assert dates.contains("2010", "2016", "2016-12")
    assert not dates.contains("2010", "2016", "2017")
    assert dates.contains(None, "2016", "1900")  # open start
    assert dates.contains("2010", None, "2100")  # open end
    assert dates.contains("2010", "2016", None)  # no as_of means no filter


def test_overlap_and_sort_key():
    assert dates.overlap("2010", "2015", "2015", "2020")
    assert not dates.overlap("2010", "2014", "2015", "2020")
    assert dates.overlap(None, None, "2000", "2001")
    assert sorted(["2024-03", "2023", "2024"], key=dates.sort_key) == ["2023", "2024", "2024-03"]


def test_util_helpers():
    assert util.norm_name("Acme  Corp ") == util.norm_name("acme corp")
    assert util.clean_list(["a", " a ", "", "b"]) == ["a", "b"]
    assert util.clip("x" * 100, 10).endswith("…") and len(util.clip("x" * 100, 10)) <= 11
    assert util.jload("not json", {"d": 1}) == {"d": 1}
    assert util.jload(util.jdump({"a": [1]}), None) == {"a": [1]}


def test_page_cursor_and_budget():
    rows = [{"i": i, "pad": "x" * 100} for i in range(30)]
    first, nxt = util.page(rows, 10, None)
    assert len(first) == 10 and nxt == "o:10"
    second, nxt2 = util.page(rows, 10, nxt)
    assert second[0]["i"] == 10 and nxt2 == "o:20"
    last, nxt3 = util.page(rows, 10, "o:20")
    assert len(last) == 10 and nxt3 is None
    small, nxt4 = util.page(rows, 30, None, budget=500)
    assert len(small) < 30 and nxt4 is not None


def test_fts_query_is_safe():
    q = util.fts_query('acme "corp" AND OR (*)')
    assert "AND OR" not in q.replace('"', "")


def test_config_defaults(tmp_path, monkeypatch):
    for key in ("ATLAS_PORT", "PORT", "ATLAS_GEOCODE", "ATLAS_ALLOW_PRIVATE_URLS", "ATLAS_FILE_ROOTS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ATLAS_DATA_DIR", str(tmp_path / "d"))
    cfg = Config.from_env()
    assert cfg.port == DEFAULT_PORT == 5193
    assert cfg.geocode is True and cfg.allow_private_urls is False
    assert cfg.stale_days == 730
    assert cfg.db_path.name == "atlas.db" and cfg.token_path.name == "mcp-token"


def test_config_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("ATLAS_GEOCODE", "0")
    monkeypatch.setenv("ATLAS_ALLOW_PRIVATE_URLS", "1")
    monkeypatch.setenv("ATLAS_FILE_ROOTS", str(tmp_path))
    cfg = Config.from_env()
    assert cfg.geocode is False and cfg.allow_private_urls is True
    assert [p.resolve() for p in cfg.file_roots] == [tmp_path.resolve()]


def test_database_migrations_and_wal(tmp_path):
    db = Database(tmp_path / "x.db")
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    for name in ("cases", "sources", "entities", "predicates", "relations", "evidence", "hypotheses", "ach_ratings",
                 "enrichment_runs", "history", "settings", "geocode_cache", "sources_fts", "entities_fts"):
        assert name in tables, name
    assert db.query("PRAGMA journal_mode")[0][0].lower() == "wal"
    version = db.query("SELECT MAX(version) AS v FROM schema_version")[0]["v"]
    db.close()
    again = Database(tmp_path / "x.db")  # re-opening must not re-run migrations
    assert again.query("SELECT MAX(version) AS v FROM schema_version")[0]["v"] == version
    again.close()


def test_settings_roundtrip(tmp_path):
    db = Database(tmp_path / "s.db")
    assert db.get_setting("missing", "d") == "d"
    db.set_setting("k", "v")
    db.set_setting("k", "w")
    assert db.get_setting("k", "d") == "w"


def test_guard_hosts():
    assert is_allowed_host("localhost") and is_allowed_host("127.0.0.1") and is_allowed_host("[::1]")
    assert not is_allowed_host("evil.example")
    allowed = parse_allowed_hosts("box.example, *.ts.net")
    assert is_allowed_host("box.example", allowed) and is_allowed_host("x.ts.net", allowed)
    assert not is_allowed_host("ts.net.evil.example", allowed)


def test_guard_rejects_foreign_host_and_origin(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code in (400, 403)
    r = client.post("/api/cases", json={"title": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code in (400, 403)
