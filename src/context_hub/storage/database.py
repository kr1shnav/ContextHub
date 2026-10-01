"""SQLite storage abstraction for the repository index."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


class IndexDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def open(self) -> "IndexDatabase":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.initialize()
        return self

    def initialize(self) -> None:
        assert self.connection is not None
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS repositories (
                id INTEGER PRIMARY KEY, root_path TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_indexed_at TEXT,
                schema_version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY, repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                relative_path TEXT NOT NULL, language TEXT NOT NULL, size INTEGER NOT NULL,
                content_hash TEXT NOT NULL, modified_time TEXT NOT NULL, indexed_at TEXT NOT NULL,
                parse_status TEXT NOT NULL, parse_error TEXT,
                UNIQUE(repository_id, relative_path)
            );
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                name TEXT NOT NULL, kind TEXT NOT NULL, language TEXT NOT NULL,
                start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, parent_name TEXT,
                stable_symbol_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                imported_name TEXT NOT NULL, resolved_target_file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
                resolved INTEGER NOT NULL, confidence REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_files_repo ON files(repository_id);
            CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
            CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_id);
        """)
        self.connection.execute("INSERT OR IGNORE INTO metadata VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        self.connection.commit()

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> "IndexDatabase":
        return self.open()

    def __exit__(self, *_: object) -> None:
        self.close()

    def repository(self, root: Path) -> sqlite3.Row | None:
        assert self.connection is not None
        return self.connection.execute("SELECT * FROM repositories WHERE root_path = ?", (str(root),)).fetchone()

    def status(self, root: Path) -> dict[str, object] | None:
        repo = self.repository(root)
        if not repo:
            return None
        assert self.connection is not None
        return {
            "repository": repo["name"], "root": repo["root_path"], "last_indexed": repo["last_indexed_at"],
            "files": self.connection.execute("SELECT COUNT(*) FROM files WHERE repository_id=?", (repo["id"],)).fetchone()[0],
            "symbols": self.connection.execute("SELECT COUNT(*) FROM symbols s JOIN files f ON f.id=s.file_id WHERE f.repository_id=?", (repo["id"],)).fetchone()[0],
            "imports": self.connection.execute("SELECT COUNT(*) FROM imports i JOIN files f ON f.id=i.file_id WHERE f.repository_id=?", (repo["id"],)).fetchone()[0],
        }

