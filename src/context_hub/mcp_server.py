"""Model Context Protocol server foundation for Context Hub."""

from pathlib import Path
from typing import Any

from .graph import build_code_graph
from .orchestration import ContextBudget, ContextOrchestrator
from .providers import ProviderError, get_provider
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

    @server.tool()
    def build_context_packet(task: str, max_files: int = 10, max_tokens: int = 6000) -> dict[str, object]:
        """Assemble bounded repository context for a coding task."""
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        if not isinstance(max_files, int) or isinstance(max_files, bool) or not 1 <= max_files <= 100:
            raise ValueError("max_files must be an integer between 1 and 100")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or not 100 <= max_tokens <= 100000:
            raise ValueError("max_tokens must be an integer between 100 and 100000")
        database = repository_root / ".context-hub" / "index.db"
        if not database.is_file():
            raise ValueError("Context Hub index is unavailable; run `ctx index` first")
        try:
            packet = ContextOrchestrator(
                repository_root,
                get_provider(),
                budget=ContextBudget(max_files=max_files, max_tokens=max_tokens),
            ).build(task)
        except ProviderError as exc:
            raise RuntimeError(f"Context provider unavailable: {exc}") from exc
        except (OSError, RuntimeError) as exc:
            raise RuntimeError(f"Context packet could not be built: {exc}") from exc
        except Exception as exc:
            raise RuntimeError("Context packet could not be built due to an unexpected internal error") from exc
        return {
            "task": packet.task,
            "files": [
                {
                    "path": item.path,
                    "symbol": item.symbol,
                    "source": item.source,
                    "score": item.score,
                    "reason": item.reason,
                    "distance": item.distance,
                    "estimated_tokens": item.estimated_tokens,
                    "metadata": item.metadata,
                    "content": item.content,
                }
                for item in packet.files
            ],
            "statistics": packet.statistics.model_dump(mode="json"),
            "constraints": packet.constraints,
            "selected_paths": [item.path for item in packet.files],
            "selected_symbols": sorted({item.symbol for item in packet.files if item.symbol}),
        }

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
