"""Shared plumbing for enrichers: a run context that records what a run touched so that it can be undone exactly."""

from __future__ import annotations

from typing import Any

from .. import entities as entities_mod
from ..util import jload

SNAP_FIELDS = ("aliases", "description", "lat", "lon", "geo_precision", "date_start", "date_end", "wikidata_qid", "attributes")


class RunContext:
    """What an enricher sees: the service, the case, the run id that stamps every row it creates, and change tracking."""

    def __init__(self, svc, case_id: int, run_id: int, entity, params: dict[str, Any]):
        self.svc, self.case_id, self.run_id, self.entity, self.params = svc, case_id, run_id, entity, params
        self.notes: list[str] = []
        self._before: dict[int, dict[str, Any]] = {}

    def touch(self, entity_id: int) -> None:
        """Snapshot an existing entity the first time the run is about to change it."""
        if entity_id in self._before:
            return
        row = entities_mod.get_row(self.svc, entity_id)
        if row["run_id"] == self.run_id:
            return
        self._before[entity_id] = {f: row[f] for f in SNAP_FIELDS}

    def changes(self) -> list[dict[str, Any]]:
        """Field-level before/after of every pre-existing entity the run changed (stored for undo)."""
        out = []
        for entity_id, before in self._before.items():
            row = self.svc.db.one("SELECT * FROM entities WHERE id = ?", (entity_id,))
            if row is None:
                continue
            for f in SNAP_FIELDS:
                if row[f] != before[f]:
                    out.append({"entity_id": entity_id, "field": f, "before": before[f], "after": row[f]})
        return out

    def ensure_entity(self, *, name: str, type: str, qid: str = "", description: str = "", public_figure: bool = False) -> tuple[int, bool]:  # noqa: A002
        """An entity of the case for this name/QID: reuse when it exists (same QID, else same normalised name and type)."""
        from ..util import norm_name
        svc = self.svc
        if qid:
            row = svc.db.one("SELECT id FROM entities WHERE case_id = ? AND wikidata_qid = ? AND merged_into IS NULL", (self.case_id, qid))
            if row:
                return row["id"], False
        key = norm_name(name)
        for r in svc.db.query("SELECT * FROM entities WHERE case_id = ? AND type = ? AND merged_into IS NULL", (self.case_id, type)):
            if r["norm_name"] == key or key in [norm_name(a) for a in jload(r["aliases"], [])]:
                if qid and not r["wikidata_qid"]:
                    self.touch(r["id"])
                    svc.db.execute("UPDATE entities SET wikidata_qid = ? WHERE id = ?", (qid, r["id"]))
                return r["id"], False
        res = entities_mod.upsert(svc, case_id=self.case_id, type=type, name=name, description=description, wikidata_qid=qid or None,
                                  public_figure=True if (public_figure and type == "person") else None, run_id=self.run_id)
        return res["entity"]["id"], True
