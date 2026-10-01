"""Extensible filename-to-language registry."""
from __future__ import annotations

from pathlib import Path

LANGUAGE_BY_SUFFIX = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".java": "Java", ".c": "C", ".h": "C", ".cc": "C++",
    ".cpp": "C++", ".hpp": "C++", ".go": "Go", ".rs": "Rust", ".html": "HTML",
    ".css": "CSS", ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".md": "Markdown",
    ".markdown": "Markdown", ".sql": "SQL", ".sh": "Shell", ".bash": "Shell",
}


def detect_language(path: Path) -> str:
    if path.name in {"Dockerfile", "Makefile"}:
        return "Shell"
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "Other")

