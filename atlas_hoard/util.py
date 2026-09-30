"""Small shared helpers: JSON columns, names, pagination with a size budget."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from .errors import AtlasError

RESULT_BUDGET = 16_000  # characters of JSON per page; the hard cap on any tool result is ~20 KB


def jload(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def iso_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def iso_stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_name(name: str) -> str:
    """Accent-, case- and punctuation-insensitive form used to spot same-name entities."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def clean_list(values: Iterable[Any] | None, *, limit: int = 50, maxlen: int = 200) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value).strip()[:maxlen]
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
        if len(out) >= limit:
            break
    return out


def parse_cursor(cursor: str | None) -> int:
    if cursor in (None, ""):
        return 0
    try:
        value = int(str(cursor).removeprefix("o:"))
    except ValueError:
        raise AtlasError(f"Invalid cursor {cursor!r}.") from None
    return max(0, value)


def page(rows: Sequence[dict], limit: int, cursor: str | None, budget: int = RESULT_BUDGET) -> tuple[list[dict], str | None]:
    """Slice ``rows`` from the cursor, stopping at ``limit`` items or ``budget`` characters of JSON.

    The cursor is an offset (``"o:40"``): stable enough for a workspace where a single
    user and assistant edit the same case, and trivially resumable.
    """
    start = parse_cursor(cursor)
    out: list[dict] = []
    used = 0
    index = start
    while index < len(rows) and len(out) < limit:
        size = len(json.dumps(rows[index], ensure_ascii=False))
        if out and used + size > budget:
            break
        out.append(rows[index])
        used += size
        index += 1
    return out, (f"o:{index}" if index < len(rows) else None)


def clip(text: str | None, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 query: quoted prefix terms joined by AND."""
    terms = re.findall(r"\w+", unicodedata.normalize("NFKC", text or ""), flags=re.UNICODE)
    terms = [t for t in terms if t]
    if not terms:
        raise AtlasError("The search text has no searchable words.")
    return " ".join(f'"{t}"*' for t in terms[:12])


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AtlasError(message)
