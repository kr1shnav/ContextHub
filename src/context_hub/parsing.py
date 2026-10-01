"""Source parser abstraction and lightweight deterministic parsers."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Protocol

from .languages import detect_language
from .models import Import, ParsedSource, Symbol, SymbolKind

try:
    import tree_sitter  # type: ignore[import-not-found]
except ImportError:  # Optional until language grammar packages are selected.
    tree_sitter = None


class SourceParser(Protocol):
    def parse(self, source: str, *, file: str, language: str) -> ParsedSource: ...


def tree_sitter_available() -> bool:
    """Report whether the Tree-sitter runtime is installed.

    Grammar packages are intentionally selected per language in a later phase;
    the deterministic parsers below keep Phase 2 usable without network access.
    """
    return tree_sitter is not None


class RegexParser:
    """Best-effort parser for languages without a bundled grammar."""
    patterns = {
        "JavaScript": [(SymbolKind.CLASS, r"\bclass\s+(\w+)"), (SymbolKind.FUNCTION, r"\bfunction\s+(\w+)")],
        "TypeScript": [(SymbolKind.CLASS, r"\bclass\s+(\w+)"), (SymbolKind.FUNCTION, r"\bfunction\s+(\w+)")],
        "Java": [(SymbolKind.CLASS, r"\bclass\s+(\w+)"), (SymbolKind.METHOD, r"(?:public|private|protected)?\s*\w+[<>,\[\] \w]*\s+(\w+)\s*\(")],
        "Go": [(SymbolKind.FUNCTION, r"\bfunc\s+(?:\([^)]*\)\s*)?(\w+)")],
        "Rust": [(SymbolKind.FUNCTION, r"\bfn\s+(\w+)")],
        "C": [(SymbolKind.FUNCTION, r"\b\w[\w *]+\s+(\w+)\s*\([^;]*\)\s*\{")],
        "C++": [(SymbolKind.CLASS, r"\bclass\s+(\w+)"), (SymbolKind.FUNCTION, r"\b\w[\w:&*<> ]+\s+(\w+)\s*\([^;]*\)\s*\{")],
    }

    def parse(self, source: str, *, file: str, language: str) -> ParsedSource:
        symbols: list[Symbol] = []
        for kind, pattern in self.patterns.get(language, []):
            for match in re.finditer(pattern, source):
                line = source.count("\n", 0, match.start()) + 1
                symbols.append(Symbol(name=match.group(1), kind=kind, file=file,
                                      start_line=line, end_line=line, language=language))
        return ParsedSource(symbols=symbols, imports=self._imports(source, language))

    @staticmethod
    def _imports(source: str, language: str) -> list[Import]:
        patterns = {
            "JavaScript": r"(?:import.*?from\s+|require\(\s*)['\"]([^'\"]+)",
            "TypeScript": r"(?:import.*?from\s+|require\(\s*)['\"]([^'\"]+)",
            "Go": r'"([^"\n]+)"', "Rust": r"use\s+([\w:]+)",
            "Java": r"import\s+([\w.]+)", "C": r'#include\s*[<\"]([^>\"]+)', "C++": r'#include\s*[<\"]([^>\"]+)',
        }
        pattern = patterns.get(language)
        if not pattern:
            return []
        return [Import(name=m.group(1), line=source.count("\n", 0, m.start()) + 1)
                for m in re.finditer(pattern, source)]


class PythonParser:
    def parse(self, source: str, *, file: str, language: str = "Python") -> ParsedSource:
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, TypeError) as exc:
            return ParsedSource(parse_error=str(exc))
        symbols: list[Symbol] = []
        imports: list[Import] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = SymbolKind.CLASS if isinstance(node, ast.ClassDef) else SymbolKind.FUNCTION
                parent = None
                for parent_node in ast.walk(tree):
                    if isinstance(parent_node, ast.ClassDef) and node in parent_node.body:
                        parent = parent_node.name
                        if kind == SymbolKind.FUNCTION:
                            kind = SymbolKind.METHOD
                        break
                symbols.append(Symbol(name=node.name, kind=kind, file=file,
                                      start_line=node.lineno, end_line=getattr(node, "end_lineno", node.lineno),
                                      parent=parent, language=language))
            elif isinstance(node, ast.Import):
                imports.extend(Import(name=a.name, line=node.lineno) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(Import(name=node.module or "", source=node.level and "." * node.level or None, line=node.lineno))
        return ParsedSource(symbols=symbols, imports=imports)


def parser_for(language: str) -> SourceParser:
    return PythonParser() if language == "Python" else RegexParser()

