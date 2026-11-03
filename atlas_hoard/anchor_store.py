"""Anchor persistence for Workspace: revisions history, anchors, per-revision statuses, comments.

An anchor stays pinned to the revision it was made on. Each later revision that
Atlas observes gets its own resolution row, so history is never rewritten.
Atlas reads file bytes to hash and locate places; it never changes them.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import secrets
import time

from . import anchors as engine

SCHEMA = """
    CREATE TABLE IF NOT EXISTS file_revisions (
      file_id TEXT NOT NULL REFERENCES files(id), seq INTEGER NOT NULL, revision TEXT NOT NULL,
      size INTEGER NOT NULL, seen REAL NOT NULL, PRIMARY KEY(file_id, seq));
    CREATE TABLE IF NOT EXISTS anchors (
      id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), file_id TEXT NOT NULL REFERENCES files(id),
      kind TEXT NOT NULL, label TEXT NOT NULL, selector TEXT NOT NULL, snapshot TEXT NOT NULL,
      revision TEXT NOT NULL, created_seq INTEGER NOT NULL, author TEXT NOT NULL, created REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS anchors_file ON anchors(file_id);
    CREATE TABLE IF NOT EXISTS anchor_status (
      anchor_id TEXT NOT NULL REFERENCES anchors(id), seq INTEGER NOT NULL, revision TEXT NOT NULL,
      status TEXT NOT NULL, location TEXT, detail TEXT NOT NULL, checked REAL NOT NULL, PRIMARY KEY(anchor_id, seq));
    CREATE TABLE IF NOT EXISTS anchor_comments (
      id INTEGER PRIMARY KEY AUTOINCREMENT, anchor_id TEXT NOT NULL REFERENCES anchors(id), seq INTEGER NOT NULL,
      revision TEXT NOT NULL, author TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL);
