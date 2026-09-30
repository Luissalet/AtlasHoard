"""/api/cases."""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from .. import cases as cases_mod
from .deps import services, tool, ui

router = APIRouter(prefix="/api")


class CaseBody(BaseModel):
    title: Optional[str] = None
    question: Optional[str] = None
    status: Optional[Literal["open", "paused", "closed"]] = None
    tags: Optional[list[str]] = None
    summary: Optional[str] = None
    open_questions: Optional[list[str]] = None


@router.get("/cases")
def cases_list(request: Request, status: Optional[str] = None, query: Optional[str] = None, limit: int = Query(100, ge=1, le=500),
               cursor: Optional[str] = None):
    with ui():
        return cases_mod.list_cases(services(request), status=status, query=query, limit=limit, cursor=cursor)


@router.post("/cases", status_code=201)
def cases_create(request: Request, body: CaseBody):
    return tool(request, "case_create", **body.model_dump(exclude_none=True))


@router.get("/cases/{case_id}")
def cases_get(request: Request, case_id: int):
    return tool(request, "case_get", case_id=case_id)


@router.put("/cases/{case_id}")
def cases_update(request: Request, case_id: int, body: CaseBody):
    return tool(request, "case_update", case_id=case_id, **body.model_dump(exclude_none=True))


@router.delete("/cases/{case_id}")
def cases_delete(request: Request, case_id: int, confirm: bool = False):
    return tool(request, "case_update", case_id=case_id, action="delete", confirm=confirm)
