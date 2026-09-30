"""Per-case change history: who (caller), what, when, with before/after for edits.

The caller comes from a context variable set by the agent route (the ``caller``
field of ``POST /api/agent/call``) or by the UI routes (``"ui"``), so no
function below has to thread it through.
"""

from __future__ import annotations

import contextvars
from typing import Any

from .util import jdump, jload, page

CALLER: contextvars.ContextVar[str] = contextvars.ContextVar("atlas_caller", default="system")


def set_caller(name: str | None) -> contextvars.Token:
    return CALLER.set((name or "agent").strip()[:80] or "agent")


def record(svc, case_id: int | None, action: str, target_type: str = "", target_id: int | None = None,
           summary: str = "", before: Any = None, after: Any = None) -> int:
    cursor = svc.db.execute(
        "INSERT INTO history(case_id, ts, caller, action, target_type, target_id, summary, before, after) VALUES (?,?,?,?,?,?,?,?,?)",
        (case_id, svc.clock(), CALLER.get(), action, target_type, target_id, summary[:400],
         jdump(before) if before is not None else None, jdump(after) if after is not None else None),
    )
    return int(cursor.lastrowid)


def _row(r) -> dict:
    return {"id": r["id"], "case_id": r["case_id"], "ts": r["ts"], "caller": r["caller"], "action": r["action"],
            "target_type": r["target_type"], "target_id": r["target_id"], "summary": r["summary"],
            "before": jload(r["before"], None), "after": jload(r["after"], None)}


def list_history(svc, case_id: int | None = None, *, target_type: str | None = None, target_id: int | None = None,
                 action: str | None = None, limit: int = 30, cursor: str | None = None) -> dict:
    clauses, params = [], []
    if case_id is not None:
        clauses.append("case_id = ?")
        params.append(case_id)
    if target_type:
        clauses.append("target_type = ?")
        params.append(target_type)
    if target_id is not None:
        clauses.append("target_id = ?")
        params.append(target_id)
    if action:
        clauses.append("action LIKE ?")
        params.append(action.replace("%", "") + "%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = [_row(r) for r in svc.db.query(f"SELECT * FROM history {where} ORDER BY id DESC LIMIT 2000", params)]
    items, nxt = page(rows, limit, cursor)
    return {"case_id": case_id, "items": items, "next_cursor": nxt, "total": len(rows)}
