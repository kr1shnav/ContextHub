"""In-memory code graph built from repository-intelligence models."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from .models import Repository


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str


class CodeGraph:
    def __init__(self) -> None:
        self.nodes: set[str] = set()
        self.edges: list[GraphEdge] = []
        self._outgoing: dict[str, set[str]] = defaultdict(set)

    def add_edge(self, source: str, target: str, kind: str) -> None:
        self.nodes.update((source, target))
        edge = GraphEdge(source, target, kind)
        if edge not in self.edges:
            self.edges.append(edge)
            self._outgoing[source].add(target)

    def neighbors(self, node: str, *, max_depth: int = 1) -> set[str]:
        seen = {node}
        queue = deque([(node, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for target in self._outgoing.get(current, ()):
                if target not in seen:
                    seen.add(target)
                    queue.append((target, depth + 1))
        return seen - {node}

    def dependents(self, node: str) -> set[str]:
        return {edge.source for edge in self.edges if edge.target == node}


def build_code_graph(repository: Repository) -> CodeGraph:
    graph = CodeGraph()
    files = {item.path: item for item in repository.files}
    for item in repository.files:
        graph.nodes.add(item.path)
        if not item.parsed:
            continue
        for symbol in item.parsed.symbols:
            symbol_id = f"{item.path}:{symbol.name}"
            graph.add_edge(item.path, symbol_id, "contains")
            if symbol.parent:
                graph.add_edge(f"{item.path}:{symbol.parent}", symbol_id, "contains")
        for imported in item.parsed.imports:
            target = _resolve_import(item.path, imported.name, files)
            if target:
                graph.add_edge(item.path, target, "imports")
    return graph


def _resolve_import(source: str, imported: str, files: dict[str, object]) -> str | None:
    normalized = imported.replace(".", "/").lstrip("./")
    candidates = [normalized, normalized + ".py", normalized + ".js", normalized + ".ts", normalized + "/__init__.py"]
    source_dir = source.rsplit("/", 1)[0] if "/" in source else ""
    for candidate in candidates:
        if candidate in files:
            return candidate
        relative = f"{source_dir}/{candidate}" if source_dir else candidate
        if relative in files:
            return relative
    return None

