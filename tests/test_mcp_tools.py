from pathlib import Path

import pytest

from context_hub.mcp_server import register_tools


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
