"""/api history."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from .. import history as history_mod
from .deps import services, ui

router = APIRouter(prefix="/api")


@router.get("/cases/{case_id}/history")
def case_history(request: Request, case_id: int, target_type: Optional[str] = None, target_id: Optional[int] = None,
                 action: Optional[str] = None, limit: int = Query(100, ge=1, le=500), cursor: Optional[str] = None):
    with ui():
        return history_mod.list_history(services(request), case_id, target_type=target_type, target_id=target_id, action=action,
                                        limit=limit, cursor=cursor)
