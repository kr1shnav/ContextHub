"""In-memory code graph built from repository-intelligence models."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import StrEnum

from .models import Repository


class NodeType(StrEnum):
    REPOSITORY = "repository"
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    SYMBOL = "symbol"
    EXTERNAL = "external"


class RelationshipType(StrEnum):
    IMPORTS = "imports"
    DEFINES = "defines"
    CONTAINS = "contains"
    CALLS = "calls"
    REFERENCES = "references"
    DEPENDS_ON = "depends_on"
    DEFINED_IN = "defined_in"


@dataclass(frozen=True)
class GraphNode:
    id: str
    type: NodeType
    name: str
    path: str | None = None
    symbol_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str
    metadata: dict[str, object] = field(default_factory=dict)
    confidence: float = 1.0


class CodeGraph:
    def __init__(self) -> None:
        self.nodes: set[str] = set()
        self.node_data: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._outgoing: dict[str, set[str]] = defaultdict(set)

    def add_node(self, node: GraphNode) -> None:
        self.nodes.add(node.id)
        self.node_data.setdefault(node.id, node)

    def add_edge(self, source: str, target: str, kind: str, *, metadata: dict[str, object] | None = None,
                 confidence: float = 1.0) -> None:
        self.nodes.update((source, target))
        edge = GraphEdge(source, target, kind, metadata or {}, confidence)
        if edge not in self.edges:
            self.edges.append(edge)
            self._outgoing[source].add(target)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.node_data.get(node_id)

    def get_edges(self) -> list[GraphEdge]:
        return list(self.edges)

    def get_dependencies(self, node_id: str) -> set[str]:
        return {e.target for e in self.edges if e.source == node_id and e.kind == RelationshipType.DEPENDS_ON}

    def stats(self) -> dict[str, int]:
        return {
            "repositories": sum(n.type == NodeType.REPOSITORY for n in self.node_data.values()),
            "files": sum(n.type == NodeType.FILE for n in self.node_data.values()),
            "modules": sum(n.type == NodeType.MODULE for n in self.node_data.values()),
            "symbols": sum(n.type in {NodeType.CLASS, NodeType.FUNCTION, NodeType.METHOD, NodeType.SYMBOL} for n in self.node_data.values()),
            "imports": sum(e.kind == RelationshipType.IMPORTS for e in self.edges),
            "dependencies": sum(e.kind == RelationshipType.DEPENDS_ON for e in self.edges),
            "edges": len(self.edges),
            "unresolved_imports": sum(e.kind == RelationshipType.IMPORTS and not e.metadata.get("resolved", True) for e in self.edges),
        }

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
    graph.add_node(GraphNode(f"repository:{repository.root}", NodeType.REPOSITORY, repository.root, path=repository.root))
    files = {item.path: item for item in repository.files}
    for item in repository.files:
        file_id = f"file:{item.path}"
        graph.add_node(GraphNode(file_id, NodeType.FILE, item.path, path=item.path,
                                 metadata={"language": item.language, "size": item.size, "content_hash": item.content_hash}))
        graph.add_edge(f"repository:{repository.root}", file_id, RelationshipType.CONTAINS)
        if not item.parsed:
            continue
        for symbol in item.parsed.symbols:
            symbol_id = f"{item.path}:{symbol.name}"
            symbol_id = f"symbol:{item.path}:{symbol.name}:{symbol.start_line}"
            kind = NodeType(symbol.kind.value) if symbol.kind.value in NodeType._value2member_map_ else NodeType.SYMBOL
            graph.add_node(GraphNode(symbol_id, kind, symbol.name, path=item.path, symbol_id=symbol_id,
                                     metadata=symbol.model_dump(exclude={"file", "name"})))
            graph.add_edge(file_id, symbol_id, RelationshipType.DEFINES)
            if symbol.parent:
                parent_id = next((n.id for n in graph.node_data.values() if n.path == item.path and n.name == symbol.parent), file_id)
                graph.add_edge(parent_id, symbol_id, RelationshipType.DEFINES)
        for imported in item.parsed.imports:
            target = _resolve_import(item.path, imported.name, files)
            target_id = f"file:{target}" if target else f"external:{imported.name}"
            if not target:
                graph.add_node(GraphNode(target_id, NodeType.EXTERNAL, imported.name, metadata={"module": imported.name}))
            graph.add_edge(file_id, target_id, RelationshipType.IMPORTS,
                           metadata={"resolved": target is not None, "import": imported.name}, confidence=1.0)
            graph.add_edge(file_id, target_id, RelationshipType.DEPENDS_ON,
                           metadata={"resolved": target is not None}, confidence=1.0)
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

