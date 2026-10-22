"""Model Context Protocol server and safe repository tools."""

import logging
import re
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any

from .graph import build_code_graph
from .orchestration import ContextBudget, ContextOrchestrator
from .providers import ProviderError, get_provider
from .retrieval import RetrievalEngine, RetrievalQuery
from .scanner import scan_repository

LOGGER = logging.getLogger(__name__)
_SECRET_ASSIGNMENT = re.compile(
    r"(?im)(\b(?:[a-z0-9]+[_-])?(?:api[_-]?key|access[_-]?key|secret|password|token)\b\s*[:=]\s*)([\"']?)[^\s\"']+"
)
_BEARER = re.compile(r"(?i)(\bBearer\s+)[^\s\"']+")
_SENSITIVE_SUFFIXES = {".key", ".pem", ".p12"}
_SENSITIVE_NAMES = {"credentials", "secrets"}


def _safe_failure(tool: str, exc: BaseException) -> None:
    """Log only diagnostic type information; never log exception contents."""
    LOGGER.error("MCP tool %s failed with %s", tool, type(exc).__name__)


def _validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty repository-relative path")
    normalized = value.strip().replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    if "\0" in normalized or normalized.startswith("/") or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("path must be repository-relative and cannot be absolute")
    if any(part == ".." for part in normalized.split("/")):
        raise ValueError("path traversal is not allowed")
    if any(part in {"", "."} for part in normalized.split("/")):
        raise ValueError("path contains an invalid empty or current-directory component")
    return normalized


def _is_sensitive_path(relative: str) -> bool:
    path = PureWindowsPath(relative.replace("/", "\\"))
    for part in path.parts:
        name = part.lower()
        if name.startswith(".env") or name in _SENSITIVE_NAMES:
            return True
        if Path(name).suffix.lower() in _SENSITIVE_SUFFIXES:
            return True
        if name.startswith("credentials.") or name.startswith("secrets."):
            return True
    return False


def _safe_repository_file(root: Path, value: str) -> Path:
    normalized = _validate_relative_path(value)
    if _is_sensitive_path(normalized):
        raise ValueError("access to sensitive configuration files is not allowed")
    candidate = (root / normalized).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError(f"repository file not found: {value}")
    return candidate


def _redact_content(content: str | None) -> str | None:
    if content is None:
        return None
    redacted = _SECRET_ASSIGNMENT.sub(r"\1\2<redacted>", content)
    return _BEARER.sub(r"\1<redacted>", redacted)


def _index_path(root: Path) -> Path:
    index = root / ".context-hub" / "index.db"
    resolved = index.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("Context Hub index is unavailable; run `ctx index` first")
    return resolved


def _serialize_packet(packet: Any, root: Path) -> dict[str, object]:
    """Serialize only safe, returned evidence and recompute returned statistics."""
    safe_files = []
    for item in packet.files:
        try:
            relative = _validate_relative_path(item.path)
            resolved = _safe_repository_file(root, relative)
        except ValueError:
            continue
        if not resolved.is_relative_to(root):
            continue
        safe_files.append({
            "path": relative,
            "symbol": item.symbol,
            "source": item.source,
            "score": item.score,
            "reason": item.reason,
            "distance": item.distance,
            "estimated_tokens": max(0, item.estimated_tokens),
            "metadata": item.metadata,
            "content": _redact_content(item.content),
        })
    returned_paths = [item["path"] for item in safe_files]
    returned_symbols = sorted({item["symbol"] for item in safe_files if item["symbol"]})
    returned_stats = packet.statistics.model_dump(mode="json")
    returned_stats["files_selected"] = len(returned_paths)
    returned_stats["estimated_tokens"] = sum(item["estimated_tokens"] for item in safe_files)
    returned_stats["graph_nodes_selected"] = sum(item["source"] == "graph" for item in safe_files)
    return {
        "task": packet.task,
        "files": safe_files,
        "statistics": returned_stats,
        "constraints": packet.constraints,
        "selected_paths": returned_paths,
        "selected_symbols": returned_symbols,
    }


def _rooted_path(root: Path, value: str) -> Path:
    return _safe_repository_file(root, value)


def _find_repository_file(root: Path, value: str, repository) -> str:
    normalized = _validate_relative_path(value)
    paths = {item.path for item in repository.files}
    candidates = [normalized]
    if "." in normalized and "/" not in normalized and not _is_sensitive_path(normalized):
        module_path = normalized.replace(".", "/")
        candidates.extend((module_path + ".py", module_path + "/__init__.py"))
    for candidate in candidates:
        if candidate in paths and not _is_sensitive_path(candidate):
            _safe_repository_file(root, candidate)
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
        database = _index_path(repository_root)
        try:
            results = RetrievalEngine(database).search(RetrievalQuery(task=query, max_results=limit))
        except Exception as exc:
            _safe_failure("search_context", exc)
            raise RuntimeError("Context search failed; check the local index and run `ctx index` if needed") from exc
        safe_results = []
        for result in results:
            try:
                relative = _validate_relative_path(result.path)
                if _is_sensitive_path(relative) or not (repository_root / relative).resolve().is_relative_to(repository_root):
                    continue
            except ValueError:
                continue
            safe_results.append({
                "path": relative,
                "symbol": result.symbol,
                "score": result.score,
                "signals": result.signals,
                "reasons": result.reasons,
                "metadata": result.metadata,
                "estimated_tokens": result.estimated_tokens,
            })
        return {
            "query": query,
            "results": safe_results,
        }

    @server.tool()
    def inspect_file(path: str) -> dict[str, object]:
        """Inspect repository file metadata, symbols, and imports."""
        try:
            repository = scan_repository(repository_root)
            relative = _find_repository_file(repository_root, path, repository)
            item = next(item for item in repository.files if item.path == relative)
        except ValueError:
            raise
        except Exception as exc:
            _safe_failure("inspect_file", exc)
            raise RuntimeError("File inspection failed; check the repository path and scanner state") from exc
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
        try:
            repository = scan_repository(repository_root)
            relative = _find_repository_file(repository_root, path, repository)
            graph = build_code_graph(repository)
        except ValueError:
            raise
        except Exception as exc:
            _safe_failure("get_dependencies", exc)
            raise RuntimeError("Dependency analysis failed; check the repository path and scanner state") from exc
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
        database = _index_path(repository_root)
        try:
            packet = ContextOrchestrator(
                repository_root,
                get_provider(),
                budget=ContextBudget(max_files=max_files, max_tokens=max_tokens),
            ).build(task)
        except ProviderError as exc:
            _safe_failure("build_context_packet", exc)
            raise RuntimeError("Context provider unavailable; configure the provider in the launching environment") from exc
        except (OSError, RuntimeError) as exc:
            _safe_failure("build_context_packet", exc)
            raise RuntimeError("Context packet could not be built; check the index and repository state") from exc
        except Exception as exc:
            _safe_failure("build_context_packet", exc)
            raise RuntimeError("Context packet could not be built due to an unexpected internal error") from exc
        try:
            return _serialize_packet(packet, repository_root)
        except Exception as exc:
            _safe_failure("build_context_packet", exc)
            raise RuntimeError("Context packet returned malformed data") from exc

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
