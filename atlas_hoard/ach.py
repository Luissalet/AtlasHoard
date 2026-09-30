"""Analysis of competing hypotheses: hypotheses x evidence, inconsistency scores, diagnosticity and sensitivity.

The method works by *disproof*: the hypothesis with the least inconsistent evidence is the one that has
survived best so far. Atlas therefore reports it as "least contradicted so far" and never as proven.
"""

from __future__ import annotations

from typing import Any

from . import cases as cases_mod
from . import history
from .errors import AtlasError, NotFound
from .util import clip, page

RATINGS = ("CC", "C", "N", "I", "II", "NA")
_VALUE = {"CC": 2, "C": 1, "N": 0, "I": -1, "II": -2}
_PENALTY = {"I": 1.0, "II": 2.0}
DISCLAIMER = ("ACH ranks hypotheses by how little evidence contradicts them. The top one is the least contradicted so far; "
              "it is not proven, and new evidence can change the order.")


def hyp_row(svc, hypothesis_id: int, case_id: int | None = None):
    row = svc.db.one("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,))
    if row is None or (case_id is not None and row["case_id"] != case_id):
        raise NotFound(f"Hypothesis {hypothesis_id} does not exist" + (f" in case {case_id}." if case_id else "."))
    return row


def hyp_view(row) -> dict:
    return {"id": row["id"], "case_id": row["case_id"], "statement": row["statement"], "status": row["status"]}


def hypothesis(svc, *, case_id: int | None = None, hypothesis_id: int | None = None, statement: str | None = None,
               status: str | None = None, action: str = "upsert", confirm: bool = False) -> dict:
    if action == "delete":
        if hypothesis_id is None:
            raise AtlasError("hypothesis_id is required to delete.")
        row = hyp_row(svc, hypothesis_id)
        if not confirm:
            raise AtlasError("Pass confirm=true to delete the hypothesis and its ratings.")
        n = svc.db.one("SELECT COUNT(*) c FROM ach_ratings WHERE hypothesis_id = ?", (hypothesis_id,))["c"]
        svc.db.execute("DELETE FROM ach_ratings WHERE hypothesis_id = ?", (hypothesis_id,))
        svc.db.execute("DELETE FROM hypotheses WHERE id = ?", (hypothesis_id,))
        history.record(svc, row["case_id"], "hypothesis.deleted", "hypothesis", hypothesis_id, f"Hypothesis deleted: {clip(row['statement'], 80)}")
        return {"deleted": True, "hypothesis_id": hypothesis_id, "ratings_removed": n}
    if action != "upsert":
        raise AtlasError("action must be upsert or delete.")
    if status is not None and status not in ("open", "discarded"):
        raise AtlasError("status must be open or discarded.")
    now = svc.clock()
    if hypothesis_id is None:
        if case_id is None:
            raise AtlasError("case_id is required to add a hypothesis.")
        cases_mod.get_row(svc, case_id)
        if not statement or not statement.strip():
            raise AtlasError("A hypothesis needs a statement.")
        c = svc.db.execute("INSERT INTO hypotheses(case_id, statement, status, created_ts, updated_ts) VALUES (?,?,?,?,?)",
                           (case_id, statement.strip()[:1000], status or "open", now, now))
        hid = int(c.lastrowid)
        history.record(svc, case_id, "hypothesis.added", "hypothesis", hid, f"Hypothesis H{hid}: {clip(statement, 80)}")
        return {"created": True, "hypothesis": hyp_view(hyp_row(svc, hid))}
    row = hyp_row(svc, hypothesis_id, case_id)
    sets = {}
    if statement is not None and statement.strip():
        sets["statement"] = statement.strip()[:1000]
    if status is not None:
        sets["status"] = status
    if not sets:
        return {"created": False, "updated": False, "hypothesis": hyp_view(row)}
    sets["updated_ts"] = now
    svc.db.execute(f"UPDATE hypotheses SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", [*sets.values(), hypothesis_id])
    history.record(svc, row["case_id"], "hypothesis.updated", "hypothesis", hypothesis_id, f"Hypothesis H{hypothesis_id} updated",
                   {k: row[k] for k in sets if k != "updated_ts"}, {k: v for k, v in sets.items() if k != "updated_ts"})
    return {"created": False, "updated": True, "hypothesis": hyp_view(hyp_row(svc, hypothesis_id))}


# ---------------- evidence items ----------------

def evidence_items(svc, case_id: int, *, only_rated: bool = False) -> list[dict]:
    rows = svc.db.query(
        """SELECT e.*, s.retracted AS s_retracted, s.title AS s_title, s.reliability AS s_rel, s.credibility AS s_cred,
                  r.predicate AS r_pred, r.subject_id AS r_sub, r.object_id AS r_obj, r.status AS r_status,
                  ent.name AS ent_name,
                  (SELECT name FROM entities WHERE id = r.subject_id) AS sub_name, (SELECT name FROM entities WHERE id = r.object_id) AS obj_name,
                  (SELECT COUNT(*) FROM ach_ratings a WHERE a.evidence_id = e.id) AS n_ratings
           FROM evidence e JOIN sources s ON s.id = e.source_id LEFT JOIN relations r ON r.id = e.relation_id
           LEFT JOIN entities ent ON ent.id = e.entity_id WHERE e.case_id = ? ORDER BY e.id""", (case_id,))
    out = []
    for r in rows:
        if only_rated and not r["n_ratings"]:
            continue
        if r["relation_id"]:
            kind, context = "relation", f"{r['sub_name']} {str(r['r_pred']).replace('_', ' ')} {r['obj_name']}"
        elif r["entity_id"]:
            kind, context = "attribute", f"{r['ent_name']} · {r['attribute']}"
        else:
            kind, context = "case", "case evidence"
        out.append({"id": r["id"], "kind": kind, "context": context, "relation_id": r["relation_id"], "entity_id": r["entity_id"],
                    "attribute": r["attribute"], "source_id": r["source_id"], "cite": f"[S{r['source_id']}]",
                    "source_title": clip(r["s_title"], 60), "grade": f"{r['s_rel']}{r['s_cred']}", "quote": clip(r["quote"], 240),
                    "locator": r["locator"], "active": not r["s_retracted"], "ratings": r["n_ratings"]})
    return out


def rate(svc, *, hypothesis_id: int, evidence_id: int | None = None, evidence: dict | None = None, rating: str | None = None,
         note: str = "", action: str = "rate") -> dict:
    hyp = hyp_row(svc, hypothesis_id)
    case_id = hyp["case_id"]
    created_evidence = None
    if evidence_id is None:
        if not evidence:
            raise AtlasError("Give evidence_id (an evidence item of the case) or evidence {source_id, quote|locator} to create a case-level item.")
        from . import relations as relations_mod
        items = relations_mod._check_evidence(svc, case_id, [evidence])
        it = items[0]
        c = svc.db.execute("INSERT INTO evidence(case_id, source_id, quote, locator, observed_at, created_ts) VALUES (?,?,?,?,?,?)",
                           (case_id, it["source_id"], it["quote"], it["locator"], it["observed_at"], svc.clock()))
        evidence_id = created_evidence = int(c.lastrowid)
        history.record(svc, case_id, "evidence.added", "evidence", evidence_id, f"Case-level evidence E{evidence_id} added for ACH")
    ev = svc.db.one("SELECT * FROM evidence WHERE id = ?", (evidence_id,))
    if ev is None or ev["case_id"] != case_id:
        raise NotFound(f"Evidence {evidence_id} does not exist in case {case_id}.")
    if action in ("delete", "clear"):
        svc.db.execute("DELETE FROM ach_ratings WHERE hypothesis_id = ? AND evidence_id = ?", (hypothesis_id, evidence_id))
        history.record(svc, case_id, "ach.cleared", "hypothesis", hypothesis_id, f"ACH rating cleared: H{hypothesis_id} x E{evidence_id}")
        return {"cleared": True, "hypothesis_id": hypothesis_id, "evidence_id": evidence_id}
    if action != "rate":
        raise AtlasError("action must be rate or delete.")
    rating = (rating or "").strip().upper()
    if rating not in RATINGS:
        raise AtlasError(f"rating must be one of {', '.join(RATINGS)} (CC very consistent, C consistent, N neutral, I inconsistent, II very inconsistent, NA not applicable).")
    old = svc.db.one("SELECT rating FROM ach_ratings WHERE hypothesis_id = ? AND evidence_id = ?", (hypothesis_id, evidence_id))
    svc.db.execute(
        "INSERT INTO ach_ratings(hypothesis_id, evidence_id, rating, note, updated_ts) VALUES (?,?,?,?,?) "
        "ON CONFLICT(hypothesis_id, evidence_id) DO UPDATE SET rating = excluded.rating, note = excluded.note, updated_ts = excluded.updated_ts",
        (hypothesis_id, evidence_id, rating, note.strip()[:500], svc.clock()))
    history.record(svc, case_id, "ach.rated", "hypothesis", hypothesis_id, f"ACH: H{hypothesis_id} x E{evidence_id} = {rating}",
                   {"rating": old["rating"] if old else None}, {"rating": rating})
    m = matrix(svc, case_id)
    return {"rated": True, "hypothesis_id": hypothesis_id, "evidence_id": evidence_id, "rating": rating,
            "created_evidence_id": created_evidence, "least_contradicted": m["least_contradicted"], "note": m["note"]}


# ---------------- the matrix ----------------

def _scores(hyps: list[dict], ratings: dict[tuple[int, int], str], evidence_ids: list[int]) -> dict[int, float]:
    return {h["id"]: sum(_PENALTY.get(ratings.get((h["id"], e), ""), 0.0) for e in evidence_ids) for h in hyps}


def _leaders(scores: dict[int, float], rated: set[int]) -> list[int]:
    cand = {h: s for h, s in scores.items() if h in rated}
    if not cand:
        return []
    best = min(cand.values())
    return sorted(h for h, s in cand.items() if s == best)


def matrix(svc, case_id: int, *, include_unrated: bool = False) -> dict:
    cases_mod.get_row(svc, case_id)
    hyps = [hyp_view(r) for r in svc.db.query("SELECT * FROM hypotheses WHERE case_id = ? ORDER BY id", (case_id,))]
    items = evidence_items(svc, case_id, only_rated=not include_unrated)
    by_ev = {e["id"]: e for e in items}
    rows = svc.db.query(
        "SELECT a.* FROM ach_ratings a JOIN hypotheses h ON h.id = a.hypothesis_id WHERE h.case_id = ?", (case_id,))
    ratings = {(r["hypothesis_id"], r["evidence_id"]): r["rating"] for r in rows}
    notes = {(r["hypothesis_id"], r["evidence_id"]): r["note"] for r in rows}
    live = [h for h in hyps if h["status"] == "open"]
    active_ev = [e["id"] for e in items if e["active"]]
    scores = _scores(live, ratings, active_ev)
    rated_h = {h["id"] for h in live if any((h["id"], e) in ratings and ratings[(h["id"], e)] != "NA" for e in active_ev)}
    leaders = _leaders(scores, rated_h)
    # diagnosticity and sensitivity
    diag: dict[int, float] = {}
    pivotal: list[int] = []
    for e in items:
        vals = [_VALUE[ratings[(h["id"], e["id"])]] for h in live if ratings.get((h["id"], e["id"]), "NA") in _VALUE]
        d = (max(vals) - min(vals)) / 4 if len(vals) >= 2 else 0.0
        diag[e["id"]] = round(d, 2)
        if d > 0 and e["active"]:
            without = [x for x in active_ev if x != e["id"]]
            sc = _scores(live, ratings, without)
            rh = {h["id"] for h in live if any((h["id"], x) in ratings and ratings[(h["id"], x)] != "NA" for x in without)}
            if _leaders(sc, rh) != leaders:
                pivotal.append(e["id"])
    ranked = sorted(live, key=lambda h: (h["id"] not in rated_h, scores[h["id"]], h["id"]))
    hyp_out = []
    for rank, h in enumerate(ranked, start=1):
        rs = [ratings.get((h["id"], e)) for e in active_ev]
        hyp_out.append({**h, "score": scores[h["id"]], "inconsistent": sum(1 for r in rs if r in ("I", "II")),
                        "consistent": sum(1 for r in rs if r in ("CC", "C")), "rated": sum(1 for r in rs if r and r != "NA"),
                        "rank": rank if h["id"] in rated_h else None, "least_contradicted": h["id"] in leaders})
    hyp_out += [{**h, "score": None, "inconsistent": 0, "consistent": 0, "rated": 0, "rank": None, "least_contradicted": False}
                for h in hyps if h["status"] != "open"]
    if not hyps:
        note = "No hypotheses yet: add at least two competing explanations."
    elif not leaders:
        note = "No ratings yet: rate each piece of evidence against every hypothesis."
    else:
        names = ", ".join(f"H{i}" for i in leaders)
        if len(leaders) > 1:
            note = f"{names} are tied as the least contradicted so far (score {scores[leaders[0]]:g}); the evidence does not separate them."
        else:
            others = sorted(scores[h] for h in rated_h if h != leaders[0])
            margin = (others[0] - scores[leaders[0]]) if others else None
            note = f"{names} is the least contradicted so far (score {scores[leaders[0]]:g}" + (f", margin {margin:g}" if margin is not None else "") + "); this is not proof."
        if pivotal:
            note += " The ranking hinges on " + ", ".join(f"E{i}" for i in pivotal) + ": removing any one of them changes which hypothesis is least contradicted."
        elif leaders:
            note += " No single piece of evidence changes this ranking when removed."
        weak = [i for i, d in diag.items() if d == 0 and by_ev[i]["active"] and by_ev[i]["ratings"]]
        if weak:
            note += " " + ", ".join(f"E{i}" for i in weak[:8]) + (" does not" if len(weak[:8]) == 1 else " do not") + " discriminate between the hypotheses."
    return {
        "case_id": case_id, "hypotheses": hyp_out,
        "evidence": [{**e, "diagnosticity": diag.get(e["id"], 0.0), "diagnostic": diag.get(e["id"], 0.0) > 0, "pivotal": e["id"] in pivotal}
                     for e in items],
        "ratings": [{"hypothesis_id": h, "evidence_id": e, "rating": r, "note": notes[(h, e)],
                     "inactive": e in by_ev and not by_ev[e]["active"]} for (h, e), r in sorted(ratings.items()) if e in by_ev],
        "least_contradicted": leaders, "pivotal_evidence_ids": pivotal, "note": note, "disclaimer": DISCLAIMER,
        "scale": {"CC": "very consistent", "C": "consistent", "N": "neutral", "I": "inconsistent", "II": "very inconsistent", "NA": "not applicable"},
    }
