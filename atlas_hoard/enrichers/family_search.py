"""Search the family's documentary apps (Borges library, Links saved pages) and keep the hits as references.

The documents stay in their apps: a hit becomes a ``family_ref`` source (``hoard://<app>/<kind>/<id>`` + title +
revision + a short excerpt). Queries never contain private persons' names unless the caller explicitly allows it.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .. import ethics, sources as sources_mod
from ..errors import AtlasError, Refused
from ..hoard_link.artifacts import parse_ref
from .base import RunContext

KIND_BY_APP = {"borges": "document", "links": "page"}
ID_KEYS = ("id", "doc_id", "document_id", "link_id", "item_id", "uid")
TITLE_KEYS = ("title", "name", "label")
TEXT_KEYS = ("snippet", "excerpt", "text", "content", "summary", "description")


def _hits(result: Any) -> list[dict]:
    if isinstance(result, list):
        return [h for h in result if isinstance(h, dict)]
    if isinstance(result, dict):
        for key in ("items", "results", "hits", "documents", "links", "matches", "data"):
            if isinstance(result.get(key), list):
                return [h for h in result[key] if isinstance(h, dict)]
    return []


def _first(hit: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = hit.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def hit_to_source(app: str, hit: dict) -> dict | None:
    ref = _first(hit, ("ref", "uri", "hoard_ref"))
    kind = KIND_BY_APP.get(app, "item")
    if ref.startswith("hoard://"):
        try:
            ref = parse_ref(ref).uri
        except ValueError:
            ref = ""
    else:
        ref = ""
    if not ref:
        ident = _first(hit, ID_KEYS)
        if not ident:
            return None
        ref = parse_ref(f"hoard://{app}/{kind}/{ident}").uri if "/" not in ident else ""
        if not ref:
            from urllib.parse import quote
            ref = f"hoard://{app}/{kind}/{quote(ident, safe='')}"
    title, text = _first(hit, TITLE_KEYS), _first(hit, TEXT_KEYS)
    revision = _first(hit, ("revision", "source_revision", "sha256", "hash", "etag")) or \
        "sha256:" + hashlib.sha256((title + "\n" + text).encode("utf-8")).hexdigest()
    return {"ref": ref, "title": title or ref, "text": text[:2000], "revision": revision}


def run(ctx: RunContext) -> dict:
    svc, p, entity = ctx.svc, ctx.params, ctx.entity
    query = (p.get("query") or (entity["name"] if entity is not None else "")).strip()
    if not query:
        raise AtlasError("family_search needs a query (or an entity to search for).")
    removed: list[str] = []
    if not p.get("include_private"):
        query, removed = ethics.redact_query(svc, ctx.case_id, query)
        if not query:
            raise Refused("The query only contained the names of private persons, which family_search never sends. "
                          "Use include_private=true only if you are entitled to search for them.")
    apps = p.get("apps") or svc.family_sources()
    limit = int(p.get("limit") or 5)
    tools = svc.family_tools()
    out: dict[str, Any] = {}
    created: list[int] = []
    for app in apps:
        tool = tools.get(app)
        if not tool:
            out[app] = {"status": "unknown_app", "hint": f"No search tool is configured for {app!r} (Settings > family sources)."}
            continue
        reply = svc.family_call(app, tool, {"query": query, "limit": limit})
        if not reply.get("ok"):
            out[app] = {"status": "unavailable", "error": str(reply.get("error") or f"HTTP {reply.get('status')}")[:300]}
            continue
        hits = _hits(reply.get("result"))
        added, dup = [], []
        for hit in hits[:limit]:
            src = hit_to_source(app, hit)
            if src is None:
                continue
            res = sources_mod.add(svc, case_id=ctx.case_id, kind="family_ref", ref=src["ref"], revision=src["revision"], title=src["title"],
                                  text=src["text"], run_id=ctx.run_id, note=f"Found by family_search for {query!r}")
            (added if res["created"] else dup).append(res["source"]["id"])
            created += [res["source"]["id"]] if res["created"] else []
        out[app] = {"status": "ok", "hits": len(hits), "sources_added": added, "already_present": dup}
    note = ""
    if removed:
        note = f"Names of private persons were removed from the query: {', '.join(removed)}."
    return {"status": "ok" if any(v.get("status") == "ok" for v in out.values()) else "unavailable", "query": query, "apps": out,
            "sources_added": created, "note": note, "redacted": removed}
