"""/api/settings."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .deps import services, ui

router = APIRouter(prefix="/api")


class SettingsBody(BaseModel):
    geocode_enabled: Optional[bool] = None
    family_sources: Optional[list[str]] = None
    family_tools: Optional[dict[str, str]] = None


@router.get("/settings")
def settings_get(request: Request):
    return services(request).get_settings()


@router.put("/settings")
def settings_put(request: Request, body: SettingsBody):
    with ui():
        return services(request).update_settings(body.model_dump(exclude_none=True))
