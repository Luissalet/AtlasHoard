"""Enrichers: traceable, scoped and undoable ways of adding material to a case."""

from . import family_search, geocode, url_capture, wikidata

ENRICHERS = {
    "wikidata": wikidata.run,
    "geocode": geocode.run,
    "url_capture": url_capture.run,
    "family_search": family_search.run,
}
