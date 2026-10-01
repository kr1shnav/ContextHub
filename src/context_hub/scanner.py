"""Deterministic repository file discovery and parsing."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from .languages import detect_language
from .models import Repository, RepositoryFile
from .parsing import parser_for

DEFAULT_IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", "coverage", ".context-hub"}
SECRET_NAMES = {".env", "credentials", "secrets"}
SECRET_SUFFIXES = {".pem", ".key", ".p12"}


def ignored(path: Path, root: Path, gitignore: list[str]) -> bool:
    rel = path.relative_to(root).as_posix()
    if any(part in DEFAULT_IGNORED for part in path.relative_to(root).parts):
        return True
    if path.name in SECRET_NAMES or path.name.startswith(".env.") or path.suffix.lower() in SECRET_SUFFIXES:
        return True
    return any(rel == rule or rel.startswith(rule.rstrip("/") + "/") for rule in gitignore if rule and not rule.startswith("#"))


def scan_repository(root: Path) -> Repository:
    root = root.resolve()
    rules = (root / ".gitignore").read_text(encoding="utf-8").splitlines() if (root / ".gitignore").is_file() else []
    files: list[RepositoryFile] = []
    for directory, dirs, names in os.walk(root):
        current = Path(directory)
        dirs[:] = [d for d in dirs if not ignored(current / d, root, rules)]
        for name in names:
            path = current / name
            if ignored(path, root, rules):
                continue
            try:
                raw = path.read_bytes()
                if b"\0" in raw:
                    continue
                stat = path.stat()
                language = detect_language(path)
                text = raw.decode("utf-8")
                parsed = parser_for(language).parse(text, file=path.relative_to(root).as_posix(), language=language) if language != "Other" else None
                files.append(RepositoryFile(path=path.relative_to(root).as_posix(), language=language, size=stat.st_size,
                    content_hash=hashlib.sha256(raw).hexdigest(), modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                    lines=text.count("\n") + (1 if text else 0), parsed=parsed))
            except (OSError, UnicodeDecodeError):
                continue
    return Repository(root=str(root), files=sorted(files, key=lambda item: item.path))

