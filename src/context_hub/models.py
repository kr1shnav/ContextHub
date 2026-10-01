"""Stable repository-intelligence data contracts."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class SymbolKind(StrEnum):
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"


class Import(BaseModel):
    name: str
    line: int
    source: str | None = None


class Symbol(BaseModel):
    name: str
    kind: SymbolKind
    file: str
    start_line: int
    end_line: int
    parent: str | None = None
    language: str


class ParsedSource(BaseModel):
    symbols: list[Symbol] = Field(default_factory=list)
    imports: list[Import] = Field(default_factory=list)
    parse_error: str | None = None


class RepositoryFile(BaseModel):
    path: str
    language: str
    size: int
    content_hash: str
    modified_at: datetime
    lines: int | None = None
    parsed: ParsedSource | None = None


class Repository(BaseModel):
    root: str
    files: list[RepositoryFile] = Field(default_factory=list)

