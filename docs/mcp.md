# Context Hub with MCP coding clients

Context Hub provides a local MCP server over stdio. Start it with the same
command used by the CLI:

```bash
uv run ctx mcp serve
```

Run that command from the repository you want Context Hub to inspect. Before
using `search_context` or `build_context_packet`, create the local index:

```bash
uv run ctx init
uv run ctx index
```

The server starts without a provider API key. `build_context_packet` uses the
configured provider, so set provider variables in the environment of the
client process. For example, configure the provider without placing a secret
in a tracked file:

```bash
# PowerShell
$env:CONTEXT_HUB_PROVIDER = "nebius"
$env:NEBIUS_API_KEY = "<set-this-outside-the-repository>"

# POSIX shell
export CONTEXT_HUB_PROVIDER=nebius
export NEBIUS_API_KEY="<set-this-outside-the-repository>"
```

Do not commit populated environment files or API keys. The provider is not
needed for `search_context`, `inspect_file`, or `get_dependencies`.

## VS Code MCP configuration

VS Code documents workspace `.vscode/mcp.json` with a top-level `servers`
object. Its stdio entries support `type`, `command`, `args`, and `cwd`.
Create `.vscode/mcp.json` in the repository, keeping the working directory
explicit:

```json
{
  "servers": {
    "contextHub": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "ctx", "mcp", "serve"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

The `${workspaceFolder}` value is a VS Code variable. Keep provider variables
in the environment that launches VS Code, or use the VS Code-specific secret
input/env mechanisms documented by VS Code rather than putting a key in this
file. This example has not been runtime-tested against a VS Code installation;
it follows the documented VS Code stdio schema.

## Claude Code project configuration

Claude Code documents project-scoped `.mcp.json` with a top-level `mcpServers`
object. From the repository root, add the server with:

```bash
claude mcp add --scope project contextHub -- uv run ctx mcp serve
```

The resulting shape is:

```json
{
  "mcpServers": {
    "contextHub": {
      "command": "uv",
      "args": ["run", "ctx", "mcp", "serve"]
    }
  }
}
```

Launch Claude Code from the repository root so the server inherits that
working directory. If the client supports an explicit working-directory field,
use the client’s documented field; do not copy VS Code’s `servers`/`cwd`
schema into Claude Code’s portable `.mcp.json` format. This configuration has
not been runtime-tested against Claude Code here.

Official references: [VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration),
[VS Code MCP setup](https://code.visualstudio.com/docs/agent-customization/mcp-servers),
and [Claude Code MCP configuration](https://docs.anthropic.com/en/docs/claude-code/mcp).

## Agent workflow

Once the client connects, ask the agent to confirm the server and discover its
tools. A practical repository workflow is:

1. Call `search_context` with a focused query and a small `limit`, such as
   `{"query":"provider configuration","limit":10}`.
2. Call `inspect_file` on a promising repository-relative path from the search
   results, such as `src/context_hub/providers/config.py`.
3. Call `get_dependencies` for that file, or pass a dotted module name such
   as `context_hub.providers.config`.
4. Call `build_context_packet` with the actual coding task and conservative
   budgets, such as
   `{"task":"add provider configuration tests","max_files":5,"max_tokens":3000}`.
5. Use the returned selected paths, symbols, evidence, and statistics to plan
   the change. The packet is bounded by the requested file/token budgets and
   is assembled by Context Hub’s existing orchestrator.

Tool behavior is read-only from the MCP client’s perspective. File paths are
repository-relative, and the server does not return API keys or unrelated
files. `search_context` and `build_context_packet` require `uv run ctx index`;
the inspection and dependency tools scan the repository directly.
