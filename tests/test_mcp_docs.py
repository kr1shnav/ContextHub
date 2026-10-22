from pathlib import Path


def test_mcp_documentation_matches_server_command_and_tools():
    documentation = (Path(__file__).parents[1] / "docs" / "mcp.md").read_text(encoding="utf-8")
    assert "uv run ctx mcp serve" in documentation
    for tool in ("search_context", "inspect_file", "get_dependencies", "build_context_packet"):
        assert tool in documentation
    assert '"servers"' in documentation
    assert '"mcpServers"' in documentation
    assert '"cwd": "${workspaceFolder}"' in documentation


def test_mcp_documentation_contains_no_real_secret_placeholder_values():
    documentation = (Path(__file__).parents[1] / "docs" / "mcp.md").read_text(encoding="utf-8")
    assert "sk-" not in documentation
    assert "Bearer " not in documentation
    assert "<set-this-outside-the-repository>" in documentation
