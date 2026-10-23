"""Bounded, read-only repository tool registry for agent execution."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, ConfigDict

from .graph import build_code_graph
from .mcp_server import _index_path, _is_sensitive_path, _safe_repository_file, _validate_relative_path
from .orchestration import ContextBudget, ContextOrchestrator
from .providers import LLMProvider, ProviderError, get_provider
from .providers.config import ProviderSettings
from .retrieval import RetrievalEngine, RetrievalQuery
from .scanner import scan_repository


class ToolPermission(StrEnum):
    READ_ONLY = "read_only"


class ToolCall(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    name: str
    status: str
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolHistoryEntry(BaseModel):
    name: str
    arguments: dict[str, Any]
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=100)


class PathInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=500)


class PacketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str = Field(min_length=1, max_length=2000)
    max_files: int = Field(default=10, ge=1, le=100)
    max_tokens: int = Field(default=6000, ge=100, le=100000)


class ToolDefinition(BaseModel):
    name: str
    description: str
    permission: ToolPermission
    input_model: type[BaseModel]
    handler: Callable[..., Any]

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolExecutor:
    """Execute only registered read-only tools within one repository root."""

    def __init__(self, root: Path, *, provider: LLMProvider | None = None,
                 settings: ProviderSettings | None = None, max_calls: int = 8,
                 max_output_chars: int = 24000, timeout_seconds: float = 10.0) -> None:
        if max_calls < 1 or max_calls > 100: raise ValueError("max_calls must be between 1 and 100")
        if max_output_chars < 100 or max_output_chars > 200000: raise ValueError("max_output_chars is out of bounds")
        if timeout_seconds <= 0 or timeout_seconds > 120: raise ValueError("timeout_seconds is out of bounds")
        self.root = root.resolve()
        self.provider = provider
        self.settings = settings or ProviderSettings.from_env()
        self.max_calls, self.max_output_chars, self.timeout_seconds = max_calls, max_output_chars, timeout_seconds
        self.history: list[ToolHistoryEntry] = []
        self._definitions = self._make_definitions()

    def registry(self) -> dict[str, ToolDefinition]:
        return dict(self._definitions)

    def execute(self, call: ToolCall | dict[str, Any]) -> ToolResult:
        try:
            request = call if isinstance(call, ToolCall) else ToolCall.model_validate(call)
            definition = self._definitions.get(request.name)
            if definition is None: raise ValueError("unknown tool")
            if len(self.history) >= self.max_calls: raise ValueError("tool call limit exceeded")
            args = definition.input_model.model_validate(request.arguments)
            sanitized = self._sanitize_args(args.model_dump(mode="json"))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(definition.handler, **sanitized)
                output = future.result(timeout=self.timeout_seconds)
            bounded = self._bound_output(output)
            result = ToolResult(name=request.name, status="success", output=bounded, metadata={"permission": definition.permission.value})
            self.history.append(ToolHistoryEntry(name=request.name, arguments=sanitized, status="success", metadata=result.metadata))
            return result
        except FutureTimeout:
            result = ToolResult(name=request.name if 'request' in locals() else "unknown", status="failure", error="tool execution timed out")
        except (ValueError, TypeError) as exc:
            result = ToolResult(name=request.name if 'request' in locals() else "unknown", status="failure", error=str(exc))
        except (ProviderError, OSError, RuntimeError):
            result = ToolResult(name=request.name if 'request' in locals() else "unknown", status="failure", error="tool execution failed")
        except Exception:
            result = ToolResult(name=request.name if 'request' in locals() else "unknown", status="failure", error="tool execution failed")
        self.history.append(ToolHistoryEntry(name=result.name, arguments=self._sanitize_args(request.arguments) if 'request' in locals() else {}, status="failure"))
        return result

    def _make_definitions(self) -> dict[str, ToolDefinition]:
        return {
            "search_repository_context": ToolDefinition(name="search_repository_context", description="Search indexed repository context.", permission=ToolPermission.READ_ONLY, input_model=SearchInput, handler=self._search),
            "inspect_repository_file": ToolDefinition(name="inspect_repository_file", description="Inspect metadata, symbols, and imports for one repository file.", permission=ToolPermission.READ_ONLY, input_model=PathInput, handler=self._inspect),
            "get_file_dependencies": ToolDefinition(name="get_file_dependencies", description="Retrieve resolved and external dependencies for one repository file.", permission=ToolPermission.READ_ONLY, input_model=PathInput, handler=self._dependencies),
            "build_context_packet": ToolDefinition(name="build_context_packet", description="Build a bounded context packet for a task.", permission=ToolPermission.READ_ONLY, input_model=PacketInput, handler=self._packet),
        }

    def _safe_path(self, value: str) -> Path:
        relative = _validate_relative_path(value)
        if _is_sensitive_path(relative): raise ValueError("access to sensitive files is not allowed")
        return _safe_repository_file(self.root, relative)

    def _search(self, query: str, limit: int) -> dict[str, Any]:
        _index_path(self.root)
        results = RetrievalEngine(self.root / ".context-hub" / "index.db").search(RetrievalQuery(task=query, max_results=limit))
        return {"query": query, "results": [{"path": r.path, "symbol": r.symbol, "score": r.score, "signals": r.signals, "reasons": r.reasons} for r in results if not _is_sensitive_path(_validate_relative_path(r.path))]}

    def _inspect(self, path: str) -> dict[str, Any]:
        target = self._safe_path(path); relative = target.relative_to(self.root).as_posix(); repository = scan_repository(self.root)
        item = next((entry for entry in repository.files if entry.path == relative), None)
        if item is None: raise ValueError("repository file not found")
        parsed = item.parsed
        return {"path": item.path, "language": item.language, "size": item.size, "lines": item.lines, "symbols": [s.model_dump(mode="json") for s in (parsed.symbols if parsed else [])], "imports": [i.model_dump(mode="json") for i in (parsed.imports if parsed else [])], "parse_error": parsed.parse_error if parsed else None}

    def _dependencies(self, path: str) -> dict[str, Any]:
        target = self._safe_path(path); relative = target.relative_to(self.root).as_posix(); graph = build_code_graph(scan_repository(self.root)); node_id = f"file:{relative}"
        if graph.get_node(node_id) is None: raise ValueError("repository file not found")
        dependencies = []
        for dependency_id in sorted(graph.get_dependencies(node_id)):
            node = graph.get_node(dependency_id)
            if node: dependencies.append({"id": node.id, "name": node.name, "type": node.type.value, "path": node.path, "resolved": node.type.value != "external"})
        return {"path": relative, "dependencies": dependencies}

    def _packet(self, task: str, max_files: int, max_tokens: int) -> dict[str, Any]:
        provider = self.provider or get_provider(); _index_path(self.root)
        packet = ContextOrchestrator(self.root, provider, budget=ContextBudget(max_files=max_files, max_tokens=max_tokens), settings=self.settings).build(task)
        return json.loads(packet.model_dump_json())

    def _sanitize_args(self, args: dict[str, Any]) -> dict[str, Any]:
        return {key: ("<redacted>" if any(secret in key.lower() for secret in ("key", "secret", "password", "token")) else value) for key, value in args.items()}

    def _bound_output(self, output: Any) -> Any:
        text = json.dumps(output, ensure_ascii=True, default=str)
        if len(text) > self.max_output_chars: return {"truncated": True, "content": text[:self.max_output_chars]}
        return output
