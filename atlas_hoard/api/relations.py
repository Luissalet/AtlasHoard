"""/api/relations and the predicate vocabulary."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from .. import relations as relations_mod
from .deps import services, tool, ui

router = APIRouter(prefix="/api")


class EvidenceBody(BaseModel):
    source_id: int
    quote: str = ""
    locator: str = ""
    observed_at: Optional[str] = None


class RelationBody(BaseModel):
    subject: Optional[int | str] = None
    predicate: Optional[str] = None
    object: Optional[int | str] = None
    evidence: Optional[list[EvidenceBody]] = None
    add_evidence: Optional[list[EvidenceBody]] = None
    remove_evidence: Optional[list[int]] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    observed_at: Optional[str] = None
    clear_dates: Optional[list[str]] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    derived_from: Optional[list[int]] = None


class RetractBody(BaseModel):
    reason: str = ""
    action: str = "retract"


class PredicateBody(BaseModel):
    name: str
    label: str = ""
    functional: bool = False
    symmetric: bool = False


@router.get("/cases/{case_id}/relations")
def relations_list(request: Request, case_id: int, subject: Optional[int | str] = None, object: Optional[int | str] = None,
                   predicate: Optional[str] = None, status: Optional[str] = None, as_of: Optional[str] = None,
                   include_retracted: bool = True, limit: int = Query(300, ge=1, le=1000), cursor: Optional[str] = None):
    with ui():
        return relations_mod.list_page(services(request), case_id, subject=subject, object=object, predicate=predicate,
                                       statuses=status.split(",") if status else None, as_of=as_of or None,
                                       include_retracted=include_retracted, limit=limit, cursor=cursor)


@router.post("/cases/{case_id}/relations", status_code=201)
def relations_add(request: Request, case_id: int, body: RelationBody):
    return tool(request, "relation_add", case_id=case_id, **body.model_dump(exclude_none=True, exclude={"add_evidence", "remove_evidence"}))


@router.get("/relations/{relation_id}")
def relations_get(request: Request, relation_id: int):
    return tool(request, "relation_get", relation_id=relation_id)


@router.put("/relations/{relation_id}")
def relations_update(request: Request, relation_id: int, body: RelationBody):
    return tool(request, "relation_update", relation_id=relation_id, **body.model_dump(exclude_none=True, exclude={"evidence"}))


@router.post("/relations/{relation_id}/retract")
def relations_retract(request: Request, relation_id: int, body: RetractBody):
    return tool(request, "relation_retract", relation_id=relation_id, reason=body.reason, action=body.action)


@router.delete("/relations/{relation_id}")
def relations_delete(request: Request, relation_id: int, confirm: bool = False):
    return tool(request, "relation_update", relation_id=relation_id, action="delete", confirm=confirm)


@router.get("/predicates")
def predicates_list(request: Request):
    return relations_mod.predicates_list(services(request))


@router.put("/predicates")
def predicates_save(request: Request, body: PredicateBody):
    with ui():
        return relations_mod.predicate_upsert(services(request), body.name, label=body.label, functional=body.functional, symmetric=body.symmetric)


@router.delete("/predicates/{name}")
def predicates_delete(request: Request, name: str):
    with ui():
        return relations_mod.predicate_delete(services(request), name)
