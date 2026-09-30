"""Sources: what a claim rests on. Graded on two axes, snapshotted, retractable (never silently deleted)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from . import cases as cases_mod
from . import history
from .dates import normalize
from .errors import AtlasError, NotFound, Refused
from .extract import MAX_TEXT_CHARS, extract_bytes
from .fetch import host_of, check_url
from .hoard_link.artifacts import parse_ref
from .util import clip, fts_query, iso_stamp, page

KINDS = ("url", "file", "text", "family_ref", "note")
RELIABILITY = "ABCDEF"
CREDIBILITY = "123456"
FILE_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".log", ".html", ".htm", ".pdf"}
MAX_FILE_BYTES = 25_000_000


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def grade_label(row) -> str:
    return f"{row['reliability']}{row['credibility']}"


def view(svc, row, *, with_text: bool = False, max_chars: int = 4000, offset: int = 0) -> dict[str, Any]:
    evidence = svc.db.one("SELECT COUNT(*) c FROM evidence WHERE source_id = ?", (row["id"],))["c"]
    out = {
        "id": row["id"], "case_id": row["case_id"], "cite": f"[S{row['id']}]", "kind": row["kind"], "title": row["title"],
        "url": row["url"], "origin": row["origin"], "reliability": row["reliability"], "credibility": row["credibility"],
        "grade": grade_label(row), "captured_at": row["captured_at"], "published_at": row["published_at"],
        "content_hash": row["content_hash"], "ref": row["ref"], "ref_revision": row["ref_revision"], "note": row["note"],
        "retracted": bool(row["retracted"]), "retract_reason": row["retract_reason"], "text_chars": len(row["text"] or ""),
        "evidence_count": evidence, "created_ts": row["created_ts"],
    }
    if with_text:
        text = row["text"] or ""
        out["text"] = text[offset: offset + max_chars]
        out["text_offset"] = offset
        out["text_truncated"] = offset + max_chars < len(text)
    return out


def get_row(svc, source_id: int, case_id: int | None = None):
    row = svc.db.one("SELECT * FROM sources WHERE id = ?", (source_id,))
    if row is None or (case_id is not None and row["case_id"] != case_id):
        raise NotFound(f"Source {source_id} does not exist" + (f" in case {case_id}." if case_id else "."))
    return row


def _grade(reliability: Any, credibility: Any) -> tuple[str | None, str | None]:
    rel = str(reliability).strip().upper() if reliability not in (None, "") else None
    cred = str(credibility).strip() if credibility not in (None, "") else None
    if rel is not None and (len(rel) != 1 or rel not in RELIABILITY):
        raise AtlasError("reliability must be a letter A-F (A completely reliable ... F cannot be judged).")
    if cred is not None and (len(cred) != 1 or cred not in CREDIBILITY):
        raise AtlasError("credibility must be a number 1-6 (1 confirmed ... 6 cannot be judged).")
    return rel, cred


def capture_url(svc, url: str) -> dict[str, Any]:
    """Fetch ``url`` through the injected fetcher and extract readable text. Raises with a reason on failure."""
    check_url(url, allow_private=svc.config.allow_private_urls)
    result = svc.fetcher.fetch(url)
    if result.error:
        raise AtlasError(f"Could not fetch {url}: {result.error}")
    if result.status >= 400 or result.status == 0:
        raise AtlasError(f"Could not fetch {url}: HTTP {result.status}.")
    extracted = extract_bytes(result.body, result.content_type, name=result.final_url.split("?")[0])
    if not extracted["text"].strip():
        raise AtlasError(f"{url} returned no readable text (it may need JavaScript, which Atlas never runs). "
                         "Add the text manually as a text source instead.")
    extracted.update(final_url=result.final_url, status=result.status, content_type=result.content_type)
    return extracted


def _read_file(svc, path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    try:
        p = p.resolve(strict=True)
    except OSError:
        raise AtlasError(f"File not found: {path}") from None
    if not p.is_file():
        raise AtlasError(f"Not a file: {path}")
    if p.suffix.lower() not in FILE_SUFFIXES:
        raise Refused(f"Only text-like files can be added ({', '.join(sorted(FILE_SUFFIXES))}); got {p.suffix or 'no extension'}.")
    roots = svc.config.file_roots
    if roots and not any(root.resolve() in p.parents or root.resolve() == p for root in roots):
        raise Refused("That file is outside the folders allowed by ATLAS_FILE_ROOTS.")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise AtlasError("The file is larger than 25 MB.")
    extracted = extract_bytes(p.read_bytes(), name=p.name)
    extracted["title"] = extracted["title"] or p.stem
    extracted["uri"] = p.as_uri()
    return extracted


def add(svc, *, case_id: int | None = None, source_id: int | None = None, kind: str | None = None, title: str = "",
        url: str = "", path: str = "", text: str = "", ref: str = "", revision: str = "", reliability: Any = None,
        credibility: Any = None, published_at: str | None = None, origin: str = "", note: str = "",
        run_id: int | None = None, captured_at: str | None = None) -> dict:
    """Create a source (URL capture, pasted text, local file, family reference, note) or, with
    ``source_id``, update its grades and metadata."""
    if source_id is not None:
        return update(svc, source_id, title=title, reliability=reliability, credibility=credibility,
                      published_at=published_at, origin=origin, note=note)
    if case_id is None:
        raise AtlasError("case_id is required to add a source.")
    cases_mod.get_row(svc, case_id)
    if kind is None:
        kind = "url" if url and not text else "file" if path else "family_ref" if ref else "text"
    if kind not in KINDS:
        raise AtlasError(f"kind must be one of {', '.join(KINDS)}.")
    rel, cred = _grade(reliability, credibility)
    published = normalize(published_at) if published_at else None
    now_iso = captured_at or iso_stamp(svc.clock())
    body, stored_url, fetched = text.strip(), url.strip(), {}
    if kind == "url":
        if not stored_url:
            raise AtlasError("kind=url needs a url.")
        if body:
            # The caller supplies the snapshot (an enricher that already holds the data, or text the user may use
            # from a page Atlas will not fetch): no request is made.
            origin = origin or host_of(stored_url).removeprefix("www.")
        else:
            fetched = capture_url(svc, stored_url)
            body = fetched["text"]
            stored_url = fetched["final_url"]
            title = title or fetched["title"]
            published = published or fetched["published_at"]
            origin = origin or host_of(stored_url).removeprefix("www.")
    elif kind == "file":
        if not path:
            raise AtlasError("kind=file needs a path.")
        fetched = _read_file(svc, path)
        body, stored_url = fetched["text"], fetched["uri"]
        title = title or fetched["title"]
        published = published or fetched["published_at"]
    elif kind == "family_ref":
        if not ref:
            raise AtlasError("kind=family_ref needs a ref like hoard://borges/document/12.")
        try:
            ref = parse_ref(ref).uri
        except ValueError as error:
            raise AtlasError(str(error)) from None
        origin = origin or ref
        title = title or ref
    else:
        if not body:
            raise AtlasError(f"kind={kind} needs text.")
    body = body[:MAX_TEXT_CHARS]
    content_hash = sha(body) if body else (sha(ref + revision) if kind == "family_ref" else "")
    # Idempotent: the same capture / reference revision of the same thing returns the existing record.
    if kind == "family_ref":
        dup = svc.db.one("SELECT * FROM sources WHERE case_id = ? AND ref = ? AND ref_revision = ?", (case_id, ref, revision))
    elif kind == "url":
        dup = svc.db.one("SELECT * FROM sources WHERE case_id = ? AND kind = 'url' AND url = ? AND content_hash = ? AND retracted = 0",
                         (case_id, stored_url, content_hash))
    else:
        dup = svc.db.one("SELECT * FROM sources WHERE case_id = ? AND kind = ? AND content_hash = ? AND title = ? AND retracted = 0",
                         (case_id, kind, content_hash, title.strip()[:300])) if body else None
    if dup is not None:
        return {"created": False, "duplicate_of": dup["id"], "source": view(svc, dup)}
    cursor = svc.db.execute(
        """INSERT INTO sources(case_id, kind, title, url, origin, reliability, credibility, captured_at, published_at,
           content_hash, text, ref, ref_revision, note, created_ts, run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (case_id, kind, (title or clip(body, 80) or "Untitled").strip()[:300], stored_url, origin.strip()[:200],
         rel or "F", cred or "6", now_iso, published, content_hash, body, ref, revision.strip()[:200], note.strip()[:2000],
         svc.clock(), run_id))
    sid = int(cursor.lastrowid)
    if not origin.strip():
        svc.db.execute("UPDATE sources SET origin = ? WHERE id = ?", (f"{kind}:{sid}", sid))
    history.record(svc, case_id, "source.added", "source", sid, f"Source added [S{sid}] ({kind}): {clip(title or body, 80)}")
    return {"created": True, "source": view(svc, get_row(svc, sid))}


