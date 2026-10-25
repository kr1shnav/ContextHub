# Context Hub

Context Hub prepares bounded, inspectable repository context for developer and
coding-agent workflows. It scans a repository, stores parsed file/symbol/import
metadata in SQLite, retrieves relevant evidence, and assembles a context packet
for a task. The goal is to reduce manual context gathering while keeping the
selected evidence and budgets visible.

It is for developers, reviewers, and coding-agent integrations that need local
repository search and evidence-backed planning. It does not apply patches,
execute arbitrary agent commands, guarantee semantic correctness, or provide
exact model-token counts.

## Implemented capabilities

- Deterministic repository scanning and Python/tree-sitter parsing where supported.
- Transactional SQLite indexing with incremental new/modified/deleted tracking.
- Lexical retrieval with symbol, path/import, and bounded dependency signals.
- In-memory code-graph construction and dependency inspection.
- Bounded `ContextPacket` assembly with file, token, character, and graph budgets.
- Local MCP server over stdio with four read-only repository tools.
- Nebius/NVIDIA-compatible provider integrations and a deterministic mock provider.
- Read-only agent planning, controlled read-only tools, reviewable unified-diff
  proposals, and explicit validation.
- Versioned retrieval, packet, performance, agent, and unified evaluation tools.

## Architecture

```text
repository -> scan_repository -> RepositoryFile / ParsedSource
                    |                    |
                    +-> index_repository -> .context-hub/index.db
                                               |
                         RetrievalEngine.search
                                               |
                         ContextOrchestrator -> ContextPacket
                              |                    |
                         CLI / MCP / AgentHarness workflows
```

Detailed guides:

- [Architecture and data flow](docs/architecture.md)
- [CLI reference](docs/cli.md)
- [MCP setup and tools](docs/mcp.md)
- [Provider configuration](docs/providers.md)
- [Evaluation and benchmarks](docs/evaluation.md)
- [Continuous integration](docs/ci.md)
- [Contributing](docs/contributing.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Offline end-to-end demo](docs/demo.md)
- [Release preparation](docs/release.md)

## Installation and quickstart

Requirements are Python 3.12+ and [uv](https://docs.astral.sh/uv/). From a
checkout:

```bash
uv sync
uv run ctx init .
uv run ctx index .
uv run ctx search "Explain how context packets are assembled" --limit 5
uv run ctx inspect src/context_hub/orchestration/orchestrator.py
uv run ctx pack "Explain how ContextOrchestrator builds a context packet" --no-llm
```

The `ctx` console script is registered as `context_hub.cli:app`. `ctx init`
creates `.context-hub/metadata.json`; `ctx index` creates or updates the local
SQLite index. The `--no-llm` packet path uses `MockProvider` and needs no API
key or network. Run `uv run ctx --help` or see the [CLI reference](docs/cli.md)
for the complete registered command surface.

For tests, use the CI-pinned tool without adding it to runtime dependencies:

```bash
uv run --locked --with pytest==8.3.5 pytest
```

## Provider configuration

Provider-backed commands read environment variables through
`ProviderSettings.from_env()`. The default provider is `nebius`; supported
providers are `nebius` and `nvidia`. Set a provider-specific key only in the
launching environment:

```bash
# POSIX
export CONTEXT_HUB_PROVIDER=nebius
export NEBIUS_API_KEY="<set-outside-the-repository>"

# PowerShell
$env:CONTEXT_HUB_PROVIDER = "nebius"
$env:NEBIUS_API_KEY = "<set-outside-the-repository>"
```

The default models/endpoints and override variables are documented in
[Provider configuration](docs/providers.md). `uv run ctx provider status`
reports only whether a key is configured, not its value. `ctx analyze`,
`ctx agent-plan`, ordinary `ctx pack`, proposal generation, and MCP
`build_context_packet` may require credentials; indexing, search, inspect,
dependencies, validation, and `--no-llm` packet flows are local/offline.

### NVIDIA on Windows

In Command Prompt, configure the NVIDIA provider and an exact model ID enabled
for the API account:

```bat
set CONTEXT_HUB_PROVIDER=nvidia
set NVIDIA_API_KEY=<set-outside-the-repository>
set NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
set NVIDIA_MODEL=<exact-enabled-model-id>
uv run ctx provider status
uv run ctx analyze "Explain the project architecture, identify the main modules, and trace how data flows between them."
```

`NVIDIA_MODEL` is intentionally configurable; a model listed in a public
catalog is not necessarily enabled for every account. Use NVIDIA's account/model
catalog or dashboard to identify an enabled hosted model, then set its exact ID.
`ctx provider status` is local-only and never prints the key.

NVIDIA errors are reported without falling back to Nebius: `401` means the key
is invalid, `403` means access is denied, `404` may indicate an unavailable
model, account entitlement, or endpoint/model mismatch, `429` means rate or
quota limiting, and `5xx` indicates an upstream NVIDIA failure. Check
`NVIDIA_BASE_URL` and `NVIDIA_MODEL` for `404`; check account access for
account-scoped 404s.

## MCP and evaluation

Start the local MCP stdio server from the repository being analyzed:

```bash
uv run ctx init .
uv run ctx index .
uv run ctx mcp serve
```

MCP client configuration is client-specific; the supported server transport is
stdio. See [MCP setup](docs/mcp.md) for tool names and safe path behavior.

Evaluation commands are available under `ctx eval`: `retrieval`, `packets`,
`performance`, `agent`, and `all`. They consume versioned local datasets and
produce terminal summaries or JSON reports. See [Evaluation](docs/evaluation.md)
for metrics, baselines, gates, and limitations.

## Limitations

Retrieval and packet metrics measure the current implementation, not downstream
answer quality. Performance results are environment-dependent; packet token
counts are estimates. Agent plans, patches, and semantic correctness still need
human review. Future work is not presented here as shipped functionality.
