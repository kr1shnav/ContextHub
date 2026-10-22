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


def test_search_context_returns_structured_index_results(tmp_path, monkeypatch):
    server = make_server(tmp_path)
    index = tmp_path / ".context-hub"
    index.mkdir()
    (index / "index.db").write_bytes(b"placeholder")

    class Result:
        path, symbol, score, signals, reasons, metadata, estimated_tokens = "app.py", "run", .9, ["symbol_match"], ["match"], {"kind": "function"}, 12

    class Engine:
        def __init__(self, path):
            assert path == index / "index.db"

        def search(self, query):
            assert query.task == "run"
            assert query.max_results == 3
            return [Result()]

    monkeypatch.setattr("context_hub.mcp_server.RetrievalEngine", Engine)
    response = server.tools["search_context"]("run", 3)
    assert response["results"][0]["path"] == "app.py"


def test_inspect_file_returns_metadata_without_content(tmp_path):
    server = make_server(tmp_path)
    response = server.tools["inspect_file"]("app.py")
    assert response["path"] == "app.py"
    assert response["symbols"][0]["name"] == "run"
    assert response["imports"][0]["name"] == "auth"
    assert "content" not in response


def test_get_dependencies_resolves_file_and_external_module(tmp_path):
    server = make_server(tmp_path)
    response = server.tools["get_dependencies"]("app.py")
    dependencies = {item["name"]: item for item in response["dependencies"]}
    assert dependencies["auth.py"]["resolved"] is True


@pytest.mark.parametrize("tool, argument", [("search_context", ""), ("inspect_file", "missing.py"), ("get_dependencies", "missing.py")])
def test_tools_reject_invalid_input(tmp_path, tool, argument):
    server = make_server(tmp_path)
    with pytest.raises(ValueError):
        server.tools[tool](argument)


def test_search_context_reports_missing_index(tmp_path):
    server = make_server(tmp_path)
    with pytest.raises(ValueError, match="index is unavailable"):
        server.tools["search_context"]("run")


def test_build_context_packet_returns_bounded_structured_evidence(tmp_path, monkeypatch):
    server = make_server(tmp_path)
    index = tmp_path / ".context-hub"
    index.mkdir()
    (index / "index.db").write_bytes(b"placeholder")
    calls = {}

    class Item:
        path, symbol, source, score, reason, distance, estimated_tokens, metadata, content = (
            "app.py", "run", "retrieval", .8, "task match", 0, 12, {"kind": "function"}, "def run(): pass\n"
        )

    class Packet:
        task = "explain run"
        files = [Item()]
        constraints = []
        statistics = ContextStatistics(files_considered=2, files_selected=1, estimated_tokens=12)

    class FakeOrchestrator:
        def __init__(self, root, provider, *, budget):
            calls.update(root=root, provider=provider, budget=budget)

        def build(self, task):
            assert task == "explain run"
            return Packet()

    monkeypatch.setattr("context_hub.mcp_server.ContextOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("context_hub.mcp_server.get_provider", lambda: "mock-provider")
    response = server.tools["build_context_packet"]("explain run", max_files=2, max_tokens=300)
    assert response["selected_paths"] == ["app.py"]
    assert response["selected_symbols"] == ["run"]
    assert response["statistics"]["estimated_tokens"] == 12
    assert calls["budget"].max_files == 2
    assert calls["budget"].max_tokens == 300


@pytest.mark.parametrize(
    ("argument", "value"),
    [("task", ""), ("max_files", 0), ("max_files", 101), ("max_tokens", 99), ("max_tokens", 100001)],
)
def test_build_context_packet_validates_arguments(tmp_path, argument, value):
    server = make_server(tmp_path)
    kwargs = {"task": "explain run", argument: value}
    with pytest.raises(ValueError):
        server.tools["build_context_packet"](**kwargs)


def test_build_context_packet_reports_provider_failure(tmp_path, monkeypatch):
    server = make_server(tmp_path)
    index = tmp_path / ".context-hub"
    index.mkdir()
    (index / "index.db").write_bytes(b"placeholder")

    def fail():
        from context_hub.providers import ProviderError
        raise ProviderError("provider is not configured")

    monkeypatch.setattr("context_hub.mcp_server.get_provider", fail)
    with pytest.raises(RuntimeError, match="Context provider unavailable"):
        server.tools["build_context_packet"]("explain run")


def test_build_context_packet_reports_orchestration_failure(tmp_path, monkeypatch):
    server = make_server(tmp_path)
    index = tmp_path / ".context-hub"
    index.mkdir()
    (index / "index.db").write_bytes(b"placeholder")

    class BrokenOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        def build(self, task):
            raise RuntimeError("index read failed")

    monkeypatch.setattr("context_hub.mcp_server.ContextOrchestrator", BrokenOrchestrator)
    monkeypatch.setattr("context_hub.mcp_server.get_provider", lambda: "mock-provider")
    with pytest.raises(RuntimeError, match="Context packet could not be built"):
        server.tools["build_context_packet"]("explain run")
