"""/api report."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request, Response

from .deps import tool

router = APIRouter(prefix="/api/cases/{case_id}")


@router.get("/report")
def report(request: Request, case_id: int, format: str = "markdown", lang: str = "es", use_model: bool = True,
           section: Optional[str] = None, raw: bool = False):
    result = tool(request, "case_report", case_id=case_id, format=format, lang=lang, use_model=use_model, section=section or None,
                  max_chars=10_000_000)
    if raw and format == "markdown":
        return Response(content=result["markdown"], media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="atlas-case-{case_id}.md"'})
    return result
