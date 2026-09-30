"""Relations: subject - predicate - object, always backed by evidence.

The status is *derived* (never hand-typed into an inconsistent state):

    retracted    a person retracted the relation (sticky until restored)
    unsupported  no evidence from a non-retracted source is left
    disputed     a person marked it disputed
    confirmed    a person confirmed it AND at least two independent sources back it
    corroborated at least two independent sources (different origin; identical content counts once)
    claimed      one source

Retracting a source recomputes every relation it touched; relations that only it supported
become ``unsupported`` (kept, not deleted) and anything derived from them is flagged.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from . import cases as cases_mod
from . import dates, history
from . import entities as entities_mod
from .errors import AtlasError, NotFound
from .util import clip, iso_day, jdump, jload, norm_name, page

STATUSES = ("claimed", "corroborated", "confirmed", "disputed", "retracted", "unsupported")
SEED_PREDICATES = [
    # name, label, functional (one object at a time per subject), symmetric
    ("member_of", "member of", 0, 0), ("works_for", "works for", 0, 0), ("ceo_of", "CEO of", 1, 0),
    ("founded", "founded", 0, 0), ("owns", "owns", 0, 0), ("subsidiary_of", "subsidiary of", 1, 0),
    ("located_in", "located in", 0, 0), ("headquartered_in", "headquartered in", 1, 0), ("born_in", "born in", 1, 0),
    ("died_in", "died in", 1, 0), ("capital_of", "capital of", 1, 0), ("spouse_of", "spouse of", 1, 1),
    ("parent_of", "parent of", 0, 0), ("sibling_of", "sibling of", 0, 1), ("associated_with", "associated with", 0, 1),
    ("participated_in", "participated in", 0, 0), ("occurred_at", "occurred at", 1, 0), ("authored", "authored", 0, 0),
    ("mentions", "mentions", 0, 0), ("funded_by", "funded by", 0, 0), ("reports_to", "reports to", 1, 0),
    ("operates", "operates", 0, 0),
]


def seed_predicates(db) -> None:
    if db.one("SELECT COUNT(*) c FROM predicates")["c"] == 0:
        for name, label, functional, symmetric in SEED_PREDICATES:
            db.execute("INSERT OR IGNORE INTO predicates(name, label, functional, symmetric) VALUES (?,?,?,?)", (name, label, functional, symmetric))


def norm_predicate(text: str) -> str:
    value = re.sub(r"[\s\-]+", "_", (text or "").strip().lower())
    value = re.sub(r"[^\w]", "", value, flags=re.UNICODE).strip("_")
    if not value or len(value) > 60:
        raise AtlasError("predicate must be 1-60 characters of letters, digits or underscores (e.g. works_for).")
    return value


# ---------------- vocabulary ----------------

def predicates_list(svc) -> dict:
    return {"items": [{"name": r["name"], "label": r["label"] or r["name"].replace("_", " "), "functional": bool(r["functional"]),
                       "symmetric": bool(r["symmetric"]),
                       "uses": svc.db.one("SELECT COUNT(*) c FROM relations WHERE predicate = ?", (r["name"],))["c"]}
                      for r in svc.db.query("SELECT * FROM predicates ORDER BY name")]}


def predicate_upsert(svc, name: str, *, label: str = "", functional: bool = False, symmetric: bool = False) -> dict:
    key = norm_predicate(name)
    svc.db.execute(
        "INSERT INTO predicates(name, label, functional, symmetric) VALUES (?,?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET label = excluded.label, functional = excluded.functional, symmetric = excluded.symmetric",
        (key, label.strip()[:80], int(functional), int(symmetric)))
    history.record(svc, None, "predicate.saved", "predicate", None, f"Predicate {key} saved (functional={functional}, symmetric={symmetric})")
    return {"saved": key, **predicates_list(svc)}


def predicate_delete(svc, name: str) -> dict:
    key = norm_predicate(name)
    svc.db.execute("DELETE FROM predicates WHERE name = ?", (key,))
    history.record(svc, None, "predicate.deleted", "predicate", None, f"Predicate {key} removed from the vocabulary")
    return {"deleted": key, **predicates_list(svc)}


def _pred_info(svc, name: str) -> dict:
    row = svc.db.one("SELECT * FROM predicates WHERE name = ?", (name,))
    return {"in_vocabulary": row is not None, "functional": bool(row and row["functional"]), "symmetric": bool(row and row["symmetric"]),
            "label": (row["label"] if row and row["label"] else name.replace("_", " "))}


# ---------------- support ----------------

def evidence_rows(svc, relation_id: int) -> list:
    return svc.db.query(
        """SELECT e.*, s.retracted AS s_retracted, s.origin AS s_origin, s.content_hash AS s_hash, s.reliability AS s_rel,
                  s.credibility AS s_cred, s.title AS s_title, s.published_at AS s_pub, s.captured_at AS s_cap, s.text AS s_text
           FROM evidence e JOIN sources s ON s.id = e.source_id WHERE e.relation_id = ? ORDER BY e.id""", (relation_id,))


def independent_origins(rows) -> int:
    """Distinct origins among active evidence; two sources with identical content count once."""
    keys: set[str] = set()
    by_hash: dict[str, str] = {}
    for r in rows:
        if r["s_retracted"]:
            continue
        key = r["s_origin"] or f"source:{r['source_id']}"
        h = r["s_hash"]
        if h:
            key = by_hash.setdefault(h, key)
        keys.add(key)
    return len(keys)


def effective_status(manual: str, active: int, independent: int) -> str:
    if manual == "retracted":
        return "retracted"
    if active == 0:
        return "unsupported"
    if manual == "disputed":
        return "disputed"
    if manual == "confirmed" and independent >= 2:
        return "confirmed"
    return "corroborated" if independent >= 2 else "claimed"


def recompute_relation(svc, relation_id: int, reason: str = "", *, announce: bool = True) -> dict | None:
    row = svc.db.one("SELECT * FROM relations WHERE id = ?", (relation_id,))
    if row is None:
        return None
    ev = evidence_rows(svc, relation_id)
    active = sum(1 for r in ev if not r["s_retracted"])
    new = effective_status(row["manual_status"], active, independent_origins(ev))
    if new == row["status"]:
        return None
    svc.db.execute("UPDATE relations SET status = ?, updated_ts = ? WHERE id = ?", (new, svc.clock(), relation_id))
    history.record(svc, row["case_id"], "relation.status_changed", "relation", relation_id,
                   f"Relation {relation_id}: {row['status']} -> {new}" + (f" ({reason})" if reason else ""),
                   {"status": row["status"]}, {"status": new})
    if announce:
        svc.emit("atlas.relation.status_changed", {"case": row["case_id"], "relation": relation_id, "from": row["status"], "to": new})
    return {"id": relation_id, "from": row["status"], "to": new}


def recompute_case(svc, case_id: int, reason: str = "") -> list[dict]:
    out = []
    for r in svc.db.query("SELECT id FROM relations WHERE case_id = ?", (case_id,)):
        change = recompute_relation(svc, r["id"], reason)
        if change:
            out.append(change)
    return out


def recompute_for_source(svc, source_id: int, reason: str = "") -> list[dict]:
    out = []
    for r in svc.db.query("SELECT DISTINCT relation_id FROM evidence WHERE source_id = ? AND relation_id IS NOT NULL", (source_id,)):
        change = recompute_relation(svc, r["relation_id"], reason)
        if change:
            out.append(change)
    return out


def derived_chain(svc, case_id: int) -> dict[int, list[str]]:
    """relation id -> flags, for relations (transitively) derived from an unsupported/retracted/disputed one."""
    rows = {r["id"]: r for r in svc.db.query("SELECT id, status, derived_from FROM relations WHERE case_id = ?", (case_id,))}
    bad = {i for i, r in rows.items() if r["status"] in ("unsupported", "retracted", "disputed")}
    flags: dict[int, list[str]] = {}
    changed = True
    while changed:
        changed = False
        for rid, r in rows.items():
            for src in jload(r["derived_from"], []):
                if src in rows and src in bad:
                    kind = rows[src]["status"] if rows[src]["status"] in ("unsupported", "retracted", "disputed") else "flagged"
                    flag = f"derived_from_{kind}:{src}"
                    if flag not in flags.setdefault(rid, []):
                        flags[rid].append(flag)
                    if rid not in bad:
                        bad.add(rid)
                        changed = True
    return flags


def cascade_after_source_change(svc, source_id: int, reason: str = "") -> dict:
    src = svc.db.one("SELECT case_id FROM sources WHERE id = ?", (source_id,))
    case_id = src["case_id"]
    changes = recompute_for_source(svc, source_id, reason)
    flags = derived_chain(svc, case_id)
    ev_ids = [r["id"] for r in svc.db.query("SELECT id FROM evidence WHERE source_id = ?", (source_id,))]
    attrs = []
    for e in svc.db.query("SELECT id, name, attributes FROM entities WHERE case_id = ?", (case_id,)):
        for key, a in jload(e["attributes"], {}).items():
            ids = a.get("source_ids", [])
            if source_id in ids:
                active = [i for i in ids if not svc.db.one("SELECT retracted FROM sources WHERE id = ?", (i,))["retracted"]]
                attrs.append({"entity_id": e["id"], "attribute": key, "supported": bool(active)})
    hyps = sorted({r["hypothesis_id"] for r in svc.db.query(
        f"SELECT hypothesis_id FROM ach_ratings WHERE evidence_id IN ({','.join('?' * len(ev_ids)) or 'NULL'})", ev_ids)}) if ev_ids else []
    return {
        "relations_status_changed": changes,
        "relations_unsupported": [c["id"] for c in changes if c["to"] == "unsupported"],
        "derived_flagged": [{"relation_id": rid, "flags": f} for rid, f in sorted(flags.items())],
        "attributes": attrs,
        "ach": {"evidence_ids": ev_ids, "hypotheses_affected": hyps},
    }


# ---------------- views ----------------

def _label(svc, row) -> str:
    s = svc.db.one("SELECT name FROM entities WHERE id = ?", (row["subject_id"],))
    o = svc.db.one("SELECT name FROM entities WHERE id = ?", (row["object_id"],))
    return f"{s['name'] if s else '?'} {row['predicate'].replace('_', ' ')} {o['name'] if o else '?'}"


def _observed(row, ev) -> str | None:
    if row["observed_at"]:
        return row["observed_at"]
    best = None
    for r in ev:
        if r["s_retracted"]:
            continue
        d = r["observed_at"] or r["s_pub"] or (r["s_cap"] or "")[:10] or None
        if d and (best is None or dates.sort_key(d) > dates.sort_key(best)):
            best = d
    return best


def staleness(svc, row, ev) -> tuple[bool, str]:
    today = iso_day(svc.clock())
    """Stale means: still meant to be current (no end, or an end in the future) but last observed long ago.
    A fact that ended in the past is history, not stale: see ``ended``."""
    end = dates.end_day(row["valid_to"])
    now_day = date.fromisoformat(today)
    if end is None or end >= now_day:
        obs = _observed(row, ev)
        od = dates.start_day(obs) if obs else None
        if od is not None and (now_day - od).days > svc.config.stale_days:
            return True, f"last observed {obs}, not refreshed in over {svc.config.stale_days // 365 or 1} year(s)"
    return False, ""


def _evidence_item(svc, r, *, quote_chars: int = 300) -> dict:
    quote = r["quote"] or ""
    text = r["s_text"] or ""
    verified = None
    if quote and text:
        verified = re.sub(r"\s+", " ", quote).strip().lower() in re.sub(r"\s+", " ", text).lower()
    return {"id": r["id"], "source_id": r["source_id"], "cite": f"[S{r['source_id']}]", "source_title": clip(r["s_title"], 80),
            "grade": f"{r['s_rel']}{r['s_cred']}", "source_retracted": bool(r["s_retracted"]), "origin": r["s_origin"],
            "quote": clip(quote, quote_chars), "locator": r["locator"], "observed_at": r["observed_at"], "quote_in_source": verified}


def view(svc, row, *, with_evidence: bool = True, flags: dict | None = None, quote_chars: int = 300) -> dict[str, Any]:
    ev = evidence_rows(svc, row["id"])
    active = [r for r in ev if not r["s_retracted"]]
    subj = svc.db.one("SELECT id, name, type, private_person FROM entities WHERE id = ?", (row["subject_id"],))
    obj = svc.db.one("SELECT id, name, type, private_person FROM entities WHERE id = ?", (row["object_id"],))
    stale, reason = staleness(svc, row, ev)
    fl = list((flags if flags is not None else derived_chain(svc, row["case_id"])).get(row["id"], []))
    info = _pred_info(svc, row["predicate"])
    out = {
        "id": row["id"], "case_id": row["case_id"], "subject_id": row["subject_id"], "subject_name": subj["name"] if subj else "?",
        "subject_type": subj["type"] if subj else "", "predicate": row["predicate"], "predicate_label": info["label"],
        "in_vocabulary": info["in_vocabulary"], "functional": info["functional"],
        "object_id": row["object_id"], "object_name": obj["name"] if obj else "?", "object_type": obj["type"] if obj else "",
        "subject_private": bool(subj and subj["private_person"]), "object_private": bool(obj and obj["private_person"]),
        "label": _label(svc, row), "valid_from": row["valid_from"], "valid_to": row["valid_to"],
        "observed_at": _observed(row, ev), "status": row["status"], "manual_status": row["manual_status"],
        "manual_reason": row["manual_reason"], "confidence": row["confidence"], "notes": row["notes"],
        "derived_from": jload(row["derived_from"], []), "flags": fl,
        "evidence_count": len(active), "evidence_total": len(ev), "independent_sources": independent_origins(ev),
        "stale": stale, "stale_reason": reason,
        "ended": bool((e := dates.end_day(row["valid_to"])) is not None and e < date.fromisoformat(iso_day(svc.clock()))),
        "current": dates.contains(row["valid_from"], row["valid_to"], iso_day(svc.clock())),
        "cite": " ".join(sorted({f"[S{r['source_id']}]" for r in active}, key=lambda c: int(c[2:-1]))),
    }
    if with_evidence:
        out["evidence"] = [_evidence_item(svc, r, quote_chars=quote_chars) for r in ev]
    return out


def get_row(svc, relation_id: int, case_id: int | None = None):
    row = svc.db.one("SELECT * FROM relations WHERE id = ?", (relation_id,))
    if row is None or (case_id is not None and row["case_id"] != case_id):
        raise NotFound(f"Relation {relation_id} does not exist" + (f" in case {case_id}." if case_id else "."))
    return row


def list_views(svc, case_id: int, *, entity_id: int | None = None, statuses: list[str] | None = None, predicate: str | None = None,
               as_of: str | None = None, include_retracted: bool = True, with_evidence: bool = False,
               subject_id: int | None = None, object_id: int | None = None) -> list[dict]:
    sql, params = "SELECT * FROM relations WHERE case_id = ?", [case_id]
    if entity_id is not None:
        sql += " AND (subject_id = ? OR object_id = ?)"
        params += [entity_id, entity_id]
    if subject_id is not None:
        sql += " AND subject_id = ?"
        params.append(subject_id)
    if object_id is not None:
        sql += " AND object_id = ?"
        params.append(object_id)
    if predicate:
        sql += " AND predicate = ?"
        params.append(norm_predicate(predicate))
    if statuses:
        for s in statuses:
            if s not in STATUSES:
                raise AtlasError(f"status must be one of {', '.join(STATUSES)}.")
        sql += f" AND status IN ({','.join('?' * len(statuses))})"
        params += statuses
    elif not include_retracted:
        sql += " AND status != 'retracted'"
    flags = derived_chain(svc, case_id)
    out = []
    for r in svc.db.query(sql + " ORDER BY id", params):
        if as_of and not dates.contains(r["valid_from"], r["valid_to"], as_of):
            continue
        out.append(view(svc, r, with_evidence=with_evidence, flags=flags))
    return out


def get(svc, relation_id: int) -> dict:
    return view(svc, get_row(svc, relation_id))


def list_page(svc, case_id: int, *, subject: int | str | None = None, object: int | str | None = None,  # noqa: A002
              predicate: str | None = None, statuses: list[str] | None = None, as_of: str | None = None,
              include_retracted: bool = True, limit: int = 30, cursor: str | None = None) -> dict:
    cases_mod.get_row(svc, case_id)
    sid = entities_mod.resolve(svc, case_id, subject)["id"] if subject not in (None, "") else None
    oid = entities_mod.resolve(svc, case_id, object)["id"] if object not in (None, "") else None
    rows = list_views(svc, case_id, statuses=statuses, predicate=predicate, as_of=as_of, include_retracted=include_retracted,
                      with_evidence=True, subject_id=sid, object_id=oid)
    for r in rows:
        r["evidence"] = [{**e, "quote": clip(e["quote"], 160)} for e in r["evidence"][:3]]
    items, nxt = page(rows, limit, cursor)
    return {"case_id": case_id, "as_of": as_of, "items": items, "next_cursor": nxt, "total": len(rows)}


# ---------------- writes ----------------

def _check_evidence(svc, case_id: int, items: list[dict]) -> list[dict]:
    out = []
    for item in items:
        sid = item.get("source_id")
        if sid is None:
            raise AtlasError("Every evidence item needs a source_id.")
        src = svc.db.one("SELECT case_id, retracted FROM sources WHERE id = ?", (int(sid),))
        if src is None or src["case_id"] != case_id:
            raise AtlasError(f"Evidence source {sid} is not a source of case {case_id}: add it with source_add first.")
        if src["retracted"]:
            raise AtlasError(f"Evidence source {sid} is retracted and cannot back a relation.")
        quote, locator = str(item.get("quote") or "").strip(), str(item.get("locator") or "").strip()
        if not quote and not locator:
            raise AtlasError("Every evidence item needs a quote or a locator (page, section, timestamp).")
        out.append({"source_id": int(sid), "quote": quote[:2000], "locator": locator[:200],
                    "observed_at": dates.normalize(item.get("observed_at"))})
    return out


def _insert_evidence(svc, case_id: int, relation_id: int, items: list[dict], run_id: int | None) -> list[int]:
    ids = []
    for it in items:
        dup = svc.db.one("SELECT id FROM evidence WHERE relation_id = ? AND source_id = ? AND quote = ? AND locator = ?",
                         (relation_id, it["source_id"], it["quote"], it["locator"]))
        if dup:
            ids.append(dup["id"])
            continue
        c = svc.db.execute(
            "INSERT INTO evidence(case_id, relation_id, source_id, quote, locator, observed_at, created_ts, run_id) VALUES (?,?,?,?,?,?,?,?)",
            (case_id, relation_id, it["source_id"], it["quote"], it["locator"], it["observed_at"], svc.clock(), run_id))
        ids.append(int(c.lastrowid))
    return ids


def _find_existing(svc, case_id: int, s: int, p: str, o: int, vf, vt, symmetric: bool):
    rows = svc.db.query(
        "SELECT * FROM relations WHERE case_id = ? AND predicate = ? AND manual_status != 'retracted' AND "
        "((subject_id = ? AND object_id = ?) OR (? AND subject_id = ? AND object_id = ?))", (case_id, p, s, o, int(symmetric), o, s))
    for r in rows:
        if (r["valid_from"] or None) == (vf or None) and (r["valid_to"] or None) == (vt or None):
            return r
    return None


def _confidence(value: float | None, default: float = 0.5) -> float:
    if value is None:
        return default
    if not 0 <= float(value) <= 1:
        raise AtlasError("confidence must be between 0 and 1.")
    return round(float(value), 3)


def add(svc, *, case_id: int, subject: int | str, predicate: str, object: int | str,  # noqa: A002
        evidence: list[dict], valid_from: str | None = None, valid_to: str | None = None, observed_at: str | None = None,
        confidence: float | None = None, notes: str = "", derived_from: list[int] | None = None, run_id: int | None = None) -> dict:
    cases_mod.get_row(svc, case_id)
    if not evidence:
        raise AtlasError("A relation cannot exist without evidence: give at least one {source_id, quote|locator}.")
    subj, obj = entities_mod.resolve(svc, case_id, subject), entities_mod.resolve(svc, case_id, object)
    if subj["id"] == obj["id"]:
        raise AtlasError("A relation needs two different entities.")
    for e in (subj, obj):
        if e["merged_into"] is not None:
            raise AtlasError(f"Entity {e['id']} was merged into {e['merged_into']}: use that one.")
    pred = norm_predicate(predicate)
    vf, vt = dates.normalize(valid_from), dates.normalize(valid_to)
    if vf and vt and dates.start_day(vf) > dates.end_day(vt):  # type: ignore[operator]
        raise AtlasError("valid_from is after valid_to.")
    derived = sorted({int(i) for i in (derived_from or [])})
    for d in derived:
        get_row(svc, d, case_id)
    items = _check_evidence(svc, case_id, evidence)
    info = _pred_info(svc, pred)
    existing = _find_existing(svc, case_id, subj["id"], pred, obj["id"], vf, vt, info["symmetric"])
    if existing is not None:
        before = existing["status"]
        ids = _insert_evidence(svc, case_id, existing["id"], items, run_id)
        history.record(svc, case_id, "relation.evidence_added", "relation", existing["id"],
                       f"Evidence added to existing relation {existing['id']}", after={"evidence": ids})
        recompute_relation(svc, existing["id"], "evidence added")
        return {"created": False, "merged_into_existing": True, "relation": get(svc, existing["id"]), "evidence_ids": ids,
                "status_before": before}
    now = svc.clock()
    cursor = svc.db.execute(
        """INSERT INTO relations(case_id, subject_id, predicate, object_id, valid_from, valid_to, observed_at, status, confidence,
           notes, derived_from, created_ts, updated_ts, run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (case_id, subj["id"], pred, obj["id"], vf, vt, dates.normalize(observed_at), "unsupported", _confidence(confidence),
         notes.strip()[:2000], jdump(derived), now, now, run_id))
    rid = int(cursor.lastrowid)
    ids = _insert_evidence(svc, case_id, rid, items, run_id)
    recompute_relation(svc, rid, "created", announce=False)
    row = get_row(svc, rid)
    history.record(svc, case_id, "relation.added", "relation", rid, f"Relation added: {_label(svc, row)} [{row['status']}]",
                   after={"predicate": pred, "subject": subj["id"], "object": obj["id"], "evidence": ids})
    svc.emit("atlas.relation.added", {"case": case_id, "relation": rid, "predicate": pred, "subject": subj["id"], "object": obj["id"],
                                      "status": row["status"]})
    warn = []
    if not info["in_vocabulary"]:
        warn.append(f"predicate {pred!r} is not in the vocabulary (free text is allowed; add it in Settings to make it a standard one).")
    return {"created": True, "merged_into_existing": False, "relation": get(svc, rid), "evidence_ids": ids, "warnings": warn}


