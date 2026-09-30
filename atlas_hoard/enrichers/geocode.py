"""Geocoding through Nominatim (OpenStreetMap): one request per second, cached, optional, never required.

Usage policy of the public instance: an identifying User-Agent, at most one request per second and no bulk
geocoding; results must credit OpenStreetMap contributors (ODbL). Manual coordinates are always possible.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from .. import entities as entities_mod
from .. import sources as sources_mod
from ..errors import AtlasError
from .base import RunContext

PRECISION = {
    "house": "exact", "building": "exact", "apartments": "exact", "residential": "street", "road": "street", "street": "street",
    "neighbourhood": "locality", "suburb": "locality", "quarter": "locality", "hamlet": "locality", "village": "locality",
    "town": "locality", "city": "locality", "municipality": "locality", "administrative": "region", "county": "region",
    "state": "region", "region": "region", "province": "region", "country": "country", "continent": "country",
}
CREDIT = "Data © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)."


class Geocoder(Protocol):
    def lookup(self, query: str, *, limit: int = 3) -> list[dict]: ...


def precision_of(result: dict) -> str:
    for key in ("addresstype", "type", "category"):
        if result.get(key) in PRECISION:
            return PRECISION[result[key]]
    return "approximate"


class NominatimGeocoder:
    """The public Nominatim search API, rate limited to 1 request/second across threads."""

    def __init__(self, *, url: str, user_agent: str, timeout_s: float = 20.0, min_interval_s: float = 1.0):
        self.url, self.user_agent, self.timeout_s, self.min_interval_s = url, user_agent, timeout_s, min_interval_s
        self._lock = threading.Lock()
        self._last = 0.0

    def lookup(self, query: str, *, limit: int = 3) -> list[dict]:
        with self._lock:
            wait = self.min_interval_s - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = httpx.get(self.url, params={"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 0},
                              headers={"User-Agent": self.user_agent}, timeout=self.timeout_s)
                r.raise_for_status()
                data = r.json()
            except (httpx.HTTPError, ValueError) as error:
                raise AtlasError(f"Nominatim is not reachable: {type(error).__name__}: {error}") from error
            finally:
                self._last = time.monotonic()
        return [{"lat": float(x["lat"]), "lon": float(x["lon"]), "display_name": x.get("display_name", ""),
                 "precision": precision_of(x), "osm_type": x.get("osm_type", ""), "osm_id": x.get("osm_id", ""),
                 "class": x.get("category") or x.get("class", ""), "type": x.get("type", "")} for x in data]


class CachedGeocoder:
    """Wraps any geocoder with the SQLite cache: the same query is never asked twice."""

    def __init__(self, db, inner: Geocoder, clock=time.time):
        self.db, self.inner, self.clock = db, inner, clock
        self.hits = 0

    def lookup(self, query: str, *, limit: int = 3) -> list[dict]:
        key = " ".join(query.lower().split())
        row = self.db.one("SELECT result FROM geocode_cache WHERE query = ?", (key,))
        if row is not None:
            self.hits += 1
            return json.loads(row["result"])[:limit]
        results = self.inner.lookup(query, limit=max(limit, 3))
        self.db.execute("INSERT OR REPLACE INTO geocode_cache(query, result, ts) VALUES (?,?,?)",
                        (key, json.dumps(results, ensure_ascii=False), self.clock()))
        return results[:limit]


def run(ctx: RunContext) -> dict:
    svc, p, entity = ctx.svc, ctx.params, ctx.entity
    if not svc.geocode_enabled():
        return {"status": "disabled", "reason": "Geocoding is switched off (ATLAS_GEOCODE=0 or the Settings toggle). Set lat/lon by hand with entity_upsert."}
    if entity is None:
        raise AtlasError("geocode enrichment needs an entity_id.")
    query = (p.get("query") or entity["name"]).strip()
    if entity["lat"] is not None and not p.get("overwrite"):
        return {"status": "already_placed", "lat": entity["lat"], "lon": entity["lon"], "precision": entity["geo_precision"],
                "hint": "Pass overwrite=true to replace the coordinates."}
    results = svc.geocoder.lookup(query, limit=3)
    if not results:
        return {"status": "not_found", "query": query, "hint": "Try a more specific query (add the country) or set coordinates by hand."}
    top = results[0]
    if p.get("dry_run"):
        return {"status": "dry_run", "query": query, "result": top, "alternatives": results[1:], "note": "Nothing was written."}
    url = "https://nominatim.openstreetmap.org/search?" + urlencode({"q": query})
    text = (f"Nominatim result for {query!r}: {top['display_name']}\nlat {top['lat']}, lon {top['lon']} "
            f"(precision: {top['precision']}; OSM {top.get('osm_type', '')} {top.get('osm_id', '')})\n{CREDIT}")
    src = sources_mod.add(svc, case_id=ctx.case_id, kind="url", url=url, title=f"OpenStreetMap Nominatim: {query}", text=text,
                          reliability="B", credibility="3", origin="nominatim.openstreetmap.org", run_id=ctx.run_id,
                          note="Geocoding result; OpenStreetMap contributors, ODbL.")
    ctx.touch(entity["id"])
    quote = f"lat {top['lat']}, lon {top['lon']}"
    res = entities_mod.upsert(svc, case_id=ctx.case_id, entity_id=entity["id"], lat=top["lat"], lon=top["lon"], geo_precision=top["precision"],
                              attributes={"geocode": {"value": top["display_name"], "source_id": src["source"]["id"], "quote": quote, "locator": "nominatim"}},
                              run_id=ctx.run_id)
    note = f"Top-ranked of {len(results)} result(s); check the place is the intended one." if len(results) > 1 else ""
    return {"status": "ok", "query": query, "lat": top["lat"], "lon": top["lon"], "precision": top["precision"],
            "display_name": top["display_name"], "alternatives": results[1:], "source_id": src["source"]["id"],
            "entity_changed": res.get("changed", []), "note": note}
