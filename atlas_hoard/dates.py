"""Partial ISO dates (``2020``, ``2020-05``, ``2020-05-12``) as comparable day ranges.

Sources rarely give an exact day, so every bound is kept as it was written and
compared through its earliest/latest possible day. That keeps "valid until 2019"
meaning "through the end of 2019" and lets two fuzzy intervals be compared honestly.
"""

from __future__ import annotations

import calendar
import re
from datetime import date

from .errors import AtlasError

_RE = re.compile(r"^(-?\d{1,4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?(?:[T ].*)?$")


def parse_partial(value: str | None) -> tuple[date, date] | None:
    """Earliest and latest day a partial date can mean; None for an empty value."""
    if value is None or str(value).strip() == "":
        return None
    match = _RE.match(str(value).strip())
    if not match:
        raise AtlasError(f"Invalid date {value!r}: use YYYY, YYYY-MM or YYYY-MM-DD.")
    year = int(match.group(1))
    if not 1 <= year <= 9999:
        raise AtlasError(f"Invalid year in date {value!r} (1-9999).")
    month = match.group(2)
    day = match.group(3)
    try:
        if month is None:
            return date(year, 1, 1), date(year, 12, 31)
        m = int(month)
        if not 1 <= m <= 12:
            raise ValueError
        if day is None:
            return date(year, m, 1), date(year, m, calendar.monthrange(year, m)[1])
        d = date(year, m, int(day))
        return d, d
    except ValueError:
        raise AtlasError(f"Invalid date {value!r}.") from None


def normalize(value: str | None) -> str | None:
    """Canonical text of a partial date (zero padded), or None."""
    if value is None or str(value).strip() == "":
        return None
    match = _RE.match(str(value).strip())
    parse_partial(value)  # validates
    year, month, day = match.group(1), match.group(2), match.group(3)  # type: ignore[union-attr]
    out = f"{int(year):04d}"
    if month:
        out += f"-{int(month):02d}"
        if day:
            out += f"-{int(day):02d}"
    return out


def start_day(value: str | None) -> date | None:
    parsed = parse_partial(value)
    return parsed[0] if parsed else None


def end_day(value: str | None) -> date | None:
    parsed = parse_partial(value)
    return parsed[1] if parsed else None


def contains(valid_from: str | None, valid_to: str | None, as_of: str | None) -> bool:
    """Was a fact with this validity interval true on ``as_of``? Open bounds are open."""
    if as_of is None or str(as_of).strip() == "":
        return True
    point = parse_partial(as_of)
    assert point is not None
    lo = start_day(valid_from)
    hi = end_day(valid_to)
    if lo is not None and lo > point[1]:
        return False
    if hi is not None and hi < point[0]:
        return False
    return True


def overlap(a_from: str | None, a_to: str | None, b_from: str | None, b_to: str | None) -> bool:
    """Do two validity intervals share a day? Unknown bounds are treated as open (they may overlap)."""
    a_lo, a_hi = start_day(a_from), end_day(a_to)
    b_lo, b_hi = start_day(b_from), end_day(b_to)
    if a_hi is not None and b_lo is not None and a_hi < b_lo:
        return False
    if b_hi is not None and a_lo is not None and b_hi < a_lo:
        return False
    return True


def sort_key(value: str | None) -> tuple[int, str]:
    """Order for timelines: dated items by earliest day, undated last."""
    day = start_day(value)
    return (0, day.isoformat()) if day else (1, "")


def days_between(a: date, b: date) -> int:
    return (b - a).days
