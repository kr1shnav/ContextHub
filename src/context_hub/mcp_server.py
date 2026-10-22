"""Model Context Protocol server foundation for Context Hub."""

from pathlib import Path
from typing import Any

from .graph import build_code_graph
from .retrieval import RetrievalEngine, RetrievalQuery
from .scanner import scan_repository


def _rooted_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty repository-relative path")
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError(f"repository file not found: {value}")
    return candidate


def _find_repository_file(root: Path, value: str, repository) -> str:
    normalized = value.strip().replace("\\", "/")
    paths = {item.path for item in repository.files}
    candidates = [normalized]
    if "." in normalized and "/" not in normalized:
        module_path = normalized.replace(".", "/")
        candidates.extend((module_path + ".py", module_path + "/__init__.py"))
    for candidate in candidates:
        if candidate in paths:
            return candidate
    _rooted_path(root, normalized)
    raise ValueError(f"repository file is unavailable to Context Hub: {value}")


def register_tools(server: Any, root: Path | None = None) -> Any:
    """Register Phase 8.2 tools on an MCP server instance."""
    repository_root = (root or Path.cwd()).resolve()

    @server.tool()
    def search_context(query: str, limit: int = 20) -> dict[str, object]:
        """Search indexed repository context without returning source contents."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        database = repository_root / ".context-hub" / "index.db"
        if not database.is_file():
            raise ValueError("Context Hub index is unavailable; run `ctx index` first")
        try:
            results = RetrievalEngine(database).search(RetrievalQuery(task=query, max_results=limit))
        except (OSError, RuntimeError) as exc:
            raise RuntimeError(f"Context search failed: {exc}") from exc
        return {
            "query": query,
            "results": [
                {
                    "path": result.path,
                    "symbol": result.symbol,
                    "score": result.score,
                    "signals": result.signals,
                    "reasons": result.reasons,
                    "metadata": result.metadata,
                    "estimated_tokens": result.estimated_tokens,
                }
                for result in results
            ],
        }

    @server.tool()
    def inspect_file(path: str) -> dict[str, object]:
        """Inspect repository file metadata, symbols, and imports."""
        repository = scan_repository(repository_root)
        relative = _find_repository_file(repository_root, path, repository)
        item = next(item for item in repository.files if item.path == relative)
        parsed = item.parsed
        return {
            "path": item.path,
            "language": item.language,
            "size": item.size,
            "lines": item.lines,
            "content_hash": item.content_hash,
            "symbols": [symbol.model_dump(mode="json") for symbol in (parsed.symbols if parsed else [])],
            "imports": [imported.model_dump(mode="json") for imported in (parsed.imports if parsed else [])],
            "parse_error": parsed.parse_error if parsed else None,
        }

    @server.tool()
    def get_dependencies(path: str) -> dict[str, object]:
        """Return resolved and unresolved dependencies for a repository file/module."""
        repository = scan_repository(repository_root)
        relative = _find_repository_file(repository_root, path, repository)
        graph = build_code_graph(repository)
        node_id = f"file:{relative}"
        dependencies = []
        for dependency_id in sorted(graph.get_dependencies(node_id)):
            node = graph.get_node(dependency_id)
            if node is None:
                continue
            dependencies.append({
                "id": node.id,
                "name": node.name,
                "type": node.type.value,
                "path": node.path,
                "resolved": node.type.value != "external",
            })
        return {"path": relative, "dependencies": dependencies}

    return server


def create_server() -> Any:
    """Create the MCP server without starting a transport."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The MCP server requires the 'mcp' package. Install project dependencies with `uv sync`."
        ) from exc
    return register_tools(FastMCP("Context Hub"))


def serve_stdio() -> None:
    """Run the MCP server over stdio for local coding-agent clients."""
    create_server().run(transport="stdio")
