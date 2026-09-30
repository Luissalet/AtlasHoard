"""Running and undoing enrichment. Every run is recorded with its inputs; every row it creates carries its run id,
so ``undo`` removes exactly that and restores what it changed."""

from __future__ import annotations

from typing import Any

from . import cases as cases_mod
from . import entities as entities_mod
from . import ethics, history
from . import relations as relations_mod
from .enrichers import ENRICHERS
from .enrichers.base import RunContext
from .errors import AtlasError, NotFound
from .util import jdump, jload

PARAM_KEYS = ("qid", "language", "query", "url", "title", "note", "reliability", "credibility", "overwrite", "dry_run", "apps",
              "limit", "include_private")


def run(svc, *, case_id: int | None = None, enricher: str, entity_id: int | None = None, **params: Any) -> dict:
    if enricher not in ENRICHERS:
        raise AtlasError(f"Unknown enricher {enricher!r}: use one of {', '.join(ENRICHERS)}.")
    entity = None
    if entity_id is not None:
        entity = entities_mod.get_row(svc, entity_id)
        if case_id is not None and entity["case_id"] != case_id:
            raise AtlasError(f"Entity {entity_id} is not in case {case_id}.")
        case_id = entity["case_id"]
        if entity["merged_into"] is not None:
            raise AtlasError(f"Entity {entity_id} was merged into {entity['merged_into']}.")
    if case_id is None:
        raise AtlasError("Give case_id or entity_id.")
    cases_mod.get_row(svc, case_id)
    ethics.check_enrichable(entity, enricher)
    inputs = {k: v for k, v in params.items() if k in PARAM_KEYS and v not in (None, "")}
    cur = svc.db.execute("INSERT INTO enrichment_runs(case_id, enricher, entity_id, inputs, created, status, created_ts) VALUES (?,?,?,?,?,?,?)",
                         (case_id, enricher, entity_id, jdump(inputs), "{}", "running", svc.clock()))
    run_id = int(cur.lastrowid)
    ctx = RunContext(svc, case_id, run_id, entity, inputs)
    try:
        result = ENRICHERS[enricher](ctx)
    except Exception as error:
        _undo_rows(svc, run_id, restore=ctx.changes())
        svc.db.execute("UPDATE enrichment_runs SET status = 'error', note = ? WHERE id = ?", (f"{type(error).__name__}: {error}"[:500], run_id))
        raise
    changes = ctx.changes()
    made = {t: [r["id"] for r in svc.db.query(f"SELECT id FROM {t} WHERE run_id = ?", (run_id,))]
            for t in ("sources", "entities", "relations", "evidence")}
    if not any(made.values()) and not changes:
        svc.db.execute("DELETE FROM enrichment_runs WHERE id = ?", (run_id,))
        return {**result, "run_id": None, "enricher": enricher, "created": made}
    svc.db.execute("UPDATE enrichment_runs SET created = ?, status = 'ok', note = ? WHERE id = ?",
                   (jdump({**made, "entity_changes": changes}), "; ".join(ctx.notes)[:500], run_id))
    history.record(svc, case_id, "enrichment.run", "enrichment", run_id,
                   f"{enricher} run {run_id}" + (f" on entity {entity_id}" if entity_id else ""), after={"created": {k: len(v) for k, v in made.items()}})
    return {**result, "run_id": run_id, "enricher": enricher, "created": made, "undo": f"enrichment_undo(run_id={run_id})"}


