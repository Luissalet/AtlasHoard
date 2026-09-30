"""Entities: the things a case talks about. Coincidence is not identity: merges are explicit, similarity only suggests."""

from __future__ import annotations

import difflib
import math
import re
from collections import defaultdict
from typing import Any

from . import cases as cases_mod
from . import history
from .dates import normalize
from .errors import AtlasError, NotFound
from .hoard_link.artifacts import ArtifactRef
from .util import clean_list, clip, fts_query, jdump, jload, norm_name, page

TYPES = ("person", "organization", "place", "event", "document", "object", "domain", "concept")
_QID = re.compile(r"^Q\d+$")


def entity_ref(entity_id: int) -> str:
    return ArtifactRef("atlas", "entity", str(entity_id)).uri


def get_row(svc, entity_id: int, case_id: int | None = None):
    row = svc.db.one("SELECT * FROM entities WHERE id = ?", (entity_id,))
    if row is None or (case_id is not None and row["case_id"] != case_id):
        raise NotFound(f"Entity {entity_id} does not exist" + (f" in case {case_id}." if case_id else "."))
    return row


def resolve(svc, case_id: int, ref: int | str) -> Any:
    """An entity by id or by (normalised) name/alias within a case; ambiguous names are an error."""
    if isinstance(ref, int) or (isinstance(ref, str) and ref.strip().isdigit()):
        return get_row(svc, int(ref), case_id)
    key = norm_name(str(ref))
    if not key:
        raise AtlasError("Empty entity reference.")
    rows = [r for r in svc.db.query("SELECT * FROM entities WHERE case_id = ? AND merged_into IS NULL", (case_id,))
            if r["norm_name"] == key or key in [norm_name(a) for a in jload(r["aliases"], [])]]
    if not rows:
        raise NotFound(f"No entity named {ref!r} in case {case_id}: create it with entity_upsert first.")
    if len(rows) > 1:
        listed = ", ".join("%s:%s" % (r["id"], r["type"]) for r in rows)
        raise AtlasError(f"{ref!r} matches several entities ({listed}): use the id.")
    return rows[0]


def attribute_view(svc, attrs: dict) -> dict:
    out = {}
    for key, a in attrs.items():
        ids = [int(i) for i in a.get("source_ids", [])]
        active = [i for i in ids if (s := svc.db.one("SELECT retracted FROM sources WHERE id = ?", (i,))) and not s["retracted"]]
        out[key] = {**a, "source_ids": ids, "active_source_ids": active,
                    "supported": (bool(active) if ids else None), "flag": ("unsupported" if ids and not active else "unsourced" if not ids else "")}
    return out


def view(svc, row, *, detail: bool = False) -> dict[str, Any]:
    counts = svc.db.one(
        "SELECT COUNT(*) c FROM relations WHERE (subject_id = ? OR object_id = ?) AND manual_status != 'retracted'",
        (row["id"], row["id"]))["c"]
    sources = svc.db.one(
        """SELECT COUNT(DISTINCT e.source_id) c FROM evidence e JOIN sources s ON s.id = e.source_id
           WHERE s.retracted = 0 AND (e.entity_id = ? OR e.relation_id IN
             (SELECT id FROM relations WHERE subject_id = ? OR object_id = ?))""", (row["id"],) * 3)["c"]
    out = {
        "id": row["id"], "case_id": row["case_id"], "type": row["type"], "name": row["name"],
        "aliases": jload(row["aliases"], []), "description": row["description"],
        "attributes": attribute_view(svc, jload(row["attributes"], {})),
        "lat": row["lat"], "lon": row["lon"], "geo_precision": row["geo_precision"],
        "date_start": row["date_start"], "date_end": row["date_end"], "wikidata_qid": row["wikidata_qid"],
        "private_person": bool(row["private_person"]), "public_figure": bool(row["public_figure"]),
        "merged_into": row["merged_into"], "relation_count": counts, "source_count": sources, "ref": entity_ref(row["id"]),
    }
    if not detail:
        out["attributes"] = {k: v["value"] for k, v in out["attributes"].items()}
    return out


