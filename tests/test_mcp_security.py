from pathlib import Path

import pytest

from context_hub.mcp_server import register_tools
from context_hub.orchestration.models import ContextStatistics



class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(function):
            self.tools[function.__name__] = function
            return function

        return decorator


def make_server(tmp_path: Path) -> FakeServer:
    (tmp_path / "auth.py").write_text("def login():\n    return True\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("from auth import login\n\ndef run():\n    return login()\n", encoding="utf-8")
    return register_tools(FakeServer(), tmp_path)


@pytest.mark.parametrize("path", ["../app.py", "..\\app.py", "C:\\outside.py", "\\\\server\\share\\file.py", "src/../app.py"])
def test_file_tools_reject_traversal_and_absolute_windows_paths(tmp_path: Path, path: str):
    server = make_server(tmp_path)
    for tool in ("inspect_file", "get_dependencies"):
        with pytest.raises(ValueError):
            server.tools[tool](path)


def test_sensitive_files_are_rejected_but_legitimate_source_names_remain_available(tmp_path: Path):
    (tmp_path / "credentials.json").write_text('{"token":"not-for-tools"}', encoding="utf-8")
    (tmp_path / "private.key").write_text("private", encoding="utf-8")
    (tmp_path / "secrets_manager.py").write_text("def load(): pass\n", encoding="utf-8")
    server = register_tools(FakeServer(), tmp_path)
    for path in ("credentials.json", "private.key", ".env"):
        with pytest.raises(ValueError, match="sensitive|not found"):
            server.tools["inspect_file"](path)
    assert server.tools["inspect_file"]("secrets_manager.py")["path"] == "secrets_manager.py"


def test_symlink_to_outside_repository_is_rejected(tmp_path: Path):
    outside = tmp_path.parent / "mcp-outside-secret.py"
    outside.write_text("token = 'outside'\n", encoding="utf-8")
    link = tmp_path / "linked.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")
    server = register_tools(FakeServer(), tmp_path)
    with pytest.raises(ValueError, match="not found|unavailable"):
        server.tools["inspect_file"]("linked.py")


def test_search_filters_unsafe_index_paths(tmp_path: Path, monkeypatch):
    server = make_server(tmp_path)
    index = tmp_path / ".context-hub"
    index.mkdir()
    (index / "index.db").write_bytes(b"placeholder")

    class Result:
        def __init__(self, path):
            self.path, self.symbol, self.score = path, None, .5
            self.signals, self.reasons, self.metadata, self.estimated_tokens = [], [], {}, 1

    class Engine:
        def __init__(self, path):
            pass

        def search(self, query):
            return [Result("../outside.py"), Result("app.py")]

    monkeypatch.setattr("context_hub.mcp_server.RetrievalEngine", Engine)
    assert [item["path"] for item in server.tools["search_context"]("app")["results"]] == ["app.py"]


def test_packet_serializer_redacts_secrets_and_recomputes_statistics(tmp_path: Path, monkeypatch):
    server = make_server(tmp_path)
    index = tmp_path / ".context-hub"
    index.mkdir()
    (index / "index.db").write_bytes(b"placeholder")

    class Item:
        path, symbol, source, score, reason, distance, estimated_tokens, metadata, content = (
            "app.py", None, "retrieval", .8, "match", 0, 99, {}, "NEBIUS_API_KEY='super-secret'\nAuthorization: Bearer abc123"
        )

    class Packet:
        task, files, constraints = "task", [Item()], []
        statistics = ContextStatistics(files_considered=1, files_selected=99, estimated_tokens=999)

    class Orchestrator:
        def __init__(self, *args, **kwargs):
            pass

        def build(self, task):
            return Packet()

    monkeypatch.setattr("context_hub.mcp_server.ContextOrchestrator", Orchestrator)
    monkeypatch.setattr("context_hub.mcp_server.get_provider", lambda: object())
    response = server.tools["build_context_packet"]("task")
    content = response["files"][0]["content"]
    assert "super-secret" not in content and "abc123" not in content
    assert response["statistics"]["files_selected"] == 1
    assert response["statistics"]["estimated_tokens"] == 99


def test_provider_error_is_safe_and_does_not_log_secret(tmp_path: Path, monkeypatch, caplog):
    server = make_server(tmp_path)
    index = tmp_path / ".context-hub"
    index.mkdir()
    (index / "index.db").write_bytes(b"placeholder")

    from context_hub.providers import ProviderError

    monkeypatch.setattr("context_hub.mcp_server.get_provider", lambda: (_ for _ in ()).throw(ProviderError("API_KEY=super-secret")))
    with pytest.raises(RuntimeError, match="Context provider unavailable") as error:
        server.tools["build_context_packet"]("task")
    assert "super-secret" not in str(error.value)
    assert "super-secret" not in caplog.text


def test_malformed_packet_response_is_safe_error(tmp_path: Path, monkeypatch):
    server = make_server(tmp_path)
    index = tmp_path / ".context-hub"
    index.mkdir()
    (index / "index.db").write_bytes(b"placeholder")

    class BrokenOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        def build(self, task):
            return object()

    monkeypatch.setattr("context_hub.mcp_server.ContextOrchestrator", BrokenOrchestrator)
    monkeypatch.setattr("context_hub.mcp_server.get_provider", lambda: object())
    with pytest.raises(RuntimeError, match="malformed data"):
        server.tools["build_context_packet"]("task")
