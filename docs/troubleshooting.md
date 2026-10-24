# Troubleshooting

## Installation and tests

- If `uv sync` cannot resolve Python, install Python 3.12+ and ensure uv can
  discover it. `requires-python` is `>=3.12`.
- If tests are unavailable after a runtime-only install, use
  `uv run --locked --with pytest==8.3.5 pytest`.
- If `uv` reports a locked-resolution or cache error, check `uv.lock`, network
  access to package indexes, and local cache permissions. Do not reuse a stale
  virtual environment from another machine.
- If `uv build` fails, inspect the Hatchling build error and confirm the build
  environment can obtain the build dependency.

## Indexing and retrieval

- `ctx search` and MCP `search_context` require `.context-hub/index.db`. Run
  `ctx init .` and `ctx index .` from the repository being inspected.
- Re-run `ctx index`; it is incremental. Use `ctx index --force` when a full
  reparse is intentionally required.
- `ctx inspect` and `ctx symbols` take repository-relative paths. Sensitive
  names and private-key suffixes are intentionally ignored.

## Providers and packets

- Missing `NEBIUS_API_KEY` or `NVIDIA_API_KEY` raises a provider error only when
  generation is attempted. Use `ctx provider status` to check configuration
  without printing secrets.
- Use `ctx pack ... --no-llm` for a deterministic local smoke test. Ordinary
  `ctx pack`, `ctx analyze`, and `ctx agent-plan` may require a configured
  provider.
- If packet building cannot open the index, index the repository first. If a
  provider request times out, check the endpoint, key, timeout, and retry
  variables without placing credentials in tracked files.

## MCP

- The implemented transport is stdio. Run `uv run ctx mcp serve` from the
  repository root or configure the client’s working directory explicitly.
- If no tools appear, restart the client’s MCP connection and inspect its local
  server log. Client configuration schemas are client-specific; see `mcp.md`.
- MCP rejects traversal, absolute paths, symlink escapes, and sensitive files by
  design.
