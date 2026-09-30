"""/api enrichment."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import enrich as enrich_mod
from .deps import services, tool, ui

router = APIRouter(prefix="/api")


class EnrichBody(BaseModel):
    enricher: str
    entity_id: Optional[int] = None
    qid: Optional[str] = None
    language: Optional[str] = None
    query: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None
    reliability: Optional[str] = None
    credibility: Optional[str] = None
    overwrite: bool = False
    dry_run: bool = False
    apps: Optional[list[str]] = None
    limit: Optional[int] = None
    include_private: bool = False


@router.post("/cases/{case_id}/enrich")
def enrich(request: Request, case_id: int, body: EnrichBody):
    return tool(request, "enrich", case_id=case_id, **body.model_dump(exclude_none=True))


@router.get("/cases/{case_id}/enrichment")
def enrichment_runs(request: Request, case_id: int):
    with ui():
        return enrich_mod.list_runs(services(request), case_id)


@router.post("/enrichment/{run_id}/undo")
def enrichment_undo(request: Request, run_id: int):
    return tool(request, "enrichment_undo", run_id=run_id)
