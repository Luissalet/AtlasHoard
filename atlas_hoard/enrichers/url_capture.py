"""URL capture as an enricher: fetch one public page into a source (readable text, hash, snapshot)."""

from __future__ import annotations

from .. import sources as sources_mod
from ..errors import AtlasError
from .base import RunContext


def run(ctx: RunContext) -> dict:
    p = ctx.params
    url = (p.get("url") or "").strip()
    if not url:
        raise AtlasError("url_capture needs a url.")
    res = sources_mod.add(ctx.svc, case_id=ctx.case_id, kind="url", url=url, title=p.get("title") or "", reliability=p.get("reliability"),
                          credibility=p.get("credibility"), run_id=ctx.run_id, note=p.get("note") or "")
    if not res["created"]:
        return {"status": "duplicate", "source": res["source"], "duplicate_of": res.get("duplicate_of")}
    s = res["source"]
    return {"status": "ok", "source_id": s["id"], "title": s["title"], "url": s["url"], "text_chars": s["text_chars"],
            "published_at": s["published_at"], "content_hash": s["content_hash"]}
