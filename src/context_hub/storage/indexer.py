"""Transactional incremental index maintenance."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..scanner import scan_repository
from .database import IndexDatabase


@dataclass(frozen=True)
class IndexResult:
    scanned: int
    new: int
    modified: int
    unchanged: int
    deleted: int
    parsed: int


def index_repository(root: Path, *, force: bool = False, database_path: Path | None = None) -> IndexResult:
    root = root.resolve()
    repository = scan_repository(root)
    database_path = database_path or root / ".context-hub" / "index.db"
    with IndexDatabase(database_path) as database:
        assert database.connection is not None
        connection = database.connection
        now = datetime.now(timezone.utc).isoformat()
        repo = database.repository(root)
        if not repo:
            cursor = connection.execute("INSERT INTO repositories(root_path,name,created_at,updated_at,schema_version) VALUES(?,?,?,?,?)",
                (str(root), root.name, now, now, 1))
            repo_id = cursor.lastrowid
            existing: dict[str, sqlite3.Row] = {}
        else:
            repo_id = repo["id"]
            existing = {row["relative_path"]: row for row in connection.execute("SELECT * FROM files WHERE repository_id=?", (repo_id,))}
        current = {item.path: item for item in repository.files}
        new = [p for p in current if p not in existing]
        modified = [p for p in current if p in existing and (force or current[p].content_hash != existing[p]["content_hash"])]
        unchanged = [p for p in current if p in existing and p not in modified]
        deleted = [p for p in existing if p not in current]
        try:
            connection.execute("BEGIN")
            for path in deleted:
                connection.execute("DELETE FROM files WHERE id=?", (existing[path]["id"],))
            for path in new + modified:
                item = current[path]
                old = existing.get(path)
                if old:
                    connection.execute("DELETE FROM files WHERE id=?", (old["id"],))
                parsed = item.parsed
                cursor = connection.execute("INSERT INTO files(repository_id,relative_path,language,size,content_hash,modified_time,indexed_at,parse_status,parse_error) VALUES(?,?,?,?,?,?,?,?,?)",
                    (repo_id, item.path, item.language, item.size, item.content_hash, item.modified_at.isoformat(), now,
                     "error" if parsed and parsed.parse_error else "parsed" if parsed else "skipped", parsed.parse_error if parsed else None))
                file_id = cursor.lastrowid
                if parsed:
                    for symbol in parsed.symbols:
                        connection.execute("INSERT INTO symbols(file_id,name,kind,language,start_line,end_line,parent_name,stable_symbol_id) VALUES(?,?,?,?,?,?,?,?)",
                            (file_id, symbol.name, symbol.kind.value, symbol.language, symbol.start_line, symbol.end_line, symbol.parent,
                             f"{item.path}:{symbol.name}:{symbol.start_line}"))
                    for imported in parsed.imports:
                        target = _resolve_import(imported.name, current)
                        target_id = None
                        if target and target in existing and target not in new + modified:
                            target_id = existing[target]["id"]
                        connection.execute("INSERT INTO imports(file_id,imported_name,resolved_target_file_id,resolved,confidence) VALUES(?,?,?,?,?)",
                            (file_id, imported.name, target_id, int(target is not None), 1.0))
            connection.execute("UPDATE repositories SET updated_at=?,last_indexed_at=? WHERE id=?", (now, now, repo_id))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return IndexResult(len(current), len(new), len(modified), len(unchanged), len(deleted), len(new) + len(modified))


def _resolve_import(name: str, files: dict[str, object]) -> str | None:
    module = name.replace(".", "/")
    for candidate in (module, module + ".py", module + "/__init__.py"):
        if candidate in files:
            return candidate
    return None