def update(svc, source_id: int, *, title: str = "", reliability: Any = None, credibility: Any = None,
           published_at: str | None = None, origin: str = "", note: str = "") -> dict:
    from . import relations as relations_mod
    row = get_row(svc, source_id)
    rel, cred = _grade(reliability, credibility)
    sets: dict[str, Any] = {}
    if rel:
        sets["reliability"] = rel
    if cred:
        sets["credibility"] = cred
    if title.strip():
        sets["title"] = title.strip()[:300]
    if published_at:
        sets["published_at"] = normalize(published_at)
    if origin.strip():
        sets["origin"] = origin.strip()[:200]
    if note.strip():
        sets["note"] = note.strip()[:2000]
    if not sets:
        return {"created": False, "updated": False, "source": view(svc, row)}
    before = {k: row[k] for k in sets}
    svc.db.execute(f"UPDATE sources SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", [*sets.values(), source_id])
    history.record(svc, row["case_id"], "source.updated", "source", source_id, f"Source [S{source_id}] updated: {', '.join(sets)}", before, sets)
    changes = relations_mod.recompute_for_source(svc, source_id, reason="source origin changed") if "origin" in sets else []
    return {"created": False, "updated": True, "source": view(svc, get_row(svc, source_id)), "status_changes": changes}


