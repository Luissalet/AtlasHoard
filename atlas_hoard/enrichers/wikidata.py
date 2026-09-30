"""Wikidata enricher: public facts about organizations, places, events and public figures, recorded as *claimed*.

The client is an interface (``search`` / ``fetch`` / ``labels``) so tests inject a fake; the HTTP one talks to the
public Wikidata API (CC0 data) with a descriptive User-Agent. Every fact becomes evidence on a Wikidata source
whose snapshot contains the exact statements, so each quote can be checked against it.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Protocol

import httpx

from .. import dates, entities as entities_mod, relations as relations_mod, sources as sources_mod
from ..errors import AtlasError
from ..util import norm_name
from .base import RunContext

HUMAN = "Q5"

# property -> (predicate, direction, target types (first = default), applies to entity types)
REL_MAP: dict[str, tuple[str, str, tuple[str, ...], tuple[str, ...]]] = {
    "P159": ("headquartered_in", "out", ("place",), ("organization",)),
    "P17": ("located_in", "out", ("place",), ("organization", "place", "event")),
    "P131": ("located_in", "out", ("place",), ("organization", "place")),
    "P276": ("occurred_at", "out", ("place",), ("event",)),
    "P112": ("founded", "in", ("person", "organization"), ("organization",)),
    "P169": ("ceo_of", "in", ("person",), ("organization",)),
    "P749": ("subsidiary_of", "out", ("organization",), ("organization",)),
    "P127": ("owns", "in", ("organization", "person"), ("organization",)),
    "P108": ("works_for", "out", ("organization",), ("person",)),
    "P463": ("member_of", "out", ("organization",), ("person", "organization")),
    "P19": ("born_in", "out", ("place",), ("person",)),
    "P20": ("died_in", "out", ("place",), ("person",)),
}
ATTR_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "P571": ("inception", ("organization", "place")), "P576": ("dissolved", ("organization", "place")),
    "P569": ("date_of_birth", ("person",)), "P570": ("date_of_death", ("person",)),
    "P856": ("website", ("organization", "place", "event")), "P1082": ("population", ("place",)),
    "P31": ("instance_of", ("organization", "place", "event", "person")),
}
PROPERTY_NAMES = {
    "P159": "headquarters location", "P17": "country", "P131": "located in the administrative territorial entity",
    "P276": "location", "P112": "founded by", "P169": "chief executive officer", "P749": "parent organization",
    "P127": "owned by", "P108": "employer", "P463": "member of", "P19": "place of birth", "P20": "place of death",
    "P571": "inception", "P576": "dissolved, abolished or demolished date", "P569": "date of birth", "P570": "date of death",
    "P856": "official website", "P1082": "population", "P31": "instance of", "P625": "coordinate location",
    "P580": "start time", "P582": "end time", "P585": "point in time",
}
MAX_PER_PROPERTY = 3
MAX_REFERENCED = 14


class WikidataClient(Protocol):
    def search(self, name: str, *, language: str = "en", limit: int = 6) -> list[dict]: ...
    def fetch(self, qid: str, *, language: str = "en") -> dict: ...
    def labels(self, qids: list[str], *, language: str = "en") -> dict[str, dict]: ...


def _wbtime(value: dict) -> str | None:
    """Wikidata time value -> partial ISO date honouring its precision (9 year, 10 month, 11 day)."""
    match = re.match(r"^([+-])(\d{1,})-(\d{2})-(\d{2})T", value.get("time", ""))
    if not match or match.group(1) == "-":
        return None
    year, month, day = int(match.group(2)), int(match.group(3)), int(match.group(4))
    precision = int(value.get("precision", 11))
    if year < 1 or year > 9999:
        return None
    if precision >= 11 and month and day:
        return f"{year:04d}-{month:02d}-{day:02d}"
    if precision == 10 and month:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}"


class HttpWikidataClient:
    """The public Wikidata API (wbsearchentities / wbgetentities)."""

    def __init__(self, *, url: str, user_agent: str, timeout_s: float = 20.0):
        self.url, self.user_agent, self.timeout_s = url, user_agent, timeout_s

    def _get(self, params: dict) -> dict:
        try:
            r = httpx.get(self.url, params={**params, "format": "json", "formatversion": "2"}, timeout=self.timeout_s,
                          headers={"User-Agent": self.user_agent})
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AtlasError(f"Wikidata is not reachable: {type(error).__name__}: {error}") from error

    def search(self, name: str, *, language: str = "en", limit: int = 6) -> list[dict]:
        data = self._get({"action": "wbsearchentities", "search": name, "language": language, "uselang": language, "type": "item", "limit": limit})
        return [{"qid": x["id"], "label": x.get("label", x["id"]), "description": x.get("description", ""),
                 "aliases": x.get("aliases", [])} for x in data.get("search", [])]

    def labels(self, qids: list[str], *, language: str = "en") -> dict[str, dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(qids), 25):
            chunk = qids[i: i + 25]
            data = self._get({"action": "wbgetentities", "ids": "|".join(chunk), "props": "labels|descriptions|claims",
                              "languages": f"{language}|en"})
            for qid, ent in (data.get("entities") or {}).items():
                if not isinstance(ent, dict) or "missing" in ent:
                    continue
                claims = ent.get("claims", {})
                classes = {c["mainsnak"]["datavalue"]["value"]["id"] for c in claims.get("P31", [])
                           if c.get("mainsnak", {}).get("datavalue")}
                out[qid] = {"label": self._pick(ent.get("labels", {}), language, qid), "description": self._pick(ent.get("descriptions", {}), language, ""),
                            "human": HUMAN in classes, "coords": "P625" in claims}
        return out

    @staticmethod
    def _pick(mapping: dict, language: str, default: str) -> str:
        for lang in (language, "en"):
            if lang in mapping:
                return mapping[lang]["value"]
        return default

    def fetch(self, qid: str, *, language: str = "en") -> dict:
        data = self._get({"action": "wbgetentities", "ids": qid, "props": "labels|descriptions|aliases|claims", "languages": f"{language}|en"})
        ent = (data.get("entities") or {}).get(qid)
        if not isinstance(ent, dict) or "missing" in ent:
            raise AtlasError(f"Wikidata has no item {qid}.")
        claims = ent.get("claims", {})
        statements: list[dict] = []
        coords = None
        referenced: list[str] = []
        for prop in (*REL_MAP, *ATTR_MAP, "P625", "P580", "P582", "P585"):
            entries = [c for c in claims.get(prop, []) if c.get("rank") != "deprecated"]
            preferred = [c for c in entries if c.get("rank") == "preferred"]
            for c in (preferred or entries)[:MAX_PER_PROPERTY]:
                snak = c.get("mainsnak", {})
                dv = snak.get("datavalue")
                if not dv:
                    continue
                v, dtype = dv.get("value"), dv.get("type")
                st: dict[str, Any] = {"property": prop, "name": PROPERTY_NAMES.get(prop, prop)}
                if dtype == "wikibase-entityid":
                    st.update(kind="entity", value={"qid": v["id"]})
                    referenced.append(v["id"])
                elif dtype == "time":
                    iso = _wbtime(v)
                    if not iso:
                        continue
                    st.update(kind="time", value={"iso": iso})
                elif dtype == "globecoordinate":
                    st.update(kind="coordinate", value={"lat": v["latitude"], "lon": v["longitude"]})
                    coords = coords or st["value"]
                elif dtype == "quantity":
                    st.update(kind="string", value={"text": str(v.get("amount", "")).lstrip("+")})
                else:
                    st.update(kind="string", value={"text": str(v)})
                quals = c.get("qualifiers", {})
                for qp, key in (("P580", "start"), ("P582", "end")):
                    for q in quals.get(qp, [])[:1]:
                        qv = (q.get("datavalue") or {}).get("value")
                        if qv and (iso := _wbtime(qv)):
                            st[key] = iso
                statements.append(st)
        ref_info = self.labels(list(dict.fromkeys(referenced))[:MAX_REFERENCED + 10], language=language) if referenced else {}
        for st in statements:
            if st["kind"] == "entity":
                info = ref_info.get(st["value"]["qid"], {})
                st["value"].update(label=info.get("label", st["value"]["qid"]), description=info.get("description", ""),
                                   human=bool(info.get("human")), coords=bool(info.get("coords")))
        aliases = [a["value"] for a in ent.get("aliases", {}).get(language, []) + ent.get("aliases", {}).get("en", [])][:8]
        return {"qid": qid, "label": self._pick(ent.get("labels", {}), language, qid),
                "description": self._pick(ent.get("descriptions", {}), language, ""), "aliases": aliases,
                "url": f"https://www.wikidata.org/wiki/{qid}", "coordinates": coords, "statements": statements}


def _statement_text(st: dict) -> str:
    v = st["value"]
    if st["kind"] == "entity":
        text = f"{v.get('label') or v['qid']} ({v['qid']})"
    elif st["kind"] == "time":
        text = v["iso"]
    elif st["kind"] == "coordinate":
        text = f"{v['lat']}, {v['lon']}"
    else:
        text = v.get("text", "")
    span = ""
    if st.get("start") or st.get("end"):
        span = f" [{st.get('start') or '?'} to {st.get('end') or '?'}]"
    return f"{st['property']} {st['name']}: {text}{span}"


def _snapshot_text(item: dict) -> str:
    head = [f"Wikidata item {item['qid']}: {item['label']}", item.get("description", "")]
    return "\n".join([*[h for h in head if h], *(_statement_text(s) for s in item.get("statements", []))])


def _same(label: str, name: str) -> bool:
    def fold(s: str) -> str:
        return norm_name(unicodedata.normalize("NFKC", s))
    return fold(label) == fold(name)


def pick_item(client: WikidataClient, name: str, language: str, qid: str | None) -> tuple[str | None, list[dict]]:
    """The QID to use, or (None, candidates) when the name is ambiguous. Never guesses between several items."""
    if qid:
        return qid, []
    results = client.search(name, language=language, limit=6)
    if not results:
        return None, []
    exact = [r for r in results if _same(r["label"], name)]
    if len(results) == 1:
        return results[0]["qid"], results
    if len(exact) == 1:
        return exact[0]["qid"], results
    return None, results


def run(ctx: RunContext) -> dict:
    svc, p = ctx.svc, ctx.params
    entity = ctx.entity
    if entity is None:
        raise AtlasError("wikidata enrichment needs an entity_id.")
    language = (p.get("language") or "en")[:5]
    qid = p.get("qid") or entity["wikidata_qid"] or None
    if qid and not re.match(r"^Q\d+$", str(qid)):
        raise AtlasError("qid must look like Q42.")
    chosen, candidates = pick_item(svc.wikidata, entity["name"], language, qid)
    if chosen is None:
        return {"status": "ambiguous" if candidates else "not_found", "candidates": candidates,
                "hint": ("Several Wikidata items match; call enrich again with qid=<one of them>." if candidates
                         else f"Wikidata has no item named {entity['name']!r}; pass qid if you know it.")}
    item = svc.wikidata.fetch(chosen, language=language)
    planned = []
    etype = entity["type"]
    for st in item["statements"]:
        prop = st["property"]
        if prop in REL_MAP and etype in REL_MAP[prop][3] and st["kind"] == "entity":
            planned.append({"property": prop, "as": "relation", "predicate": REL_MAP[prop][0], "text": _statement_text(st)})
        elif prop in ATTR_MAP and etype in ATTR_MAP[prop][1]:
            planned.append({"property": prop, "as": "attribute", "name": ATTR_MAP[prop][0], "text": _statement_text(st)})
    if p.get("dry_run"):
        return {"status": "dry_run", "qid": chosen, "label": item["label"], "description": item.get("description", ""),
                "planned": planned, "note": "Nothing was written."}
    snap_text = _snapshot_text(item)
    src = sources_mod.add(svc, case_id=ctx.case_id, kind="url", url=item["url"], title=f"Wikidata: {item['label']} ({chosen})",
                          text=snap_text, reliability="C", credibility="3", origin="wikidata.org", run_id=ctx.run_id,
                          note="Crowd-sourced public data (CC0). Statements are recorded as claimed.")
    source_id = src["source"]["id"]
    if not src["created"]:
        ctx.notes.append("The same Wikidata snapshot was already a source of this case: reused.")
    ctx.touch(entity["id"])
    fields: dict[str, Any] = {"wikidata_qid": chosen}
    if not entity["description"] and item.get("description"):
        fields["description"] = item["description"]
    alias_add = [a for a in [item["label"], *item.get("aliases", [])] if norm_name(a) != entity["norm_name"]][:8]
    attrs: dict[str, Any] = {}
    made = {"relations": [], "entities": [], "attributes": [], "skipped": []}
    referenced = 0
    for st in item["statements"]:
        prop, text = st["property"], _statement_text(st)
        evidence = {"source_id": source_id, "quote": text, "locator": prop}
        if prop == "P625" and entity["lat"] is None and st["kind"] == "coordinate":
            fields.update(lat=st["value"]["lat"], lon=st["value"]["lon"], geo_precision="wikidata")
            attrs["coordinates_wikidata"] = {"value": f"{st['value']['lat']}, {st['value']['lon']}", **evidence}
        elif prop in ("P580", "P585") and etype == "event" and not entity["date_start"] and st["kind"] == "time":
            fields["date_start"] = st["value"]["iso"]
        elif prop == "P582" and etype == "event" and not entity["date_end"] and st["kind"] == "time":
            fields["date_end"] = st["value"]["iso"]
        elif prop in REL_MAP and etype in REL_MAP[prop][3] and st["kind"] == "entity":
            predicate, direction, types, _ = REL_MAP[prop]
            v = st["value"]
            if referenced >= MAX_REFERENCED:
                made["skipped"].append(text)
                continue
            referenced += 1
            target_type = types[0]
            if "person" in types and v.get("human"):
                target_type = "person"
            elif "organization" in types and "person" in types:
                target_type = "organization"
            elif target_type == "place" and v.get("human"):
                continue
            other_id, created = ctx.ensure_entity(name=v["label"], type=target_type, qid=v["qid"], description=v.get("description", ""),
                                                  public_figure=target_type == "person")
            if created:
                made["entities"].append(other_id)
            s_id, o_id = (entity["id"], other_id) if direction == "out" else (other_id, entity["id"])
            try:
                res = relations_mod.add(svc, case_id=ctx.case_id, subject=s_id, predicate=predicate, object=o_id, evidence=[evidence],
                                        valid_from=st.get("start"), valid_to=st.get("end"), observed_at=None, confidence=0.5,
                                        notes="From Wikidata", run_id=ctx.run_id)
                made["relations"].append(res["relation"]["id"])
            except AtlasError as error:
                made["skipped"].append(f"{text}: {error}")
        elif prop in ATTR_MAP and etype in ATTR_MAP[prop][1]:
            name = ATTR_MAP[prop][0]
            value = (st["value"].get("label") if st["kind"] == "entity" else st["value"].get("iso") or st["value"].get("text"))
            if st["kind"] == "time" and st["value"]["iso"]:
                value = st["value"]["iso"]
            prev = attrs.get(name)
            if prev and name == "instance_of":
                prev["value"] = f"{prev['value']}; {value}"
                prev["quote"] += f" | {text}"
            elif not prev:
                attrs[name] = {"value": value, **evidence}
    if attrs:
        made["attributes"] = sorted(attrs)
    res = entities_mod.upsert(svc, case_id=ctx.case_id, entity_id=entity["id"], aliases=alias_add, attributes=attrs or None,
                              description=fields.get("description"), lat=fields.get("lat"), lon=fields.get("lon"),
                              geo_precision=fields.get("geo_precision"), date_start=fields.get("date_start"),
                              date_end=fields.get("date_end"), wikidata_qid=chosen, run_id=ctx.run_id)
    return {"status": "ok", "qid": chosen, "label": item["label"], "description": item.get("description", ""), "source_id": source_id,
            "relations_added": made["relations"], "entities_created": made["entities"], "attributes_set": made["attributes"],
            "fields_set": sorted(k for k in fields if k != "wikidata_qid") + ["wikidata_qid"], "skipped": made["skipped"],
            "entity_changed": res.get("changed", []), "note": "Everything is recorded as claimed with a Wikidata source; undo with enrichment_undo."}
