"""/api/sources."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from .. import sources as sources_mod
from .deps import services, tool, ui

router = APIRouter(prefix="/api")


class SourceBody(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    path: Optional[str] = None
    text: Optional[str] = None
    ref: Optional[str] = None
    revision: Optional[str] = None
    reliability: Optional[str] = None
    credibility: Optional[str] = None
    published_at: Optional[str] = None
    origin: Optional[str] = None
    note: Optional[str] = None


class RetractBody(BaseModel):
    action: str = "retract"
    reason: str = ""


@router.get("/cases/{case_id}/sources")
def sources_list(request: Request, case_id: int, kind: Optional[str] = None, include_retracted: bool = True,
                 limit: int = Query(200, ge=1, le=1000), cursor: Optional[str] = None):
    with ui():
        return sources_mod.list_sources(services(request), case_id, kind=kind, include_retracted=include_retracted, limit=limit, cursor=cursor)


@router.get("/cases/{case_id}/sources/search")
def sources_search(request: Request, case_id: int, q: str, include_retracted: bool = False, limit: int = Query(20, ge=1, le=50)):
    return tool(request, "sources_search", case_id=case_id, query=q, include_retracted=include_retracted, limit=limit)


@router.post("/cases/{case_id}/sources", status_code=201)
def sources_add(request: Request, case_id: int, body: SourceBody):
    return tool(request, "source_add", case_id=case_id, **body.model_dump(exclude_none=True))


@router.get("/sources/{source_id}")
def sources_get(request: Request, source_id: int, max_chars: int = Query(4000, ge=200, le=12000), offset: int = Query(0, ge=0)):
    return tool(request, "source_get", source_id=source_id, max_chars=max_chars, offset=offset)


@router.put("/sources/{source_id}")
def sources_update(request: Request, source_id: int, body: SourceBody):
    return tool(request, "source_add", source_id=source_id, **body.model_dump(exclude_none=True))


@router.post("/sources/{source_id}/retract")
def sources_retract(request: Request, source_id: int, body: RetractBody):
    return tool(request, "source_retract", source_id=source_id, action=body.action, reason=body.reason)


@router.delete("/sources/{source_id}")
def sources_delete(request: Request, source_id: int, confirm: bool = False):
    return tool(request, "source_retract", source_id=source_id, action="delete", confirm=confirm)