def update(svc, relation_id: int, *, subject: int | str | None = None, predicate: str | None = None,
           object: int | str | None = None, valid_from: str | None = None, valid_to: str | None = None,  # noqa: A002
           observed_at: str | None = None, confidence: float | None = None, notes: str | None = None,
           status: str | None = None, reason: str = "", add_evidence: list[dict] | None = None,
           remove_evidence: list[int] | None = None, derived_from: list[int] | None = None, clear_dates: list[str] | None = None) -> dict:
    row = get_row(svc, relation_id)
    case_id = row["case_id"]
    before = view(svc, row, with_evidence=False)
    sets: dict[str, Any] = {}
    if subject is not None:
        sets["subject_id"] = entities_mod.resolve(svc, case_id, subject)["id"]
    if object is not None:
        sets["object_id"] = entities_mod.resolve(svc, case_id, object)["id"]
    if sets.get("subject_id", row["subject_id"]) == sets.get("object_id", row["object_id"]):
        raise AtlasError("A relation needs two different entities.")
    if predicate is not None:
        sets["predicate"] = norm_predicate(predicate)
    for field, value in (("valid_from", valid_from), ("valid_to", valid_to), ("observed_at", observed_at)):
        if value is not None:
            sets[field] = dates.normalize(value)
    for field in clear_dates or []:
        if field not in ("valid_from", "valid_to", "observed_at"):
            raise AtlasError("clear_dates accepts valid_from, valid_to, observed_at.")
        sets[field] = None
    vf, vt = sets.get("valid_from", row["valid_from"]), sets.get("valid_to", row["valid_to"])
    if vf and vt and dates.start_day(vf) > dates.end_day(vt):  # type: ignore[operator]
        raise AtlasError("valid_from is after valid_to.")
    if confidence is not None:
        sets["confidence"] = _confidence(confidence)
    if notes is not None:
        sets["notes"] = notes.strip()[:2000]
    if derived_from is not None:
        ids = sorted({int(i) for i in derived_from})
        for d in ids:
            if d == relation_id:
                raise AtlasError("A relation cannot derive from itself.")
            get_row(svc, d, case_id)
        sets["derived_from"] = jdump(ids)
    if status is not None:
        if status not in ("disputed", "confirmed", "clear"):
            raise AtlasError("status can be set to disputed, confirmed or clear (claimed/corroborated/unsupported are derived from the evidence; use relation_retract to retract).")
        if row["manual_status"] == "retracted":
            raise AtlasError("The relation is retracted: restore it first (relation_retract action=restore).")
        if status == "confirmed":
            independent = independent_origins(evidence_rows(svc, relation_id))
            if independent < 2:
                raise AtlasError(f"Cannot confirm: only {independent} independent source(s) back this relation; corroboration needs at least 2 with a different origin.")
        sets["manual_status"] = "" if status == "clear" else status
        sets["manual_reason"] = reason.strip()[:500]
    added: list[int] = []
    removed: list[int] = []
    with svc.db.transaction() as conn:
        if add_evidence:
            added = _insert_evidence(svc, case_id, relation_id, _check_evidence(svc, case_id, add_evidence), None)
        for eid in remove_evidence or []:
            ev = conn.execute("SELECT id FROM evidence WHERE id = ? AND relation_id = ?", (eid, relation_id)).fetchone()
            if ev is None:
                raise AtlasError(f"Evidence {eid} does not belong to relation {relation_id}.")
            total = conn.execute("SELECT COUNT(*) c FROM evidence WHERE relation_id = ?", (relation_id,)).fetchone()["c"]
            if total <= 1:
                raise AtlasError("A relation cannot be left without evidence: add another item first, or retract/delete the relation.")
            conn.execute("DELETE FROM ach_ratings WHERE evidence_id = ?", (eid,))
            conn.execute("DELETE FROM evidence WHERE id = ?", (eid,))
            removed.append(eid)
        if sets:
            sets["updated_ts"] = svc.clock()
            conn.execute(f"UPDATE relations SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", [*sets.values(), relation_id])
    if not sets and not added and not removed:
        return {"updated": False, "relation": get(svc, relation_id), "changed": []}
    change = recompute_relation(svc, relation_id, reason or "edited")
    after = view(svc, get_row(svc, relation_id), with_evidence=False)
    changed = [k for k in after if k not in ("evidence_count", "evidence_total", "cite", "current", "ended", "stale", "stale_reason", "label",
                                              "subject_name", "object_name", "flags", "independent_sources", "observed_at")
               and before.get(k) != after.get(k)]
    history.record(svc, case_id, "relation.updated", "relation", relation_id,
                   f"Relation {relation_id} updated: {', '.join(changed) or 'evidence'}",
                   {k: before[k] for k in changed}, {**{k: after[k] for k in changed}, "evidence_added": added, "evidence_removed": removed})
    return {"updated": True, "relation": get(svc, relation_id), "changed": changed, "evidence_added": added,
            "evidence_removed": removed, "status_change": change}


