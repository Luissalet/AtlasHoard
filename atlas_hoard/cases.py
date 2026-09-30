"""Cases: the unit of work. A case holds a question, its sources, entities, relations and hypotheses."""

from __future__ import annotations

from typing import Any

from . import history
from .errors import AtlasError, NotFound
from .hoard_link.artifacts import ArtifactRef
from .util import clean_list, jdump, jload, page

STATUSES = ("open", "paused", "closed")


def case_ref(case_id: int) -> str:
    """``hoard://atlas/case/<id>``: how other apps point at a case."""
    return ArtifactRef("atlas", "case", str(case_id)).uri


def get_row(svc, case_id: int):
    row = svc.db.one("SELECT * FROM cases WHERE id = ?", (case_id,))
    if row is None:
        raise NotFound(f"Case {case_id} does not exist.")
    return row


def view(row) -> dict[str, Any]:
    return {
        "id": row["id"], "title": row["title"], "question": row["question"], "status": row["status"],
        "tags": jload(row["tags"], []), "summary": row["summary"], "open_questions": jload(row["open_questions"], []),
        "created_ts": row["created_ts"], "updated_ts": row["updated_ts"], "ref": case_ref(row["id"]),
    }


def create(svc, *, title: str, question: str = "", tags: list[str] | None = None, summary: str = "",
           open_questions: list[str] | None = None) -> dict:
    title = title.strip()
    if not title:
        raise AtlasError("A case needs a title.")
    now = svc.clock()
    cursor = svc.db.execute(
        "INSERT INTO cases(title, question, status, tags, summary, open_questions, created_ts, updated_ts) VALUES (?,?,?,?,?,?,?,?)",
        (title, question.strip(), "open", jdump(clean_list(tags)), summary.strip(), jdump(clean_list(open_questions, maxlen=400)), now, now))
    case_id = int(cursor.lastrowid)
    history.record(svc, case_id, "case.created", "case", case_id, f"Case created: {title}")
    svc.emit("atlas.case.created", {"case": case_id, "title": title[:80], "ref": case_ref(case_id)})
    return {"created": True, "case": view(get_row(svc, case_id))}


def update(svc, case_id: int, *, title: str | None = None, question: str | None = None, status: str | None = None,
           tags: list[str] | None = None, summary: str | None = None, open_questions: list[str] | None = None) -> dict:
    row = get_row(svc, case_id)
    before = view(row)
    sets: dict[str, Any] = {}
    if title is not None:
        if not title.strip():
            raise AtlasError("A case needs a title.")
        sets["title"] = title.strip()
    if question is not None:
        sets["question"] = question.strip()
    if status is not None:
        if status not in STATUSES:
            raise AtlasError(f"status must be one of {', '.join(STATUSES)}.")
        sets["status"] = status
    if tags is not None:
        sets["tags"] = jdump(clean_list(tags))
    if summary is not None:
        sets["summary"] = summary.strip()
    if open_questions is not None:
        sets["open_questions"] = jdump(clean_list(open_questions, maxlen=400))
    if not sets:
        return {"updated": False, "case": before, "changed": []}
    sets["updated_ts"] = svc.clock()
    svc.db.execute(f"UPDATE cases SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", [*sets.values(), case_id])
    after = view(get_row(svc, case_id))
    changed = [k for k in before if before[k] != after[k] and k != "updated_ts"]
    history.record(svc, case_id, "case.updated", "case", case_id, f"Case updated: {', '.join(changed)}",
                   {k: before[k] for k in changed}, {k: after[k] for k in changed})
    return {"updated": True, "case": after, "changed": changed}