def _coerce_attributes(svc, case_id: int, raw: dict[str, Any], observed: str | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, spec in (raw or {}).items():
        key = str(key).strip()
        if not key:
            raise AtlasError("Attribute names cannot be empty.")
        if isinstance(spec, dict) and "value" in spec:
            value = spec["value"]
            ids = spec.get("source_ids") or ([spec["source_id"]] if spec.get("source_id") is not None else [])
            entry = {"value": value, "source_ids": [int(i) for i in ids],
                     "quote": str(spec.get("quote") or "")[:1000], "locator": str(spec.get("locator") or "")[:200],
                     "valid_from": normalize(spec.get("valid_from")), "valid_to": normalize(spec.get("valid_to")),
                     "observed_at": normalize(spec.get("observed_at")) or observed}
        else:
            entry = {"value": spec, "source_ids": [], "quote": "", "locator": "", "valid_from": None, "valid_to": None,
                     "observed_at": observed}
        for sid in entry["source_ids"]:
            row = svc.db.one("SELECT case_id, retracted FROM sources WHERE id = ?", (sid,))
            if row is None or row["case_id"] != case_id:
                raise AtlasError(f"Attribute {key!r}: source {sid} is not a source of case {case_id}.")
            if row["retracted"]:
                raise AtlasError(f"Attribute {key!r}: source {sid} is retracted.")
        out[key[:80]] = entry
    return out


def _geo(lat, lon, precision):
    if lat is None and lon is None:
        return None, None, precision
    if lat is None or lon is None:
        raise AtlasError("Give both lat and lon, or neither.")
    if not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
        raise AtlasError("lat must be within -90..90 and lon within -180..180.")
    return float(lat), float(lon), (precision or "manual")


def upsert(svc, *, case_id: int, entity_id: int | None = None, type: str | None = None, name: str | None = None,
           aliases: list[str] | None = None, remove_aliases: list[str] | None = None, description: str | None = None,
           attributes: dict[str, Any] | None = None, remove_attributes: list[str] | None = None,
           lat: float | None = None, lon: float | None = None, geo_precision: str | None = None,
           date_start: str | None = None, date_end: str | None = None, wikidata_qid: str | None = None,
           private_person: bool | None = None, public_figure: bool | None = None, run_id: int | None = None) -> dict:
    cases_mod.get_row(svc, case_id)
    if type is not None and type not in TYPES:
        raise AtlasError(f"type must be one of {', '.join(TYPES)}.")
    if wikidata_qid not in (None, "") and not _QID.match(str(wikidata_qid)):
        raise AtlasError("wikidata_qid must look like Q42.")
    existing = None
    if entity_id is not None:
        existing = get_row(svc, entity_id, case_id)
        if existing["merged_into"] is not None:
            raise AtlasError(f"Entity {entity_id} was merged into {existing['merged_into']}; edit that one.")
    elif name:
        key = norm_name(name)
        for r in svc.db.query("SELECT * FROM entities WHERE case_id = ? AND merged_into IS NULL AND (type = ? OR ? IS NULL)",
                              (case_id, type, type)):
            if r["norm_name"] == key or key in [norm_name(a) for a in jload(r["aliases"], [])]:
                existing = r
                break
    now = svc.clock()
    observed = None
    attrs_in = _coerce_attributes(svc, case_id, attributes or {}, observed)
    lat_v, lon_v, prec_v = _geo(lat, lon, geo_precision)
    if existing is None:
        if not name or not name.strip():
            raise AtlasError("A new entity needs a name.")
        etype = type or "concept"
        is_public = bool(public_figure)
        if private_person is None:
            private = (etype == "person") and not is_public
        else:
            private = bool(private_person)
        if public_figure and private_person:
            raise AtlasError("An entity cannot be both a public figure and a private person.")
        attr_store = {k: {kk: vv for kk, vv in v.items() if kk not in ("quote", "locator")} for k, v in attrs_in.items()}
        cursor = svc.db.execute(
            """INSERT INTO entities(case_id, type, name, norm_name, aliases, description, attributes, lat, lon, geo_precision,
               date_start, date_end, wikidata_qid, private_person, public_figure, created_ts, updated_ts, run_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (case_id, etype, name.strip()[:300], norm_name(name), jdump(clean_list(aliases)), (description or "").strip(),
             jdump(attr_store), lat_v, lon_v, prec_v or "", normalize(date_start), normalize(date_end), wikidata_qid or "",
             int(private), int(is_public), now, now, run_id))
        eid = int(cursor.lastrowid)
        _attribute_evidence(svc, case_id, eid, attrs_in, run_id)
        history.record(svc, case_id, "entity.created", "entity", eid, f"Entity created: {name.strip()[:80]} ({etype})")
        dups = _quick_duplicates(svc, case_id, eid)
        return {"created": True, "entity": view(svc, get_row(svc, eid), detail=True), "possible_duplicates": dups,
                "private_person": bool(private)}
    # ---- update
    before = view(svc, existing, detail=True)
    sets: dict[str, Any] = {}
    alias_list = jload(existing["aliases"], [])
    if name and name.strip() and name.strip() != existing["name"]:
        alias_list = clean_list([*alias_list, existing["name"]])
        sets["name"], sets["norm_name"] = name.strip()[:300], norm_name(name)
    if aliases:
        alias_list = clean_list([*alias_list, *aliases])
    if remove_aliases:
        drop = {norm_name(a) for a in remove_aliases}
        alias_list = [a for a in alias_list if norm_name(a) not in drop]
    alias_list = [a for a in alias_list if norm_name(a) != (sets.get("norm_name") or existing["norm_name"])]
    if alias_list != jload(existing["aliases"], []):
        sets["aliases"] = jdump(alias_list)
    if type is not None and type != existing["type"]:
        sets["type"] = type
        if private_person is None and public_figure is None:
            sets["private_person"] = int(type == "person" and not existing["public_figure"])
    if description is not None and description.strip() != existing["description"]:
        sets["description"] = description.strip()
    if lat_v is not None:
        sets.update(lat=lat_v, lon=lon_v, geo_precision=prec_v)
    elif geo_precision is not None:
        sets["geo_precision"] = geo_precision
    if date_start is not None:
        sets["date_start"] = normalize(date_start)
    if date_end is not None:
        sets["date_end"] = normalize(date_end)
    if wikidata_qid is not None:
        sets["wikidata_qid"] = wikidata_qid
    if public_figure is not None:
        sets["public_figure"] = int(public_figure)
        if private_person is None:
            sets["private_person"] = int(not public_figure and (sets.get("type", existing["type"]) == "person"))
    if private_person is not None:
        if private_person and (public_figure or (public_figure is None and existing["public_figure"] and "public_figure" not in sets)):
            if public_figure is None:
                sets["public_figure"] = 0
            else:
                raise AtlasError("An entity cannot be both a public figure and a private person.")
        sets["private_person"] = int(private_person)
    attrs = jload(existing["attributes"], {})
    changed_attrs: list[str] = []
    for key, entry in attrs_in.items():
        old = attrs.get(key)
        stored = {k: v for k, v in entry.items() if k not in ("quote", "locator")}
        if old and old.get("value") == entry["value"]:
            stored["source_ids"] = sorted({*old.get("source_ids", []), *entry["source_ids"]})
        elif old:  # the value changed: evidence of the old value with no ACH rating goes away
            svc.db.execute("DELETE FROM evidence WHERE entity_id = ? AND attribute = ? AND id NOT IN (SELECT evidence_id FROM ach_ratings)",
                           (existing["id"], key))
        attrs[key] = stored
        changed_attrs.append(key)
    for key in remove_attributes or []:
        if attrs.pop(key, None) is not None:
            changed_attrs.append(key)
            svc.db.execute("DELETE FROM evidence WHERE entity_id = ? AND attribute = ? AND id NOT IN (SELECT evidence_id FROM ach_ratings)",
                           (existing["id"], key))
    if changed_attrs:
        sets["attributes"] = jdump(attrs)
    if not sets:
        return {"created": False, "updated": False, "entity": before, "changed": []}
    sets["updated_ts"] = now
    svc.db.execute(f"UPDATE entities SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", [*sets.values(), existing["id"]])
    _attribute_evidence(svc, case_id, existing["id"], attrs_in, run_id)
    after = view(svc, get_row(svc, existing["id"]), detail=True)
    changed = sorted({k for k in sets if k not in ("updated_ts", "norm_name")} | set())
    history.record(svc, case_id, "entity.updated", "entity", existing["id"],
                   f"Entity {existing['id']} updated: {', '.join(changed)}",
                   {k: before.get(k) for k in changed if k in before}, {k: after.get(k) for k in changed if k in after})
    return {"created": False, "updated": True, "entity": after, "changed": changed,
            "private_person": after["private_person"]}


def _attribute_evidence(svc, case_id: int, entity_id: int, attrs_in: dict, run_id: int | None) -> list[int]:
    made = []
    for key, entry in attrs_in.items():
        for sid in entry["source_ids"]:
            dup = svc.db.one("SELECT id FROM evidence WHERE entity_id = ? AND attribute = ? AND source_id = ? AND quote = ?",
                             (entity_id, key, sid, entry["quote"]))
            if dup:
                continue
            c = svc.db.execute(
                "INSERT INTO evidence(case_id, entity_id, attribute, source_id, quote, locator, observed_at, created_ts, run_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (case_id, entity_id, key, sid, entry["quote"], entry["locator"], entry["observed_at"], svc.clock(), run_id))
            made.append(int(c.lastrowid))
    return made


def delete(svc, entity_id: int, confirm: bool) -> dict:
    row = get_row(svc, entity_id)
    if not confirm:
        raise AtlasError("Pass confirm=true to delete the entity (merge it instead if it duplicates another).")
    rels = svc.db.one("SELECT COUNT(*) c FROM relations WHERE subject_id = ? OR object_id = ?", (entity_id, entity_id))["c"]
    if rels:
        raise AtlasError(f"Entity {entity_id} is part of {rels} relation(s): retract or delete them first, or merge the entity.")
    with svc.db.transaction() as conn:
        conn.execute("DELETE FROM ach_ratings WHERE evidence_id IN (SELECT id FROM evidence WHERE entity_id = ?)", (entity_id,))
        conn.execute("DELETE FROM evidence WHERE entity_id = ?", (entity_id,))
        conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
    history.record(svc, row["case_id"], "entity.deleted", "entity", entity_id, f"Entity deleted: {row['name']}",
                   before={"name": row["name"], "type": row["type"]})
    return {"deleted": True, "entity_id": entity_id}


def get(svc, entity_id: int, *, as_of: str | None = None, include_retracted: bool = False) -> dict:
    from . import relations as relations_mod
    row = get_row(svc, entity_id)
    out = view(svc, row, detail=True)
    views = relations_mod.list_views(svc, row["case_id"], entity_id=entity_id, as_of=as_of, include_retracted=include_retracted)
    out["relations"] = [{**r, "direction": "out" if r["subject_id"] == entity_id else "in"} for r in views]
    out["as_of"] = as_of
    out["evidence"] = [{"id": e["id"], "attribute": e["attribute"], "source_id": e["source_id"], "quote": clip(e["quote"], 200),
                        "locator": e["locator"]} for e in svc.db.query(
        "SELECT * FROM evidence WHERE entity_id = ? ORDER BY id LIMIT 50", (entity_id,))]
    out["history"] = history.list_history(svc, row["case_id"], target_type="entity", target_id=entity_id, limit=8)["items"]
    return out


def search(svc, *, query: str | None = None, case_id: int | None = None, type: str | None = None,
           limit: int = 20, cursor: str | None = None, include_merged: bool = False) -> dict:
    if case_id is not None:
        cases_mod.get_row(svc, case_id)
    params: list[Any] = []
    if query and query.strip():
        sql = ("SELECT e.* FROM entities_fts JOIN entities e ON e.id = entities_fts.rowid WHERE entities_fts MATCH ?")
        params.append(fts_query(query))
        order = " ORDER BY bm25(entities_fts)"
    else:
        sql = "SELECT e.* FROM entities e WHERE 1=1"
        order = " ORDER BY e.type, e.name COLLATE NOCASE"
    if case_id is not None:
        sql += " AND e.case_id = ?"
        params.append(case_id)
    if type:
        sql += " AND e.type = ?"
        params.append(type)
    if not include_merged:
        sql += " AND e.merged_into IS NULL"
    rows = [view(svc, r) for r in svc.db.query(sql + order + " LIMIT 500", params)]
    if query and query.strip() and not rows:  # prefix fallback on the normalised name (typos in the middle, accents)
        key = norm_name(query)
        like = "SELECT * FROM entities WHERE norm_name LIKE ?" + (" AND case_id = ?" if case_id is not None else "") \
            + (" AND type = ?" if type else "") + " AND merged_into IS NULL LIMIT 200"
        p2 = [f"%{key}%"] + ([case_id] if case_id is not None else []) + ([type] if type else [])
        rows = [view(svc, r) for r in svc.db.query(like, p2)]
    items, nxt = page(rows, limit, cursor)
    return {"items": items, "next_cursor": nxt, "total": len(rows)}


# ---------------- duplicates and merge ----------------

def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _pair_reasons(a, b) -> list[dict]:
    reasons = []
    na, nb = a["norm_name"], b["norm_name"]
    alias_a = {norm_name(x) for x in jload(a["aliases"], [])} | {na}
    alias_b = {norm_name(x) for x in jload(b["aliases"], [])} | {nb}
    if a["wikidata_qid"] and a["wikidata_qid"] == b["wikidata_qid"]:
        reasons.append({"kind": "same_qid", "detail": a["wikidata_qid"], "weight": 1.0})
    if na and na == nb:
        reasons.append({"kind": "same_name", "detail": a["name"], "weight": 0.9})
    else:
        shared = (alias_a & alias_b) - {""}
        if shared:
            reasons.append({"kind": "alias_overlap", "detail": sorted(shared)[0], "weight": 0.85})
    if a["lat"] is not None and b["lat"] is not None:
        km = _haversine_km((a["lat"], a["lon"]), (b["lat"], b["lon"]))
        if km <= 1.0:
            reasons.append({"kind": "close_coordinates", "detail": f"{km * 1000:.0f} m apart", "weight": 0.6})
    if na != nb and na and nb:
        ratio = difflib.SequenceMatcher(None, na, nb).ratio()
        if ratio >= 0.88:
            reasons.append({"kind": "similar_name", "detail": f"{ratio:.2f} similar", "weight": round(ratio * 0.7, 2)})
    return reasons


def suggest_duplicates(svc, case_id: int, *, min_score: float = 0.5, limit: int = 20) -> dict:
    """Pairs of same-type entities that may be the same thing, each with the reasons. Never merges anything."""
    cases_mod.get_row(svc, case_id)
    rows = svc.db.query("SELECT * FROM entities WHERE case_id = ? AND merged_into IS NULL", (case_id,))
    by_id = {r["id"]: r for r in rows}
    buckets: dict[tuple, set[int]] = defaultdict(set)
    for r in rows:
        tokens = {t for t in r["norm_name"].split() if len(t) >= 3} | {t for al in jload(r["aliases"], []) for t in norm_name(al).split() if len(t) >= 3}
        for t in tokens:
            buckets[(r["type"], "t", t)].add(r["id"])
        if r["wikidata_qid"]:
            buckets[(r["type"], "q", r["wikidata_qid"])].add(r["id"])
        if r["lat"] is not None:
            buckets[(r["type"], "g", round(r["lat"], 1), round(r["lon"], 1))].add(r["id"])
    pairs: set[tuple[int, int]] = set()
    for members in buckets.values():
        ids = sorted(members)
        for i, x in enumerate(ids):
            for y in ids[i + 1:]:
                pairs.add((x, y))
    out = []
    for x, y in pairs:
        a, b = by_id[x], by_id[y]
        reasons = _pair_reasons(a, b)
        if not reasons:
            continue
        score = min(0.99, max(r["weight"] for r in reasons) + 0.05 * (len(reasons) - 1))
        if score >= min_score:
            out.append({"a": _mini(a), "b": _mini(b), "score": round(score, 2), "reasons": [{k: v for k, v in r.items() if k != "weight"} for r in reasons]})
    out.sort(key=lambda p: (-p["score"], p["a"]["id"], p["b"]["id"]))
    return {"case_id": case_id, "suggestions": out[:limit], "total": len(out),
            "note": "Suggestions only: similarity is not identity. Merge explicitly with entity_merge after checking the evidence."}


def _mini(r) -> dict:
    return {"id": r["id"], "name": r["name"], "type": r["type"], "aliases": jload(r["aliases"], []),
            "wikidata_qid": r["wikidata_qid"], "private_person": bool(r["private_person"])}


def _quick_duplicates(svc, case_id: int, entity_id: int) -> list[dict]:
    me = get_row(svc, entity_id)
    out = []
    for r in svc.db.query("SELECT * FROM entities WHERE case_id = ? AND merged_into IS NULL AND id != ? AND type = ?",
                          (case_id, entity_id, me["type"])):
        reasons = _pair_reasons(me, r)
        if reasons:
            out.append({"id": r["id"], "name": r["name"], "reasons": [x["kind"] for x in reasons]})
    return out[:5]


def merge(svc, keep_id: int, merge_id: int, *, confirm: bool = False) -> dict:
    """Fold ``merge_id`` into ``keep_id``. Without confirm it only previews what would move."""
    from . import relations as relations_mod
    if keep_id == merge_id:
        raise AtlasError("Cannot merge an entity into itself.")
    keep, gone = get_row(svc, keep_id), get_row(svc, merge_id)
    if keep["case_id"] != gone["case_id"]:
        raise AtlasError("Both entities must belong to the same case.")
    if keep["merged_into"] is not None or gone["merged_into"] is not None:
        raise AtlasError("One of the entities was already merged into another.")
    case_id = keep["case_id"]
    rel_ids = [r["id"] for r in svc.db.query("SELECT id FROM relations WHERE subject_id = ? OR object_id = ?", (merge_id, merge_id))]
    k_attrs, g_attrs = jload(keep["attributes"], {}), jload(gone["attributes"], {})
    conflicts = [k for k, v in g_attrs.items() if k in k_attrs and k_attrs[k].get("value") != v.get("value")]
    plan = {"keep": _mini(keep), "merge": _mini(gone), "relations_moved": len(rel_ids), "attribute_conflicts": conflicts,
            "same_type": keep["type"] == gone["type"],
            "private_person_after": bool(keep["private_person"] or gone["private_person"])}
    if not confirm:
        return {"preview": True, "merged": False, **plan, "note": "Nothing changed. Call again with confirm=true to merge."}
    with svc.db.transaction() as conn:
        aliases = clean_list([*jload(keep["aliases"], []), gone["name"], *jload(gone["aliases"], [])])
        aliases = [a for a in aliases if norm_name(a) != keep["norm_name"]]
        for key, val in g_attrs.items():
            if key not in k_attrs:
                k_attrs[key] = val
            elif k_attrs[key].get("value") == val.get("value"):
                k_attrs[key]["source_ids"] = sorted({*k_attrs[key].get("source_ids", []), *val.get("source_ids", [])})
        conn.execute(
            """UPDATE entities SET aliases = ?, attributes = ?, description = CASE WHEN description = '' THEN ? ELSE description END,
               lat = COALESCE(lat, ?), lon = COALESCE(lon, ?), geo_precision = CASE WHEN lat IS NULL THEN ? ELSE geo_precision END,
               date_start = COALESCE(date_start, ?), date_end = COALESCE(date_end, ?),
               wikidata_qid = CASE WHEN wikidata_qid = '' THEN ? ELSE wikidata_qid END,
               private_person = ?, public_figure = ?, updated_ts = ? WHERE id = ?""",
            (jdump(aliases), jdump(k_attrs), gone["description"], gone["lat"], gone["lon"], gone["geo_precision"],
             gone["date_start"], gone["date_end"], gone["wikidata_qid"], int(keep["private_person"] or gone["private_person"]),
             0 if (keep["private_person"] or gone["private_person"]) else int(keep["public_figure"] or gone["public_figure"]),
             svc.clock(), keep_id))
        conn.execute("UPDATE relations SET subject_id = ? WHERE subject_id = ?", (keep_id, merge_id))
        conn.execute("UPDATE relations SET object_id = ? WHERE object_id = ?", (keep_id, merge_id))
        conn.execute("UPDATE evidence SET entity_id = ? WHERE entity_id = ?", (keep_id, merge_id))
        conn.execute("UPDATE entities SET merged_into = ?, updated_ts = ? WHERE id = ?", (keep_id, svc.clock(), merge_id))
    collapsed = relations_mod.dedupe_after_merge(svc, case_id, keep_id)
    history.record(svc, case_id, "entity.merged", "entity", keep_id, f"Entity {merge_id} ({gone['name']}) merged into {keep_id} ({keep['name']})",
                   {"merged": _mini(gone), "relations": rel_ids}, {"kept": keep_id, "collapsed_relations": collapsed})
    return {"preview": False, "merged": True, **plan, "collapsed_relations": collapsed,
            "entity": view(svc, get_row(svc, keep_id), detail=True)}
