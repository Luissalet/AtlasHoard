"""/api/cases/{id}/timeline | map | graph | evidence."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from .. import ach as ach_mod
from .deps import services, tool

router = APIRouter(prefix="/api/cases/{case_id}")


def _csv(value: Optional[str]) -> Optional[list[str]]:
    return [x for x in value.split(",") if x] if value else None


@router.get("/timeline")
def timeline(request: Request, case_id: int, entity_id: Optional[int] = None, types: Optional[str] = None, as_of: Optional[str] = None,
             date_from: Optional[str] = None, date_to: Optional[str] = None, gap_days: int = 365, limit: int = Query(500, ge=1, le=1000)):
    return tool(request, "timeline", case_id=case_id, entity_id=entity_id, types=_csv(types), as_of=as_of or None,
                date_from=date_from or None, date_to=date_to or None, gap_days=gap_days, limit=limit)


@router.get("/map")
def map_layers(request: Request, case_id: int, as_of: Optional[str] = None, date_from: Optional[str] = None,
               date_to: Optional[str] = None, types: Optional[str] = None):
    return tool(request, "map_layers", case_id=case_id, as_of=as_of or None, date_from=date_from or None, date_to=date_to or None, types=_csv(types))


@router.get("/graph")
def graph(request: Request, case_id: int, entity_id: Optional[int] = None, depth: int = Query(1, ge=1, le=4), status: Optional[str] = None,
          as_of: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
          include_retracted: bool = False, max_nodes: int = Query(300, ge=5, le=600)):
    return tool(request, "graph", case_id=case_id, entity_id=entity_id, depth=depth, statuses=_csv(status), as_of=as_of or None,
                date_from=date_from or None, date_to=date_to or None, include_retracted=include_retracted, max_nodes=max_nodes)


@router.get("/evidence")
def evidence(request: Request, case_id: int):
    return {"case_id": case_id, "items": ach_mod.evidence_items(services(request), case_id)}