def get(svc, source_id: int, *, max_chars: int = 4000, offset: int = 0) -> dict:
    row = get_row(svc, source_id)
    out = view(svc, row, with_text=True, max_chars=max_chars, offset=offset)
    out["evidence"] = [
        {"id": e["id"], "relation_id": e["relation_id"], "entity_id": e["entity_id"], "attribute": e["attribute"],
         "quote": clip(e["quote"], 240), "locator": e["locator"]}
        for e in svc.db.query("SELECT * FROM evidence WHERE source_id = ? ORDER BY id LIMIT 50", (source_id,))]
    return out


def retract(svc, source_id: int, *, action: str = "retract", reason: str = "", confirm: bool = False) -> dict:
    """Retract (or restore) a source. Its evidence stays on file, but relations that only it supported
    become ``unsupported``; nothing is deleted. ``action=delete`` is only for sources nothing refers to."""
    from . import relations as relations_mod
    row = get_row(svc, source_id)
    case_id = row["case_id"]
    if action == "delete":
        if not confirm:
            raise AtlasError("Deleting a source is permanent. Pass confirm=true (or retract it instead to keep the record).")
        used = svc.db.one("SELECT COUNT(*) c FROM evidence WHERE source_id = ?", (source_id,))["c"]
        if used:
            raise AtlasError(f"Source {source_id} is cited by {used} evidence item(s): retract it instead of deleting it.")
        svc.db.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        history.record(svc, case_id, "source.deleted", "source", source_id, f"Source [S{source_id}] deleted: {row['title']}")
        return {"deleted": True, "source_id": source_id}
    if action not in ("retract", "restore"):
        raise AtlasError("action must be retract, restore or delete.")
    if action == "retract":
        if row["retracted"]:
            return {"retracted": True, "changed": False, "source": view(svc, row), "affected": {}}
        svc.db.execute("UPDATE sources SET retracted = 1, retract_reason = ?, retracted_ts = ? WHERE id = ?",
                       (reason.strip()[:500], svc.clock(), source_id))
        history.record(svc, case_id, "source.retracted", "source", source_id, f"Source [S{source_id}] retracted: {reason.strip()[:120]}",
                       {"retracted": False}, {"retracted": True, "reason": reason.strip()[:500]})
        svc.emit("atlas.source.retracted", {"case": case_id, "source": source_id, "title": clip(row["title"], 60)})
    else:
        if not row["retracted"]:
            return {"retracted": False, "changed": False, "source": view(svc, row), "affected": {}}
        svc.db.execute("UPDATE sources SET retracted = 0, retract_reason = '', retracted_ts = NULL WHERE id = ?", (source_id,))
        history.record(svc, case_id, "source.restored", "source", source_id, f"Source [S{source_id}] restored",
                       {"retracted": True}, {"retracted": False})
    affected = relations_mod.cascade_after_source_change(svc, source_id, reason=f"source S{source_id} {action}ed")
    return {"retracted": action == "retract", "changed": True, "source": view(svc, get_row(svc, source_id)), "affected": affected}


def search(svc, case_id: int, query: str, *, kind: str | None = None, include_retracted: bool = False,
           limit: int = 10, cursor: str | None = None) -> dict:
    cases_mod.get_row(svc, case_id)
    sql = ("SELECT s.*, snippet(sources_fts, 1, '[', ']', '…', 14) AS snip, bm25(sources_fts) AS rank "
           "FROM sources_fts JOIN sources s ON s.id = sources_fts.rowid WHERE sources_fts MATCH ? AND s.case_id = ?")
    params: list[Any] = [fts_query(query), case_id]
    if kind:
        sql += " AND s.kind = ?"
        params.append(kind)
    if not include_retracted:
        sql += " AND s.retracted = 0"
    sql += " ORDER BY rank LIMIT 200"
    rows = []
    for r in svc.db.query(sql, params):
        item = view(svc, r)
        item["snippet"] = r["snip"]
        rows.append(item)
    items, nxt = page(rows, limit, cursor)
    return {"case_id": case_id, "query": query, "items": items, "next_cursor": nxt, "total": len(rows)}


def list_sources(svc, case_id: int, *, kind: str | None = None, include_retracted: bool = True, limit: int = 50,
                 cursor: str | None = None) -> dict:
    cases_mod.get_row(svc, case_id)
    sql, params = "SELECT * FROM sources WHERE case_id = ?", [case_id]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if not include_retracted:
        sql += " AND retracted = 0"
    rows = [view(svc, r) for r in svc.db.query(sql + " ORDER BY id", params)]
    items, nxt = page(rows, limit, cursor)
    return {"case_id": case_id, "items": items, "next_cursor": nxt, "total": len(rows)}