"""


def _err(message, status=400):
    from .store import StoreError
    return StoreError(message, status)


class AnchorMixin:
    def _init_anchors(self):
        self.db.executescript(SCHEMA)
        # Files registered before anchors existed start their history at the revision they have now.
        self.db.execute("INSERT INTO file_revisions SELECT id,1,revision,size,updated FROM files "
                        "WHERE id NOT IN (SELECT file_id FROM file_revisions)")

    # --- revision history -------------------------------------------------
    def _current_seq(self, file_id):
        row = self.db.execute("SELECT MAX(seq) FROM file_revisions WHERE file_id=?", (file_id,)).fetchone()
        return row[0] or 1

    def _note_revision(self, file_id, revision, size, path):
        last = self.db.execute("SELECT seq,revision FROM file_revisions WHERE file_id=? ORDER BY seq DESC LIMIT 1", (file_id,)).fetchone()
        if last and last["revision"] == revision:
            return last["seq"]
        seq = (last["seq"] if last else 0) + 1
        self.db.execute("INSERT INTO file_revisions VALUES (?,?,?,?,?)", (file_id, seq, revision, size, time.time()))
        if last:
            try:
                self._reresolve(file_id, seq, revision, path)
            except Exception:
                logging.getLogger("atlas").exception("Anchor re-resolution failed")
        return seq

    def _read_revision(self, path, revision, kind):
        """Bytes of the revision, None if too large (kinds that can do without), 409 if the file moved on."""
        if path.stat().st_size > engine.MAX_ANCHOR_BYTES:
            return None
        data = path.read_bytes()
        if "sha256:" + hashlib.sha256(data).hexdigest() != revision:
            raise _err("file changed while it was being read; try again", 409)
        return data

    def _reresolve(self, file_id, seq, revision, path):
        rows = self.db.execute("SELECT * FROM anchors WHERE file_id=? AND created_seq<?", (file_id, seq)).fetchall()
        if not rows or not Path(path).is_file():
            return
        try:
            data = self._read_revision(Path(path), revision, None)
        except Exception:
            return
        for row in rows:
            status, location, detail = engine.resolve(row["kind"], json.loads(row["selector"]), json.loads(row["snapshot"]), data, Path(path).name)
            self._store_status(row["id"], seq, revision, status, location, detail)

    def _store_status(self, anchor_id, seq, revision, status, location, detail):
        self.db.execute("INSERT OR REPLACE INTO anchor_status VALUES (?,?,?,?,?,?,?)",
                        (anchor_id, seq, revision, status, json.dumps(location, ensure_ascii=False) if location else None, detail, time.time()))

    # --- views -----------------------------------------------------------
    def _seq_of(self, file_id, value):
        if value is None:
            return self._current_seq(file_id)
        if isinstance(value, bool):
            raise _err("revision must be a sequence number or a sha256 hash")
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            row = self.db.execute("SELECT seq FROM file_revisions WHERE file_id=? AND seq=?", (file_id, int(value))).fetchone()
        else:
            row = self.db.execute("SELECT MAX(seq) AS seq FROM file_revisions WHERE file_id=? AND revision=?", (file_id, str(value))).fetchone()
        if row is None or row["seq"] is None:
            raise _err("revision not known to Atlas for this file", 404)
        return row["seq"]

    def _status_at(self, anchor_id, seq):
        return self.db.execute("SELECT * FROM anchor_status WHERE anchor_id=? AND seq<=? ORDER BY seq DESC LIMIT 1", (anchor_id, seq)).fetchone()

    def _anchor_view(self, row, seq=None):
        seq = self._current_seq(row["file_id"]) if seq is None else seq
        st = self._status_at(row["id"], seq)
        return {"id": row["id"], "uri": f"hoard://atlas/anchor/{row['id']}", "project_id": row["project_id"], "file_id": row["file_id"],
                "kind": row["kind"], "label": row["label"], "selector": json.loads(row["selector"]),
                "revision": row["revision"], "revision_seq": row["created_seq"], "author": row["author"], "created": row["created"],
                "at_revision_seq": seq, "status": st["status"], "status_revision_seq": st["seq"],
                "location": json.loads(st["location"]) if st["location"] else None, "detail": st["detail"],
                "stale": st["seq"] != seq and seq > row["created_seq"], "comment_count": self.db.execute(
                    "SELECT COUNT(*) FROM anchor_comments WHERE anchor_id=?", (row["id"],)).fetchone()[0]}

    def _comments(self, anchor_id):
        out = []
        for c in self.db.execute("SELECT * FROM anchor_comments WHERE anchor_id=? ORDER BY id", (anchor_id,)):
            st = self._status_at(anchor_id, c["seq"])
            out.append({"id": c["id"], "text": c["body"], "author": c["author"], "created": c["created"],
                        "revision_seq": c["seq"], "revision": c["revision"], "status_at_revision": st["status"] if st else None})
        return out

    def _history(self, row):
        out = []
        for r in self.db.execute("SELECT s.*, v.seen FROM anchor_status s JOIN file_revisions v ON v.file_id=? AND v.seq=s.seq "
                                 "WHERE s.anchor_id=? ORDER BY s.seq", (row["file_id"], row["id"])):
            out.append({"revision_seq": r["seq"], "revision": r["revision"], "status": r["status"], "detail": r["detail"],
                        "location": json.loads(r["location"]) if r["location"] else None, "checked": r["checked"], "seen": r["seen"]})
        return out

    def _anchor_row(self, anchor_id, caller):
        row = self.db.execute("SELECT * FROM anchors WHERE id=?", (str(anchor_id),)).fetchone()
        if row is None:
            raise _err("anchor not found", 404)
        self._project(row["project_id"], caller)
        return row

    # --- tools -----------------------------------------------------------
    def anchor_create(self, args, caller):
        from .store import text

        def create():
            row, project = self._file(args.get("file_id"), caller)
            kind = args.get("kind")
            label = text(args.get("label", ""), "label", 200)
            comment = text(args.get("comment", ""), "comment", 4000)
            row = self._refresh(row, project)
            if row["state"] != "available":
                raise _err("file is missing; restore it before anchoring", 409)
            seq = self._current_seq(row["id"])
            if args.get("revision") is not None and self._seq_of(row["id"], args["revision"]) != seq:
                raise _err(f"anchors are made on the current revision (r{seq}); an older revision's content is no longer available", 409)
            path = Path(row["external_path"]) if row["external_path"] else self._path(project, row["relative_path"])
            try:
                data = self._read_revision(path, row["revision"], kind)
                selector, snapshot = engine.capture(kind, args.get("selector"), data, path.name)
            except engine.AnchorError as exc:
                raise _err(str(exc), exc.status) from None
            uid = secrets.token_hex(8)
            now = time.time()
            self.db.execute("INSERT INTO anchors VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (uid, project["id"], row["id"], kind, label or kind, json.dumps(selector, ensure_ascii=False),
                             json.dumps(snapshot, ensure_ascii=False), row["revision"], seq, caller, now))
            self._store_status(uid, seq, row["revision"], "intact", selector, "anchored on this revision")
            if comment:
                self.db.execute("INSERT INTO anchor_comments (anchor_id,seq,revision,author,body,created) VALUES (?,?,?,?,?,?)",
                                (uid, seq, row["revision"], caller, comment, now))
            created = self.db.execute("SELECT * FROM anchors WHERE id=?", (uid,)).fetchone()
            return {"ok": True, "anchor": self._anchor_view(created)}
        return self._mutate("atlas_anchor_create", args, caller, create)

    def anchor_comment(self, args, caller):
        from .store import text

        def comment():
            row = self._anchor_row(args.get("anchor_id"), caller)
            body = text(args.get("text", ""), "text", 4000, required=True)
            frow, project = self._file(row["file_id"], caller)
            frow = self._refresh(frow, project)
            seq = self._current_seq(frow["id"])
            self.db.execute("INSERT INTO anchor_comments (anchor_id,seq,revision,author,body,created) VALUES (?,?,?,?,?,?)",
                            (row["id"], seq, frow["revision"], caller, body, time.time()))
            return {"ok": True, "anchor": self._anchor_view(row), "comments": self._comments(row["id"])}
        return self._mutate("atlas_anchor_comment", args, caller, comment)

    def anchor_get(self, args, caller):
        row = self._anchor_row(args.get("anchor_id"), caller)
        return {"ok": True, "anchor": self._anchor_view(row), "history": self._history(row), "comments": self._comments(row["id"])}

    def anchor_list(self, args, caller):
        from .store import text
        file_id, project_id = args.get("file_id"), args.get("project_id")
        if not file_id and not project_id:
            raise _err("give file_id or project_id")
        if file_id:
            frow, project = self._file(file_id, caller, project_id)
            where, params = "file_id=?", [frow["id"]]
        else:
            project = self._project(project_id, caller)
            where, params = "project_id=?", [project["id"]]
        if args.get("kind"):
            if args["kind"] not in engine.KINDS:
                raise _err("unknown anchor kind")
            where += " AND kind=?"
            params.append(args["kind"])
        status = args.get("status")
        if status is not None and status not in engine.STATUSES:
            raise _err("status must be intact, moved, changed or lost")
        limit, offset = args.get("limit", 100), args.get("offset", 0)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500 or not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise _err("limit must be 1-500 and offset 0 or more")
        revision = args.get("revision")
        views, revisions = [], None
        seqs = {}
        for row in self.db.execute(f"SELECT * FROM anchors WHERE {where} ORDER BY created, id", params).fetchall():
            if row["file_id"] not in seqs:
                seqs[row["file_id"]] = self._seq_of(row["file_id"], revision) if (revision is not None and file_id) else self._current_seq(row["file_id"])
            seq = seqs[row["file_id"]]
            if row["created_seq"] > seq:
                continue
            view = self._anchor_view(row, seq)
            if status is None or view["status"] == status:
                views.append(view)
        if file_id:
            revisions = [{"seq": r["seq"], "revision": r["revision"], "size": r["size"], "seen": r["seen"]} for r in
                         self.db.execute("SELECT * FROM file_revisions WHERE file_id=? ORDER BY seq", (frow["id"],))]
        summary = {s: sum(1 for v in views if v["status"] == s) for s in engine.STATUSES}
        result = {"ok": True, "anchors": views[offset:offset + limit], "total": len(views), "summary": summary, "limit": limit, "offset": offset}
        if revisions is not None:
            result["revisions"] = revisions
        return result

    def anchor_resolve(self, args, caller):
        row = self._anchor_row(args.get("anchor_id"), caller)
        frow, project = self._file(row["file_id"], caller)
        frow = self._refresh(frow, project)
        current = self._current_seq(frow["id"])
        seq = self._seq_of(frow["id"], args.get("revision")) if args.get("revision") is not None else current
        if row["created_seq"] > seq:
            raise _err("the anchor did not exist at that revision", 404)
        view = self._anchor_view(row, seq)
        fview = self._file_view(frow, project)
        rev = self.db.execute("SELECT * FROM file_revisions WHERE file_id=? AND seq=?", (frow["id"], seq)).fetchone()
        viewable = seq == current and fview["exists"] and frow["state"] == "available"
        opened = {"file_id": frow["id"], "path": fview["path"], "file_uri": fview["uri"], "anchor_uri": view["uri"],
                  "revision": rev["revision"], "revision_seq": seq, "current_revision_seq": current, "viewable": viewable,
                  "status": view["status"], **engine.open_block(row["kind"], view["location"])}
        return {"ok": True, "anchor": view, "status": view["status"], "detail": view["detail"], "location": view["location"],
                "file": fview, "open": opened, "origin": {"revision": row["revision"], "revision_seq": row["created_seq"], "selector": json.loads(row["selector"])},
                "history": self._history(row), "comments": self._comments(row["id"])}
