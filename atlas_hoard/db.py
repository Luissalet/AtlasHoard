"""SQLite connection (WAL) and ordered schema migrations."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

MIGRATIONS: list[str] = [
    # 1: cases, sources (+FTS), entities (+FTS), predicates, relations, evidence, hypotheses, ACH, enrichment, history
    """
    CREATE TABLE cases (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      question TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'open',
      tags TEXT NOT NULL DEFAULT '[]',
      summary TEXT NOT NULL DEFAULT '',
      open_questions TEXT NOT NULL DEFAULT '[]',
      created_ts REAL NOT NULL,
      updated_ts REAL NOT NULL
    );
    CREATE TABLE sources (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
      kind TEXT NOT NULL DEFAULT 'text',
      title TEXT NOT NULL DEFAULT '',
      url TEXT NOT NULL DEFAULT '',
      origin TEXT NOT NULL DEFAULT '',
      reliability TEXT NOT NULL DEFAULT 'F',
      credibility TEXT NOT NULL DEFAULT '6',
      captured_at TEXT,
      published_at TEXT,
      content_hash TEXT NOT NULL DEFAULT '',
      text TEXT NOT NULL DEFAULT '',
      ref TEXT NOT NULL DEFAULT '',
      ref_revision TEXT NOT NULL DEFAULT '',
      note TEXT NOT NULL DEFAULT '',
      retracted INTEGER NOT NULL DEFAULT 0,
      retract_reason TEXT NOT NULL DEFAULT '',
      retracted_ts REAL,
      created_ts REAL NOT NULL,
      run_id INTEGER
    );
    CREATE INDEX sources_case ON sources(case_id);
    CREATE INDEX sources_ref ON sources(case_id, ref, ref_revision);
    CREATE VIRTUAL TABLE sources_fts USING fts5(title, text, url, note, content='sources', content_rowid='id');
    CREATE TRIGGER sources_ai AFTER INSERT ON sources BEGIN
      INSERT INTO sources_fts(rowid, title, text, url, note) VALUES (new.id, new.title, new.text, new.url, new.note);
    END;
    CREATE TRIGGER sources_ad AFTER DELETE ON sources BEGIN
      INSERT INTO sources_fts(sources_fts, rowid, title, text, url, note) VALUES ('delete', old.id, old.title, old.text, old.url, old.note);
    END;
    CREATE TRIGGER sources_au AFTER UPDATE ON sources BEGIN
      INSERT INTO sources_fts(sources_fts, rowid, title, text, url, note) VALUES ('delete', old.id, old.title, old.text, old.url, old.note);
      INSERT INTO sources_fts(rowid, title, text, url, note) VALUES (new.id, new.title, new.text, new.url, new.note);
    END;
    CREATE TABLE entities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
      type TEXT NOT NULL DEFAULT 'concept',
      name TEXT NOT NULL,
      norm_name TEXT NOT NULL DEFAULT '',
      aliases TEXT NOT NULL DEFAULT '[]',
      description TEXT NOT NULL DEFAULT '',
      attributes TEXT NOT NULL DEFAULT '{}',
      lat REAL,
      lon REAL,
      geo_precision TEXT NOT NULL DEFAULT '',
      date_start TEXT,
      date_end TEXT,
      wikidata_qid TEXT NOT NULL DEFAULT '',
      private_person INTEGER NOT NULL DEFAULT 0,
      public_figure INTEGER NOT NULL DEFAULT 0,
      merged_into INTEGER,
      created_ts REAL NOT NULL,
      updated_ts REAL NOT NULL,
      run_id INTEGER
    );
    CREATE INDEX entities_case ON entities(case_id, type);
    CREATE INDEX entities_norm ON entities(case_id, norm_name);
    CREATE VIRTUAL TABLE entities_fts USING fts5(name, aliases, description, content='entities', content_rowid='id');
    CREATE TRIGGER entities_ai AFTER INSERT ON entities BEGIN
      INSERT INTO entities_fts(rowid, name, aliases, description) VALUES (new.id, new.name, new.aliases, new.description);
    END;
    CREATE TRIGGER entities_ad AFTER DELETE ON entities BEGIN
      INSERT INTO entities_fts(entities_fts, rowid, name, aliases, description) VALUES ('delete', old.id, old.name, old.aliases, old.description);
    END;
    CREATE TRIGGER entities_au AFTER UPDATE ON entities BEGIN
      INSERT INTO entities_fts(entities_fts, rowid, name, aliases, description) VALUES ('delete', old.id, old.name, old.aliases, old.description);
      INSERT INTO entities_fts(rowid, name, aliases, description) VALUES (new.id, new.name, new.aliases, new.description);
    END;
    CREATE TABLE predicates (
      name TEXT PRIMARY KEY,
      label TEXT NOT NULL DEFAULT '',
      functional INTEGER NOT NULL DEFAULT 0,
      symmetric INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE relations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
      subject_id INTEGER NOT NULL REFERENCES entities(id),
      predicate TEXT NOT NULL,
      object_id INTEGER NOT NULL REFERENCES entities(id),
      valid_from TEXT,
      valid_to TEXT,
      observed_at TEXT,
      status TEXT NOT NULL DEFAULT 'unsupported',
      manual_status TEXT NOT NULL DEFAULT '',
      manual_reason TEXT NOT NULL DEFAULT '',
      confidence REAL NOT NULL DEFAULT 0.5,
      notes TEXT NOT NULL DEFAULT '',
      derived_from TEXT NOT NULL DEFAULT '[]',
      created_ts REAL NOT NULL,
      updated_ts REAL NOT NULL,
      run_id INTEGER
    );
    CREATE INDEX relations_case ON relations(case_id);
    CREATE INDEX relations_subject ON relations(subject_id);
    CREATE INDEX relations_object ON relations(object_id);
    CREATE TABLE evidence (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
      relation_id INTEGER REFERENCES relations(id),
      entity_id INTEGER REFERENCES entities(id),
      attribute TEXT NOT NULL DEFAULT '',
      source_id INTEGER NOT NULL REFERENCES sources(id),
      quote TEXT NOT NULL DEFAULT '',
      locator TEXT NOT NULL DEFAULT '',
      observed_at TEXT,
      created_ts REAL NOT NULL,
      run_id INTEGER
    );
    CREATE INDEX evidence_case ON evidence(case_id);
    CREATE INDEX evidence_relation ON evidence(relation_id);
    CREATE INDEX evidence_entity ON evidence(entity_id);
    CREATE INDEX evidence_source ON evidence(source_id);
    CREATE TABLE hypotheses (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
      statement TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'open',
      created_ts REAL NOT NULL,
      updated_ts REAL NOT NULL
    );
    CREATE INDEX hypotheses_case ON hypotheses(case_id);
    CREATE TABLE ach_ratings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      hypothesis_id INTEGER NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
      evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
      rating TEXT NOT NULL,
      note TEXT NOT NULL DEFAULT '',
      updated_ts REAL NOT NULL,
      UNIQUE(hypothesis_id, evidence_id)
    );
    CREATE TABLE enrichment_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
      enricher TEXT NOT NULL,
      entity_id INTEGER,
      inputs TEXT NOT NULL DEFAULT '{}',
      created TEXT NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'ok',
      note TEXT NOT NULL DEFAULT '',
      created_ts REAL NOT NULL,
      undone_ts REAL
    );
    CREATE TABLE history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id INTEGER,
      ts REAL NOT NULL,
      caller TEXT NOT NULL DEFAULT 'system',
      action TEXT NOT NULL,
      target_type TEXT NOT NULL DEFAULT '',
      target_id INTEGER,
      summary TEXT NOT NULL DEFAULT '',
      before TEXT,
      after TEXT
    );
    CREATE INDEX history_case ON history(case_id, id);
    CREATE INDEX history_target ON history(case_id, target_type, target_id);
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
    # 2: geocoding cache (Nominatim terms: never ask twice for the same query)
    """
    CREATE TABLE geocode_cache (
      query TEXT PRIMARY KEY,
      result TEXT NOT NULL,
      ts REAL NOT NULL
    );
    """,
]


class Database:
    """One connection shared by every thread, guarded by a re-entrant lock.

    The app is the only writer; the MCP bridge never opens this file.
    """

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.migrate()

    def migrate(self) -> None:
        with self.lock:
            self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            current = row["v"] or 0
            for index, sql in enumerate(MIGRATIONS, start=1):
                if index <= current:
                    continue
                script = f"BEGIN;\n{sql}\nINSERT INTO schema_version(version) VALUES ({index});\nCOMMIT;"
                try:
                    self.conn.executescript(script)
                except Exception:
                    if self.conn.in_transaction:
                        self.conn.execute("ROLLBACK")
                    raise

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, params)

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def transaction(self):
        """`with db.transaction():` — BEGIN IMMEDIATE / COMMIT (ROLLBACK on error) under the lock."""
        return _Transaction(self)

    def close(self) -> None:
        with self.lock:
            try:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            self.conn.close()


class _Transaction:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self):
        self.db.lock.acquire()
        self.db.conn.execute("BEGIN IMMEDIATE")
        return self.db.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.db.conn.execute("COMMIT")
            else:
                self.db.conn.execute("ROLLBACK")
        finally:
            self.db.lock.release()
        return False
