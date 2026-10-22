from typer.testing import CliRunner

from context_hub import cli
from context_hub.mcp_server import create_server


def test_mcp_command_is_registered():
    result = CliRunner().invoke(cli.app, ["mcp", "serve", "--help"])
    assert result.exit_code == 0
    assert "Start the Context Hub MCP server over stdio" in result.stdout


def test_create_server_initializes_fastmcp(monkeypatch):
    class FakeFastMCP:
        def __init__(self, name):
            self.name = name

        def tool(self):
            return lambda function: function

    monkeypatch.setattr("mcp.server.fastmcp.FastMCP", FakeFastMCP)
    assert create_server().name == "Context Hub"


def test_stdio_startup_uses_stdio_transport(monkeypatch):
    calls = []

    class FakeServer:
        def run(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("context_hub.mcp_server.create_server", lambda: FakeServer())
    from context_hub.mcp_server import serve_stdio

    serve_stdio()
    assert calls == [{"transport": "stdio"}]


def test_startup_error_is_reported_without_traceback(monkeypatch):
    monkeypatch.setattr(cli, "serve_stdio", lambda: (_ for _ in ()).throw(RuntimeError("SDK unavailable")))
    result = CliRunner().invoke(cli.app, ["mcp", "serve"])
    assert result.exit_code == 1
    assert "SDK unavailable" in result.stderr
    assert "Traceback" not in result.stderr


def test_mcp_startup_does_not_require_provider(monkeypatch):
    monkeypatch.setattr(cli, "serve_stdio", lambda: None)
    monkeypatch.setattr(cli, "get_provider", lambda: (_ for _ in ()).throw(AssertionError("provider used")))
    assert CliRunner().invoke(cli.app, ["mcp", "serve"]).exit_code == 0
