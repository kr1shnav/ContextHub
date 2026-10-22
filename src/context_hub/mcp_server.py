"""Model Context Protocol server foundation for Context Hub."""

from typing import Any


def create_server() -> Any:
    """Create the MCP server without starting a transport."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The MCP server requires the 'mcp' package. Install project dependencies with `uv sync`."
        ) from exc
    return FastMCP("Context Hub")


def serve_stdio() -> None:
    """Run the MCP server over stdio for local coding-agent clients."""
    create_server().run(transport="stdio")
