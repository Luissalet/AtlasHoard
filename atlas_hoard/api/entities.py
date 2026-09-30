"""/api/entities."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from .. import entities as entities_mod
from .deps import services, tool, ui

router = APIRouter(prefix="/api")


class EntityBody(BaseModel):
    type: Optional[str] = None
    name: Optional[str] = None
    aliases: Optional[list[str]] = None
    remove_aliases: Optional[list[str]] = None
    description: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None
    remove_attributes: Optional[list[str]] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    geo_precision: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    wikidata_qid: Optional[str] = None
    public_figure: Optional[bool] = None
    private_person: Optional[bool] = None


class MergeBody(BaseModel):
    keep_id: int
    merge_id: int
    confirm: bool = False


@router.get("/cases/{case_id}/entities")
def entities_list(request: Request, case_id: int, q: Optional[str] = None, type: Optional[str] = None,
                  limit: int = Query(300, ge=1, le=1000), cursor: Optional[str] = None):
    with ui():
        return entities_mod.search(services(request), query=q, case_id=case_id, type=type, limit=limit, cursor=cursor)


@router.post("/cases/{case_id}/entities", status_code=201)
def entities_create(request: Request, case_id: int, body: EntityBody):
    return tool(request, "entity_upsert", case_id=case_id, **body.model_dump(exclude_none=True))


@router.get("/cases/{case_id}/duplicates")
def entities_duplicates(request: Request, case_id: int, min_score: float = 0.5):
    return tool(request, "duplicates_suggest", case_id=case_id, min_score=min_score)


@router.post("/entities/merge")
def entities_merge(request: Request, body: MergeBody):
    return tool(request, "entity_merge", **body.model_dump())


@router.get("/entities/{entity_id}")
def entities_get(request: Request, entity_id: int, as_of: Optional[str] = None, include_retracted: bool = False):
    return tool(request, "entity_get", entity_id=entity_id, as_of=as_of or None, include_retracted=include_retracted)


@router.put("/entities/{entity_id}")
def entities_update(request: Request, entity_id: int, body: EntityBody):
    case_id = entities_mod.get_row(services(request), entity_id)["case_id"]
    return tool(request, "entity_upsert", case_id=case_id, entity_id=entity_id, **body.model_dump(exclude_none=True))


@router.delete("/entities/{entity_id}")
def entities_delete(request: Request, entity_id: int, confirm: bool = False):
    case_id = entities_mod.get_row(services(request), entity_id)["case_id"]
    return tool(request, "entity_upsert", case_id=case_id, entity_id=entity_id, action="delete", confirm=confirm)
