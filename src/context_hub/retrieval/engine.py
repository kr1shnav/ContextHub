from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import RetrievalConfig, RetrievalQuery, RetrievalResult
from .query import normalize_query, tokenize


class RetrievalEngine:
    """Search indexed metadata without reading or parsing repository source."""
    def __init__(self, database_path: Path, config: RetrievalConfig | None = None):
        self.database_path = database_path
        self.config = config or RetrievalConfig()

    def search(self, query: RetrievalQuery | str) -> list[RetrievalResult]:
        query = RetrievalQuery(task=query, config=self.config) if isinstance(query, str) else query
        terms = normalize_query(query.task)
        if not terms:
            return []
        try:
            connection = sqlite3.connect(self.database_path)
            connection.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise RuntimeError("Unable to open Context Hub index. Run `ctx index` first.") from exc
        try:
            files = connection.execute("SELECT * FROM files").fetchall()
            symbols = connection.execute("SELECT * FROM symbols").fetchall()
            imports = connection.execute("SELECT i.*, f.relative_path FROM imports i JOIN files f ON f.id=i.file_id").fetchall()
        finally:
            connection.close()
        candidates: dict[str, RetrievalResult] = {}
        for file in files:
            path_tokens = set(tokenize(file["relative_path"]))
            import_tokens = set(tokenize(" ".join(row["imported_name"] for row in imports if row["file_id"] == file["id"])) )
            matched = set(terms) & (path_tokens | import_tokens)
            score = min(1.0, len(matched) / max(1, len(terms)) * self.config.path_weight)
            signals = ["path_match"] if matched else []
            reasons = [f"Path/import token match: {', '.join(sorted(matched))}"] if matched else []
            candidates[f"file:{file['relative_path']}"] = RetrievalResult(item_id=f"file:{file['relative_path']}", path=file["relative_path"], score=score,
                signals=signals, reasons=reasons, metadata={"language": file["language"], "size": file["size"]},
                estimated_characters=file["size"], estimated_tokens=max(1, file["size"] // 4))
        direct_paths: set[str] = set()
        for symbol in symbols:
            file = next((row for row in files if row["id"] == symbol["file_id"]), None)
            if not file:
                continue
            symbol_tokens = set(tokenize(symbol["name"]))
            matched = set(terms) & symbol_tokens
            if not matched:
                continue
            path = file["relative_path"]
            direct_paths.add(path)
            item_id = f"symbol:{path}:{symbol['name']}:{symbol['start_line']}"
            score = min(1.0, self.config.exact_symbol_weight + len(matched) / max(1, len(terms)) * self.config.token_weight)
            candidates[item_id] = RetrievalResult(item_id=item_id, item_type="symbol", path=path, symbol=symbol["name"], score=score,
                signals=["symbol_match"], reasons=[f"Symbol token match: {symbol['name']}"], metadata={"kind": symbol["kind"], "line": symbol["start_line"]},
                estimated_characters=file["size"], estimated_tokens=max(1, file["size"] // 4))
        # Add bounded structural context around directly matched files.
        for row in imports:
            source = row["relative_path"]
            target = next((f["relative_path"] for f in files if f["id"] == row["resolved_target_file_id"]), None)
            if not target:
                continue
            if source in direct_paths and f"file:{target}" in candidates:
                candidates[f"file:{target}"].score = min(1.0, candidates[f"file:{target}"].score + self.config.graph_weight)
                candidates[f"file:{target}"].signals.append("dependency_match")
                candidates[f"file:{target}"].reasons.append(f"Dependency of directly matched file: {source}")
            if target in direct_paths and f"file:{source}" in candidates:
                candidates[f"file:{source}"].score = min(1.0, candidates[f"file:{source}"].score + self.config.graph_weight)
                candidates[f"file:{source}"].signals.append("dependent_match")
                candidates[f"file:{source}"].reasons.append(f"Dependent of directly matched file: {target}")
        limit = query.max_results or self.config.max_results
        return sorted((r for r in candidates.values() if r.score >= self.config.minimum_score),
                      key=lambda r: (-r.score, r.path, r.symbol or ""))[:limit]