def retract(svc, relation_id: int, *, reason: str = "", action: str = "retract") -> dict:
    row = get_row(svc, relation_id)
    if action not in ("retract", "restore"):
        raise AtlasError("action must be retract or restore.")
    if action == "retract":
        if not reason.strip():
            raise AtlasError("Say why the relation is retracted (reason).")
        svc.db.execute("UPDATE relations SET manual_status = 'retracted', manual_reason = ?, updated_ts = ? WHERE id = ?",
                       (reason.strip()[:500], svc.clock(), relation_id))
    else:
        if row["manual_status"] != "retracted":
            return {"changed": False, "relation": get(svc, relation_id)}
        svc.db.execute("UPDATE relations SET manual_status = '', manual_reason = '', updated_ts = ? WHERE id = ?", (svc.clock(), relation_id))
    change = recompute_relation(svc, relation_id, reason or action)
    flags = derive_flagged(svc, row["case_id"])
    history.record(svc, row["case_id"], f"relation.{action}ed", "relation", relation_id, f"Relation {relation_id} {action}ed: {reason.strip()[:120]}")
    return {"changed": True, "relation": get(svc, relation_id), "status_change": change, "derived_flagged": flags}


def derive_flagged(svc, case_id: int) -> list[dict]:
    return [{"relation_id": rid, "flags": f} for rid, f in sorted(derived_chain(svc, case_id).items())]


