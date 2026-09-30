"""/api hypotheses and ACH ratings."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import ach as ach_mod
from .deps import services, tool

router = APIRouter(prefix="/api")


class HypothesisBody(BaseModel):
    statement: Optional[str] = None
    status: Optional[str] = None


class EvidenceBody(BaseModel):
    source_id: int
    quote: str = ""
    locator: str = ""


class RateBody(BaseModel):
    hypothesis_id: int
    evidence_id: Optional[int] = None
    evidence: Optional[EvidenceBody] = None
    rating: Optional[str] = None
    note: str = ""
    action: str = "rate"


@router.get("/cases/{case_id}/ach")
def ach_matrix(request: Request, case_id: int, include_unrated: bool = False):
    return tool(request, "ach_matrix", case_id=case_id, include_unrated=include_unrated)


@router.post("/cases/{case_id}/hypotheses", status_code=201)
def hypotheses_add(request: Request, case_id: int, body: HypothesisBody):
    return tool(request, "hypothesis_add", case_id=case_id, **body.model_dump(exclude_none=True))


@router.put("/hypotheses/{hypothesis_id}")
def hypotheses_update(request: Request, hypothesis_id: int, body: HypothesisBody):
    return tool(request, "hypothesis_add", hypothesis_id=hypothesis_id, **body.model_dump(exclude_none=True))


@router.delete("/hypotheses/{hypothesis_id}")
def hypotheses_delete(request: Request, hypothesis_id: int, confirm: bool = False):
    return tool(request, "hypothesis_add", hypothesis_id=hypothesis_id, action="delete", confirm=confirm)


@router.put("/ach")
def ach_rate(request: Request, body: RateBody):
    return tool(request, "ach_rate", **body.model_dump(exclude_none=True))
