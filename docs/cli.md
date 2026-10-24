# CLI reference

Run commands from the repository root. Use `uv run ctx --help` and each
subcommand’s `--help` for the installed Typer-generated help.

## Project and repository commands

| Command | Options/arguments | Prerequisite and effect |
|---|---|---|
| `ctx version` | none | Prints the package version. |
| `ctx init [PATH]` | default `.` | Creates local `.context-hub` metadata. |
| `ctx status [PATH]` | default `.` | Shows project and index status. |
| `ctx index [PATH]` | `--force`; default `.` | Scans and transactionally creates/updates `.context-hub/index.db`. |
| `ctx scan [PATH]` | default `.` | Reports scanned files, parsed sources, symbols, and imports. |
| `ctx inspect PATH` | repository-relative file path | Prints metadata, symbols, and imports. |
| `ctx symbols PATH` | repository-relative file path | Lists parsed symbols. |
| `ctx graph [PATH]` | default `.` | Summarizes the in-memory code graph. |
| `ctx deps PATH` | repository-relative file path | Lists direct dependencies. |
| `ctx dependents PATH` | repository-relative file path | Lists files that depend on the target. |

`ctx search QUERY` requires an existing `.context-hub/index.db`. Options are
`--limit` (1–100, default 20), `--path` to restrict a prefix, and `--explain`.
`ctx benchmark-validate` validates the checked-in retrieval dataset; it accepts
`--dataset PATH` and `--repository PATH`.

## Context and providers

`ctx pack TASK` accepts `--max-files` (default 10), `--max-tokens` (default
6000), `--no-llm`, and `--json`. Without `--no-llm`, provider configuration and
an index are required. `ctx analyze TASK` accepts `--limit` (default 10) and
`--json`. `ctx provider status` prints provider settings without revealing key
values.

## MCP and agent commands

- `ctx mcp serve` starts the local stdio MCP server.
- `ctx agent-plan TASK` accepts `--max-files`, `--max-tokens`, and `--json` and
  returns a read-only repository plan.
- `ctx agent propose TASK` accepts `--max-files`, `--max-tokens`, `--output-dir`,
  `--filename`, and `--json`; it generates a reviewable proposal and never
  applies it.
- `ctx agent validate PROPOSAL_FILE` accepts `--execute`, repeated `--check`
  values (`pytest` or `py_compile`), `--path` for `py_compile`, and `--json`.
  Without `--execute`, requested checks are `not_run`.

## Evaluation commands

All evaluation commands support `--json` and, where listed, `--output PATH`.

- `ctx eval retrieval`: repeated `--k` values (default 1, 3, 5), optional
  `--dataset`; requires an index.
- `ctx eval packets`: `--max-files` (10), `--max-tokens` (6000),
  `--max-characters` (24000), and optional dataset/output; uses `MockProvider`.
- `ctx eval performance`: `--repository`, `--repeats` (3), `--warmups` (1),
  packet budget options, dataset, and output; uses isolated temporary copies.
- `ctx eval agent`: `--repository`, `--dataset`, and optional `--artifacts PATH`
  containing a JSON bundle keyed by agent task ID.
- `ctx eval all`: repeated `--suite` values (`retrieval`, `packets`,
  `performance`, `agent`), `--baseline`, `--save-baseline`, retrieval `--k`,
  performance repeats/warmups, packet budgets, and opt-in gate thresholds.

Evaluation prerequisites and report formats are described in
[evaluation.md](evaluation.md). No command in this reference applies generated
patches or executes arbitrary agent-provided commands.
