"""The ethics guard, in code: who may be enriched, and what may leave the app in a search query.

* ``private_person`` entities are never enriched and never sent to ``family_search``.
* Wikidata only for organizations, places, events and public figures.
* No enrichment of social networks or personal-data lookups: there is no such enricher, and URL capture
  refuses social hosts (see ``fetch.py``).
"""

from __future__ import annotations

from .errors import Refused
from .util import jload, norm_name

WIKIDATA_TYPES = ("organization", "place", "event", "person")
GEOCODE_TYPES = ("place", "event", "organization")


def check_enrichable(entity, enricher: str) -> None:
    """Raise Refused when ``enricher`` must not run on ``entity``."""
    if entity is None:
        return
    if entity["private_person"]:
        raise Refused(f"{entity['name']!r} is flagged as a private person: enrichers never run on them. "
                      "If this is a public figure, mark public_figure=true on the entity first.")
    if enricher == "wikidata":
        if entity["type"] not in WIKIDATA_TYPES:
            raise Refused(f"Wikidata enrichment covers organizations, places, events and public figures, not {entity['type']}.")
        if entity["type"] == "person" and not entity["public_figure"]:
            raise Refused("Wikidata enrichment of a person needs public_figure=true on the entity.")
    if enricher == "geocode" and entity["type"] not in GEOCODE_TYPES:
        raise Refused(f"Geocoding covers places, events and organizations, not {entity['type']}.")


def private_names(svc, case_id: int) -> list[list[str]]:
    """Normalised token lists of every name and alias of the case's private persons."""
    out: list[list[str]] = []
    for e in svc.db.query("SELECT name, aliases FROM entities WHERE case_id = ? AND private_person = 1 AND merged_into IS NULL", (case_id,)):
        for n in [e["name"], *jload(e["aliases"], [])]:
            tokens = norm_name(n).split()
            if tokens:
                out.append(tokens)
    out.sort(key=len, reverse=True)
    return out


def redact_query(svc, case_id: int, query: str) -> tuple[str, list[str]]:
    """Remove private persons' names from a query that would leave the app. Returns (clean query, removed names)."""
    tokens = norm_name(query).split()
    removed: list[str] = []
    for name in private_names(svc, case_id):
        i = 0
        while i <= len(tokens) - len(name):
            if tokens[i: i + len(name)] == name:
                removed.append(" ".join(name))
                del tokens[i: i + len(name)]
            else:
                i += 1
    return " ".join(tokens), removed