def delete(svc, relation_id: int, confirm: bool) -> dict:
    row = get_row(svc, relation_id)
    if not confirm:
        raise AtlasError("Pass confirm=true to delete the relation and its evidence (retract it instead to keep the history).")
    label = _label(svc, row)
    n = svc.db.one("SELECT COUNT(*) c FROM evidence WHERE relation_id = ?", (relation_id,))["c"]
    with svc.db.transaction() as conn:
        conn.execute("DELETE FROM ach_ratings WHERE evidence_id IN (SELECT id FROM evidence WHERE relation_id = ?)", (relation_id,))
        conn.execute("DELETE FROM evidence WHERE relation_id = ?", (relation_id,))
        conn.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
    for r in svc.db.query("SELECT id, derived_from FROM relations WHERE case_id = ?", (row["case_id"],)):
        d = jload(r["derived_from"], [])
        if relation_id in d:
            svc.db.execute("UPDATE relations SET derived_from = ? WHERE id = ?", (jdump([i for i in d if i != relation_id]), r["id"]))
    history.record(svc, row["case_id"], "relation.deleted", "relation", relation_id, f"Relation deleted: {label}", before={"evidence": n})
    return {"deleted": True, "relation_id": relation_id, "evidence_removed": n}


def dedupe_after_merge(svc, case_id: int, keeper_id: int) -> list[dict]:
    collapsed: list[dict] = []
    rows = svc.db.query("SELECT * FROM relations WHERE case_id = ? AND (subject_id = ? OR object_id = ?) ORDER BY id", (case_id, keeper_id, keeper_id))
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r["subject_id"] == r["object_id"]:
            svc.db.execute("UPDATE relations SET manual_status = 'retracted', manual_reason = 'self-loop after entity merge' WHERE id = ?", (r["id"],))
            collapsed.append({"relation_id": r["id"], "action": "retracted_self_loop"})
            continue
        groups[(r["subject_id"], r["predicate"], r["object_id"], r["valid_from"], r["valid_to"])].append(r)
    for members in groups.values():
        if len(members) < 2:
            continue
        keep, rest = members[0], members[1:]
        for dup in rest:
            svc.db.execute("UPDATE evidence SET relation_id = ? WHERE relation_id = ?", (keep["id"], dup["id"]))
            merged_from = sorted({*jload(keep["derived_from"], []), *jload(dup["derived_from"], [])} - {keep["id"], dup["id"]})
            svc.db.execute("UPDATE relations SET derived_from = ? WHERE id = ?", (jdump(merged_from), keep["id"]))
            for r in svc.db.query("SELECT id, derived_from FROM relations WHERE case_id = ?", (case_id,)):
                d = jload(r["derived_from"], [])
                if dup["id"] in d:
                    svc.db.execute("UPDATE relations SET derived_from = ? WHERE id = ?",
                                   (jdump(sorted({keep["id"] if i == dup["id"] else i for i in d} - {r["id"]})), r["id"]))
            svc.db.execute("DELETE FROM relations WHERE id = ?", (dup["id"],))
            collapsed.append({"kept": keep["id"], "removed": dup["id"], "action": "collapsed_duplicate"})
    for r in svc.db.query("SELECT id FROM relations WHERE case_id = ? AND (subject_id = ? OR object_id = ?)", (case_id, keeper_id, keeper_id)):
        recompute_relation(svc, r["id"], "entity merge")
    return collapsed