def _undo_rows(svc, run_id: int, restore: list[dict]) -> dict:
    removed: dict[str, list[int]] = {"evidence": [], "relations": [], "sources": [], "entities": []}
    kept: dict[str, list] = {"relations": [], "sources": [], "entities": []}
    with svc.db.transaction() as conn:
        ev_ids = [r["id"] for r in conn.execute("SELECT id FROM evidence WHERE run_id = ?", (run_id,)).fetchall()]
        touched_rel = {r["relation_id"] for r in conn.execute(
            "SELECT DISTINCT relation_id FROM evidence WHERE run_id = ? AND relation_id IS NOT NULL", (run_id,)).fetchall()}
        for eid in ev_ids:
            conn.execute("DELETE FROM ach_ratings WHERE evidence_id = ?", (eid,))
            conn.execute("DELETE FROM evidence WHERE id = ?", (eid,))
        removed["evidence"] = ev_ids
        for r in conn.execute("SELECT id FROM relations WHERE run_id = ?", (run_id,)).fetchall():
            left = conn.execute("SELECT COUNT(*) c FROM evidence WHERE relation_id = ?", (r["id"],)).fetchone()["c"]
            if left == 0:
                conn.execute("DELETE FROM relations WHERE id = ?", (r["id"],))
                removed["relations"].append(r["id"])
                touched_rel.discard(r["id"])
            else:
                kept["relations"].append(r["id"])
        for r in conn.execute("SELECT id FROM sources WHERE run_id = ?", (run_id,)).fetchall():
            used = conn.execute("SELECT COUNT(*) c FROM evidence WHERE source_id = ?", (r["id"],)).fetchone()["c"]
            if used:
                kept["sources"].append(r["id"])
            else:
                conn.execute("DELETE FROM sources WHERE id = ?", (r["id"],))
                removed["sources"].append(r["id"])
        for ch in restore:
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (ch["entity_id"],)).fetchone()
            if row is not None and row[ch["field"]] == ch["after"]:
                conn.execute(f"UPDATE entities SET {ch['field']} = ? WHERE id = ?", (ch["before"], ch["entity_id"]))
        for r in conn.execute("SELECT id FROM entities WHERE run_id = ?", (run_id,)).fetchall():
            n_rel = conn.execute("SELECT COUNT(*) c FROM relations WHERE subject_id = ? OR object_id = ?", (r["id"], r["id"])).fetchone()["c"]
            n_ev = conn.execute("SELECT COUNT(*) c FROM evidence WHERE entity_id = ?", (r["id"],)).fetchone()["c"]
            if n_rel or n_ev:
                kept["entities"].append(r["id"])
            else:
                conn.execute("DELETE FROM entities WHERE id = ?", (r["id"],))
                removed["entities"].append(r["id"])
        # derived_from pointers to deleted relations
        if removed["relations"]:
            for r in conn.execute("SELECT id, derived_from FROM relations").fetchall():
                d = jload(r["derived_from"], [])
                if any(i in removed["relations"] for i in d):
                    conn.execute("UPDATE relations SET derived_from = ? WHERE id = ?", (jdump([i for i in d if i not in removed["relations"]]), r["id"]))
    for rid in touched_rel:
        relations_mod.recompute_relation(svc, rid, f"enrichment run {run_id} undone")
    return {"removed": removed, "kept": kept}


def undo(svc, run_id: int) -> dict:
    row = svc.db.one("SELECT * FROM enrichment_runs WHERE id = ?", (run_id,))
    if row is None:
        raise NotFound(f"Enrichment run {run_id} does not exist.")
    if row["status"] == "undone":
        raise AtlasError(f"Run {run_id} was already undone.")
    if row["status"] != "ok":
        raise AtlasError(f"Run {run_id} has status {row['status']!r}; only completed runs can be undone.")
    created = jload(row["created"], {})
    result = _undo_rows(svc, run_id, restore=created.get("entity_changes", []))
    svc.db.execute("UPDATE enrichment_runs SET status = 'undone', undone_ts = ? WHERE id = ?", (svc.clock(), run_id))
    history.record(svc, row["case_id"], "enrichment.undone", "enrichment", run_id, f"Enrichment run {run_id} ({row['enricher']}) undone",
                   before={k: len(v) for k, v in created.items() if isinstance(v, list)},
                   after={k: len(v) for k, v in result["removed"].items()})
    return {"undone": True, "run_id": run_id, "enricher": row["enricher"], **result}


def list_runs(svc, case_id: int) -> dict:
    cases_mod.get_row(svc, case_id)
    items = []
    for r in svc.db.query("SELECT * FROM enrichment_runs WHERE case_id = ? ORDER BY id DESC LIMIT 100", (case_id,)):
        created = jload(r["created"], {})
        items.append({"id": r["id"], "enricher": r["enricher"], "entity_id": r["entity_id"], "status": r["status"], "ts": r["created_ts"],
                      "undone_ts": r["undone_ts"], "inputs": jload(r["inputs"], {}), "note": r["note"],
                      "created": {k: len(v) for k, v in created.items() if isinstance(v, list)}})
    return {"case_id": case_id, "items": items}
