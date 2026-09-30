"""Time and place views of a case: timeline (with gaps and contradictions), map layers, graph."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import cases as cases_mod
from . import dates
from . import entities as entities_mod
from . import relations as relations_mod
from .errors import AtlasError
from .util import jload

LIVE = ("claimed", "corroborated", "confirmed", "disputed")


def _entity_types(svc, case_id: int) -> dict[int, Any]:
    return {e["id"]: e for e in svc.db.query("SELECT * FROM entities WHERE case_id = ?", (case_id,))}


def contradictions(svc, case_id: int) -> list[dict]:
    """Incompatible facts: two live relations of a *functional* predicate on the same subject with different
    objects and overlapping validity, plus everything a person marked disputed."""
    views = relations_mod.list_views(svc, case_id, statuses=list(LIVE))
    out: list[dict] = []
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for v in views:
        if not v["functional"]:
            continue
        info = svc.db.one("SELECT symmetric FROM predicates WHERE name = ?", (v["predicate"],))
        groups[(v["subject_id"], v["predicate"])].append(v)
        if info and info["symmetric"]:
            groups[(v["object_id"], v["predicate"])].append({**v, "subject_id": v["object_id"], "subject_name": v["object_name"],
                                                             "object_id": v["subject_id"], "object_name": v["subject_name"]})
    seen: set[tuple] = set()
    for (subject, predicate), rels in groups.items():
        for i, a in enumerate(rels):
            for b in rels[i + 1:]:
                if a["object_id"] == b["object_id"] or a["id"] == b["id"]:
                    continue
                if not dates.overlap(a["valid_from"], a["valid_to"], b["valid_from"], b["valid_to"]):
                    continue
                key = (predicate, tuple(sorted((a["id"], b["id"]))))
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "kind": "functional_conflict", "predicate": predicate, "subject_id": subject, "subject_name": a["subject_name"],
                    "relation_ids": sorted((a["id"], b["id"])),
                    "objects": [a["object_name"], b["object_name"]],
                    "intervals": [[a["valid_from"], a["valid_to"]], [b["valid_from"], b["valid_to"]]],
                    "note": f"{a['subject_name']} cannot {a['predicate_label']} both {a['object_name']} and {b['object_name']} at the same time.",
                })
    for v in views:
        if v["status"] == "disputed":
            out.append({"kind": "disputed", "relation_id": v["id"], "label": v["label"], "reason": v["manual_reason"]})
    return out


def timeline(svc, case_id: int, *, entity_id: int | None = None, types: list[str] | None = None, as_of: str | None = None,
             date_from: str | None = None, date_to: str | None = None, gap_days: int = 365, include_retracted: bool = False,
             limit: int = 200) -> dict:
    cases_mod.get_row(svc, case_id)
    if types:
        for t in types:
            if t not in entities_mod.TYPES:
                raise AtlasError(f"type must be one of {', '.join(entities_mod.TYPES)}.")
    ents = _entity_types(svc, case_id)
    entries: list[dict[str, Any]] = []
    linked_events: set[int] = set()
    rels = relations_mod.list_views(svc, case_id, include_retracted=include_retracted, with_evidence=False)
    for v in rels:
        if entity_id is not None and entity_id in (v["subject_id"], v["object_id"]):
            for other in (v["subject_id"], v["object_id"]):
                if other in ents and ents[other]["type"] == "event":
                    linked_events.add(other)

    def type_ok(*ids: int) -> bool:
        return not types or any(ents[i]["type"] in types for i in ids if i in ents)

    for e in ents.values():
        if e["merged_into"] is not None or e["type"] != "event" or not (e["date_start"] or e["date_end"]):
            continue
        if entity_id is not None and e["id"] != entity_id and e["id"] not in linked_events:
            continue
        if not type_ok(e["id"]):
            continue
        entries.append({"kind": "event", "date": e["date_start"] or e["date_end"], "date_end": e["date_end"], "entity_id": e["id"],
                        "name": e["name"], "place": None, "source_count": entities_mod.view(svc, e)["source_count"]})
    for v in rels:
        if entity_id is not None and entity_id not in (v["subject_id"], v["object_id"]):
            continue
        if not type_ok(v["subject_id"], v["object_id"]):
            continue
        base = {"relation_id": v["id"], "label": v["label"], "status": v["status"], "predicate": v["predicate"],
                "flags": v["flags"], "stale": v["stale"], "evidence_count": v["evidence_count"], "cite": v["cite"]}
        if v["valid_from"]:
            entries.append({"kind": "relation_start", "date": v["valid_from"], **base})
        if v["valid_to"]:
            entries.append({"kind": "relation_end", "date": v["valid_to"], **base})
    lo = dates.start_day(date_from)
    hi = dates.end_day(date_to)
    cap = dates.end_day(as_of)
    kept = []
    for x in entries:
        d = dates.start_day(x["date"])
        if d is None:
            continue
        if (lo and d < lo) or (hi and d > hi) or (cap and d > cap):
            continue
        if as_of and x["kind"] != "event":
            x["active_at_as_of"] = dates.contains(rels_lookup(rels, x["relation_id"])["valid_from"], rels_lookup(rels, x["relation_id"])["valid_to"], as_of)
        kept.append(x)
    kept.sort(key=lambda x: (dates.sort_key(x["date"]), x.get("relation_id") or x.get("entity_id") or 0))
    gaps = []
    for a, b in zip(kept, kept[1:]):
        da, db = dates.end_day(a["date"]), dates.start_day(b["date"])
        if da and db and (db - da).days > gap_days:
            gaps.append({"from": a["date"], "to": b["date"], "days": (db - da).days})
    window = [x for x in kept]
    result = {
        "case_id": case_id, "entity_id": entity_id, "as_of": as_of, "total": len(window), "entries": window[:limit],
        "truncated": len(window) > limit, "gaps": gaps, "gap_days": gap_days,
        "contradictions": [c for c in contradictions(svc, case_id)
                           if entity_id is None or c.get("subject_id") == entity_id or entity_id in _c_entities(svc, c)],
        "range": {"from": window[0]["date"] if window else None, "to": window[-1]["date"] if window else None},
    }
    return result


def rels_lookup(rels: list[dict], rid: int) -> dict:
    for r in rels:
        if r["id"] == rid:
            return r
    return {"valid_from": None, "valid_to": None}


def _c_entities(svc, c: dict) -> set[int]:
    if c["kind"] == "disputed":
        r = svc.db.one("SELECT subject_id, object_id FROM relations WHERE id = ?", (c["relation_id"],))
        return {r["subject_id"], r["object_id"]} if r else set()
    return set()


# ---------------- map ----------------

def map_layers(svc, case_id: int, *, as_of: str | None = None, date_from: str | None = None, date_to: str | None = None,
               types: list[str] | None = None) -> dict:
    """One layer per entity type that has coordinates; each layer reports how many sources stand behind it and its date span."""
    cases_mod.get_row(svc, case_id)
    lo, hi = dates.start_day(date_from), dates.end_day(date_to)
    rels = relations_mod.list_views(svc, case_id, include_retracted=False, with_evidence=False)
    by_entity: dict[int, list[dict]] = defaultdict(list)
    for v in rels:
        by_entity[v["subject_id"]].append(v)
        by_entity[v["object_id"]].append(v)
    layers: dict[str, dict] = {}
    unplaced = []
    all_dates: list[str] = []
    for e in svc.db.query("SELECT * FROM entities WHERE case_id = ? AND merged_into IS NULL ORDER BY id", (case_id,)):
        if types and e["type"] not in types:
            continue
        for d in (e["date_start"], e["date_end"]):
            if d:
                all_dates.append(d)
        if e["lat"] is None:
            if e["type"] in ("place", "event", "organization"):
                unplaced.append({"entity_id": e["id"], "name": e["name"], "type": e["type"]})
            continue
        start, end = dates.start_day(e["date_start"]), dates.end_day(e["date_end"] or e["date_start"])
        if as_of:
            point = dates.parse_partial(as_of)
            if (start and start > point[1]) or (end and e["type"] == "event" and end < point[0] and e["date_end"]):  # type: ignore[index]
                continue
        if lo and end and end < lo:
            continue
        if hi and start and start > hi:
            continue
        v = entities_mod.view(svc, e)
        layer = layers.setdefault(e["type"], {"type": e["type"], "count": 0, "features": [], "_src": set(), "_dates": []})
        src_ids = {r["source_id"] for r in svc.db.query(
            """SELECT ev.source_id FROM evidence ev JOIN sources s ON s.id = ev.source_id WHERE s.retracted = 0 AND
               (ev.entity_id = ? OR ev.relation_id IN (SELECT id FROM relations WHERE subject_id = ? OR object_id = ?))""", (e["id"],) * 3)}
        layer["_src"] |= src_ids
        for d in (e["date_start"], e["date_end"], *[x for rel in by_entity.get(e["id"], []) for x in (rel["valid_from"], rel["valid_to"])]):
            if d:
                layer["_dates"].append(d)
                all_dates.append(d)
        layer["features"].append({"entity_id": e["id"], "name": e["name"], "lat": e["lat"], "lon": e["lon"], "precision": e["geo_precision"],
                                  "date_start": e["date_start"], "date_end": e["date_end"], "source_count": v["source_count"],
                                  "private": v["private_person"], "qid": e["wikidata_qid"]})
        layer["count"] += 1
    out_layers = []
    for layer in layers.values():
        ds = sorted(layer.pop("_dates"), key=dates.sort_key)
        layer["source_count"] = len(layer.pop("_src"))
        layer["coverage"] = {"from": ds[0] if ds else None, "to": ds[-1] if ds else None}
        out_layers.append(layer)
    out_layers.sort(key=lambda l: l["type"])
    ds_all = sorted(all_dates, key=dates.sort_key)
    return {"case_id": case_id, "as_of": as_of, "layers": out_layers, "unplaced": unplaced[:50], "unplaced_count": len(unplaced),
            "time_range": {"from": ds_all[0] if ds_all else None, "to": ds_all[-1] if ds_all else None},
            "attribution": "Map data © OpenStreetMap contributors (ODbL); geocoding by Nominatim."}


# ---------------- graph ----------------

def graph(svc, case_id: int, *, entity_id: int | None = None, depth: int = 1, statuses: list[str] | None = None,
          as_of: str | None = None, date_from: str | None = None, date_to: str | None = None, include_retracted: bool = False,
          max_nodes: int = 120) -> dict:
    """Entities as nodes, relations as edges coloured by status. With ``entity_id``: its neighbourhood up to ``depth``."""
    cases_mod.get_row(svc, case_id)
    if not 1 <= depth <= 4:
        raise AtlasError("depth must be between 1 and 4.")
    lo, hi = dates.start_day(date_from), dates.end_day(date_to)
    rels = relations_mod.list_views(svc, case_id, statuses=statuses, as_of=as_of, include_retracted=include_retracted, with_evidence=False)
    if lo or hi:
        def in_range(v):
            a, b = dates.start_day(v["valid_from"]), dates.end_day(v["valid_to"])
            return not ((lo and b and b < lo) or (hi and a and a > hi))
        rels = [v for v in rels if in_range(v)]
    ents = {e["id"]: e for e in svc.db.query("SELECT * FROM entities WHERE case_id = ? AND merged_into IS NULL", (case_id,))}
    rels = [v for v in rels if v["subject_id"] in ents and v["object_id"] in ents]
    include: set[int]
    if entity_id is not None:
        entities_mod.get_row(svc, entity_id, case_id)
        include, frontier = {entity_id}, {entity_id}
        for _ in range(depth):
            nxt = set()
            for v in rels:
                if v["subject_id"] in frontier:
                    nxt.add(v["object_id"])
                if v["object_id"] in frontier:
                    nxt.add(v["subject_id"])
            frontier = nxt - include
            include |= nxt
    else:
        include = set(ents)
    edges = [v for v in rels if v["subject_id"] in include and v["object_id"] in include]
    degree: dict[int, int] = defaultdict(int)
    for v in edges:
        degree[v["subject_id"]] += 1
        degree[v["object_id"]] += 1
    truncated = False
    if len(include) > max_nodes:
        keep = {entity_id} if entity_id is not None else set()
        for nid in sorted(include, key=lambda i: (-degree[i], i)):
            if len(keep) >= max_nodes:
                break
            keep.add(nid)
        include, truncated = keep, True
        edges = [v for v in edges if v["subject_id"] in include and v["object_id"] in include]
    nodes = []
    for nid in sorted(include):
        e = ents[nid]
        ev = entities_mod.view(svc, e)
        nodes.append({"id": nid, "name": e["name"], "type": e["type"], "private": bool(e["private_person"]), "degree": degree[nid],
                      "source_count": ev["source_count"], "center": nid == entity_id})
    return {
        "case_id": case_id, "entity_id": entity_id, "depth": depth, "as_of": as_of, "truncated": truncated,
        "nodes": nodes,
        "edges": [{"id": v["id"], "source": v["subject_id"], "target": v["object_id"], "predicate": v["predicate"], "label": v["label"],
                   "status": v["status"], "confidence": v["confidence"], "evidence_count": v["evidence_count"],
                   "valid_from": v["valid_from"], "valid_to": v["valid_to"], "stale": v["stale"], "flags": v["flags"], "cite": v["cite"]}
                  for v in edges],
        "status_legend": list(relations_mod.STATUSES),
    }
