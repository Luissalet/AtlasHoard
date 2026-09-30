"""Shared helpers for the API routers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from fastapi import Request

from .. import history
from ..agent_tools import call_tool
from ..services import Services


def services(request: Request) -> Services:
    return request.app.state.services


@contextmanager
def ui():
    """Mark every change made inside as coming from the web UI in the case history."""
    token = history.set_caller("ui")
    try:
        yield
    finally:
        history.CALLER.reset(token)


def tool(request: Request, _tool: str, **arguments: Any) -> Any:
    """Run a catalogue tool for the UI: the REST routes and the MCP tools are the same code and cannot disagree."""
    clean = {k: v for k, v in arguments.items() if v is not None}
    return call_tool(services(request), _tool, clean, caller="ui", cap=False)
