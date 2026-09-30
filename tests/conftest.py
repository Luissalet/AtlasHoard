from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
for entry in (str(ROOT), str(ROOT / "tests")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

warnings.filterwarnings("ignore", category=DeprecationWarning)

from atlas_hoard.config import Config  # noqa: E402
from atlas_hoard.fetch import FetchResult  # noqa: E402
from atlas_hoard.main import create_app  # noqa: E402
from atlas_hoard.services import Services  # noqa: E402

# Words that must never appear in the product, its manifest or its docs (built from fragments so this file does not contain them).
BANNED_WORDS = ("chat" + "gpt", "open" + "ai", "anthro" + "pic", "lm " + "studio", "odys" + "seus", "vitru" + "vius", "gem" + "ini", "co" + "pilot", "clau" + "de")

T0 = 1_790_000_000.0  # 2026-09-21 in UTC: the fixed clock of the tests

ARTICLE = """<html lang="en"><head><title>Acme Corp opens Paris office</title>
<meta property="article:published_time" content="2024-03-05T09:00:00Z"></head><body>
<nav><a href="/">Home</a><a href="/news">News</a></nav>
<article><h1>Acme Corp opens Paris office</h1>
<p>Acme Corp announced on 5 March 2024 that its new headquarters will be in Paris, France, led by chief executive Jane Doe.</p>
<p>The company previously operated from Lyon. The move is expected to create 200 jobs over two years, a spokesperson said.</p>
<p>Analysts quoted by the newspaper said the decision reflects the growth of the European market.</p></article>
<footer>Copyright 2024 Example Daily</footer><script>var x = 1;</script></body></html>"""


class FakeFetcher:
    """Maps URL -> (status, content type, body); anything else is a 404. Counts calls."""

    def __init__(self, pages: Optional[dict[str, Any]] = None):
        self.pages = pages or {}
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        page = self.pages.get(url)
        if page is None:
            return FetchResult(url, url, 404, "text/html", b"not found")
        if isinstance(page, FetchResult):
            return page
        status, ctype, body = page
        return FetchResult(url, url, status, ctype, body.encode() if isinstance(body, str) else body)


class FakeWikidata:
    """Two items: Acme Corp (Q100) and Paris (Q90); 'Springfield' is ambiguous."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.items = {
            "Q100": {"qid": "Q100", "label": "Acme Corp", "description": "fictional manufacturing company", "aliases": ["Acme"],
                     "url": "https://www.wikidata.org/wiki/Q100", "coordinates": None,
                     "statements": [
                         {"property": "P159", "name": "headquarters location", "kind": "entity",
                          "value": {"qid": "Q90", "label": "Paris", "description": "capital of France", "human": False, "coords": True}},
                         {"property": "P169", "name": "chief executive officer", "kind": "entity", "start": "2021",
                          "value": {"qid": "Q777", "label": "Jane Doe", "description": "business executive", "human": True, "coords": False}},
                         {"property": "P571", "name": "inception", "kind": "time", "value": {"iso": "1949-03-01"}},
                         {"property": "P856", "name": "official website", "kind": "string", "value": {"text": "https://acme.example"}},
                     ]},
            "Q90": {"qid": "Q90", "label": "Paris", "description": "capital of France", "aliases": ["Ville Lumière"],
                    "url": "https://www.wikidata.org/wiki/Q90", "coordinates": {"lat": 48.8566, "lon": 2.3522},
                    "statements": [
                        {"property": "P625", "name": "coordinate location", "kind": "coordinate", "value": {"lat": 48.8566, "lon": 2.3522}},
                        {"property": "P17", "name": "country", "kind": "entity",
                         "value": {"qid": "Q142", "label": "France", "description": "country in Europe", "human": False, "coords": True}},
                        {"property": "P1082", "name": "population", "kind": "string", "value": {"text": "2102650"}},
                    ]},
            "Q500": {"qid": "Q500", "label": "Moon landing", "description": "1969 event", "aliases": [], "url": "https://www.wikidata.org/wiki/Q500",
                     "coordinates": None,
                     "statements": [{"property": "P585", "name": "point in time", "kind": "time", "value": {"iso": "1969-07-20"}}]},
        }

    def search(self, name, *, language="en", limit=6):
        self.calls.append(("search", name))
        key = name.lower()
        if key == "springfield":
            return [{"qid": "Q1", "label": "Springfield", "description": "city in Illinois"},
                    {"qid": "Q2", "label": "Springfield", "description": "city in Massachusetts"}]
        return [{"qid": q, "label": it["label"], "description": it["description"]} for q, it in self.items.items() if it["label"].lower() == key]

    def fetch(self, qid, *, language="en"):
        self.calls.append(("fetch", qid))
        if qid not in self.items:
            from atlas_hoard.errors import AtlasError
            raise AtlasError(f"Wikidata has no item {qid}.")
        return self.items[qid]

    def labels(self, qids, *, language="en"):
        return {}


class FakeGeocoder:
    def __init__(self):
        self.calls: list[str] = []
        self.data = {
            "paris": [{"lat": 48.8566, "lon": 2.3522, "display_name": "Paris, Île-de-France, France", "precision": "locality", "osm_type": "relation", "osm_id": 7444},
                      {"lat": 33.66, "lon": -95.55, "display_name": "Paris, Texas, United States", "precision": "locality", "osm_type": "relation", "osm_id": 1},],
            "lyon": [{"lat": 45.764, "lon": 4.8357, "display_name": "Lyon, France", "precision": "locality", "osm_type": "relation", "osm_id": 2}],
        }

    def lookup(self, query, *, limit=3):
        self.calls.append(query)
        return self.data.get(query.lower().strip(), [])[:limit]


class FakeFamily:
    """Stands in for hoard_link.family.call. `apps` maps app -> reply dict (or an Exception to raise)."""

    def __init__(self, apps: Optional[dict[str, Any]] = None):
        self.apps = apps if apps is not None else {}
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, app, tool, arguments):
        self.calls.append((app, tool, arguments))
        reply = self.apps.get(app)
        if isinstance(reply, Exception):
            raise reply
        if reply is None:
            return {"ok": False, "app": app, "tool": tool, "status": None, "error": "hub not reachable"}
        return reply


@dataclass
class FakeChatResult:
    text: str = "Acme Corp is headquartered in Paris [S1]."
    model: str = "fake-model"


class FakeLink:
    """A sync-shaped stand-in for hoard_link.Link.sync: no network, deterministic."""

    def __init__(self, chat_text: Optional[str] = None, available: bool = True):
        self.chat_text, self.available, self.chat_calls = chat_text, available, []

    def chat(self, messages, images=None, **kwargs):
        self.chat_calls.append((messages, kwargs))
        if not self.available:
            raise RuntimeError("no model configured")
        return FakeChatResult(text=self.chat_text if self.chat_text is not None else FakeChatResult().text)

    def status(self):
        cap = {"state": "resolved" if self.available else "unavailable", "provider": "fake", "model": "fake-model"}
        return {"llm": cap}

    def close(self):
        pass


class Recorder:
    """Collects events that would go to the hub bus."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __call__(self, type_, data):
        self.events.append((type_, data))

    def types(self):
        return [t for t, _ in self.events]


def make_config(tmp_path: Path, **overrides) -> Config:
    base = dict(data_dir=tmp_path / "data", port=0, data_dir_configured=True)
    base.update(overrides)
    return Config(**base)


def make_services(tmp_path: Path, *, pages=None, link=None, family_apps=None, **config_overrides) -> Services:
    config = make_config(tmp_path, **config_overrides)
    family = FakeFamily(family_apps)
    svc = Services(config, link=link if link is not None else FakeLink(), fetcher=FakeFetcher(pages), wikidata=FakeWikidata(),
                   geocoder=FakeGeocoder(), family_call=family, emit_fn=Recorder(), clock_fn=lambda: T0)
    svc.fake_family = family
    return svc


@pytest.fixture
def services(tmp_path):
    svc = make_services(tmp_path, pages={"https://news.example.com/acme": (200, "text/html; charset=utf-8", ARTICLE)})
    svc.start()
    yield svc
    svc.stop()


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    svc = make_services(tmp_path, pages={"https://news.example.com/acme": (200, "text/html; charset=utf-8", ARTICLE)})
    app = create_app(svc.config, svc)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.svc = svc
        yield test_client


@pytest.fixture
def case(services):
    """A case with two sources, three entities and two relations (one corroborated, one claimed)."""
    from atlas_hoard import cases, entities, relations, sources
    c = cases.create(services, title="Acme HQ move", question="Where is Acme headquartered?")["case"]
    s1 = sources.add(services, case_id=c["id"], kind="text", title="Press release", text="Acme Corp moved its headquarters to Paris in 2024.",
                     reliability="B", credibility="2", origin="acme.example", published_at="2024-03-05")["source"]
    s2 = sources.add(services, case_id=c["id"], kind="text", title="Newspaper", text="The firm Acme is now based in Paris, the paper reports.",
                     reliability="C", credibility="3", origin="daily.example", published_at="2024-03-06")["source"]
    acme = entities.upsert(services, case_id=c["id"], type="organization", name="Acme Corp")["entity"]
    paris = entities.upsert(services, case_id=c["id"], type="place", name="Paris", lat=48.85, lon=2.35)["entity"]
    jane = entities.upsert(services, case_id=c["id"], type="person", name="Jane Doe", public_figure=True)["entity"]
    r1 = relations.add(services, case_id=c["id"], subject=acme["id"], predicate="headquartered_in", object=paris["id"], valid_from="2024",
                       evidence=[{"source_id": s1["id"], "quote": "Acme Corp moved its headquarters to Paris in 2024."},
                                 {"source_id": s2["id"], "quote": "Acme is now based in Paris"}])["relation"]
    r2 = relations.add(services, case_id=c["id"], subject=jane["id"], predicate="ceo_of", object=acme["id"],
                       evidence=[{"source_id": s1["id"], "locator": "para 2"}])["relation"]
    return {"case": c, "s1": s1, "s2": s2, "acme": acme, "paris": paris, "jane": jane, "r1": r1, "r2": r2}