def delete(svc, case_id: int, confirm: bool) -> dict:
    row = get_row(svc, case_id)
    if not confirm:
        raise AtlasError("Deleting a case removes all its sources, entities, relations, evidence and history. Pass confirm=true to do it.")
    counts = {t: svc.db.one(f"SELECT COUNT(*) c FROM {t} WHERE case_id = ?", (case_id,))["c"]
              for t in ("sources", "entities", "relations", "evidence", "hypotheses")}
    with svc.db.transaction() as conn:
        conn.execute("DELETE FROM ach_ratings WHERE hypothesis_id IN (SELECT id FROM hypotheses WHERE case_id = ?)", (case_id,))
        for table in ("evidence", "relations", "hypotheses", "entities", "sources", "enrichment_runs", "history"):
            conn.execute(f"DELETE FROM {table} WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
    history.record(svc, None, "case.deleted", "case", case_id, f"Case {case_id} deleted: {row['title']}", before=counts)
    return {"deleted": True, "case_id": case_id, "removed": counts}


def list_cases(svc, *, status: str | None = None, query: str | None = None, limit: int = 30, cursor: str | None = None) -> dict:
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if query:
        clauses.append("(title LIKE ? OR question LIKE ? OR tags LIKE ?)")
        params += [f"%{query}%"] * 3
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = svc.db.query(f"SELECT * FROM cases {where} ORDER BY updated_ts DESC, id DESC", params)
    items = []
    for r in rows:
        v = view(r)
        v["counts"] = counts(svc, r["id"])
        items.append(v)
    out, nxt = page(items, limit, cursor)
    return {"items": out, "next_cursor": nxt, "total": len(items)}


def counts(svc, case_id: int) -> dict:
    one = lambda sql: svc.db.one(sql, (case_id,))["c"]  # noqa: E731
    rel = {r["status"]: r["c"] for r in svc.db.query(
        "SELECT status, COUNT(*) c FROM relations WHERE case_id = ? GROUP BY status", (case_id,))}
    return {
        "sources": one("SELECT COUNT(*) c FROM sources WHERE case_id = ? AND retracted = 0"),
        "sources_retracted": one("SELECT COUNT(*) c FROM sources WHERE case_id = ? AND retracted = 1"),
        "entities": one("SELECT COUNT(*) c FROM entities WHERE case_id = ? AND merged_into IS NULL"),
        "relations": sum(rel.values()), "relations_by_status": rel,
        "hypotheses": one("SELECT COUNT(*) c FROM hypotheses WHERE case_id = ?"),
    }


def get(svc, case_id: int) -> dict:
    """Case plus its dashboard: counts, what needs attention and recent activity."""
    from . import relations as relations_mod
    from . import timeline as timeline_mod
    row = get_row(svc, case_id)
    out = view(row)
    out["counts"] = counts(svc, case_id)
    unsupported = [r for r in relations_mod.list_views(svc, case_id, statuses=["unsupported"])][:20]
    disputed = [r for r in relations_mod.list_views(svc, case_id, statuses=["disputed"])][:20]
    stale = [r for r in relations_mod.list_views(svc, case_id, include_retracted=False) if r["stale"]][:20]
    contradictions = timeline_mod.contradictions(svc, case_id)
    orphans = [dict(id=e["id"], name=e["name"]) for e in svc.db.query(
        """SELECT id, name FROM entities WHERE case_id = ? AND merged_into IS NULL AND id NOT IN
           (SELECT subject_id FROM relations WHERE case_id = ? UNION SELECT object_id FROM relations WHERE case_id = ?)
           LIMIT 20""", (case_id, case_id, case_id))]
    unrated = [h["id"] for h in svc.db.query(
        "SELECT id FROM hypotheses WHERE case_id = ? AND id NOT IN (SELECT hypothesis_id FROM ach_ratings)", (case_id,))]
    out["dashboard"] = {
        "open_questions": out["open_questions"],
        "unsupported_relations": [{"id": r["id"], "label": r["label"]} for r in unsupported],
        "disputed_relations": [{"id": r["id"], "label": r["label"]} for r in disputed],
        "stale_facts": [{"id": r["id"], "label": r["label"], "reason": r["stale_reason"]} for r in stale],
        "contradictions": contradictions,
        "entities_without_relations": orphans,
        "hypotheses_without_ratings": unrated,
    }
    out["recent_enrichment_runs"] = [
        {"id": r["id"], "enricher": r["enricher"], "entity_id": r["entity_id"], "status": r["status"], "ts": r["created_ts"]}
        for r in svc.db.query("SELECT * FROM enrichment_runs WHERE case_id = ? ORDER BY id DESC LIMIT 5", (case_id,))]
    out["recent_history"] = history.list_history(svc, case_id, limit=8)["items"]
    return out
