"""Domain errors. The API and the agent route map them to HTTP codes (400 / 404 / 403)."""

from __future__ import annotations


class AtlasError(ValueError):
    """Invalid input or a violated rule (HTTP 400)."""


class NotFound(LookupError):
    """The record does not exist (HTTP 404)."""


class Refused(AtlasError):
    """Blocked by the ethics guard or a safety rule (HTTP 403)."""
