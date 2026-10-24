# Architecture and data flow

Context Hub is a local repository-intelligence pipeline. The implementation is
metadata-first: retrieval reads the SQLite index and does not read source files;
packet assembly later reads only selected, safe repository files.

## Repository scan and index

`scan_repository(root)` walks the root, excludes generated directories and
sensitive names/suffixes, detects languages, and parses supported source files
into `RepositoryFile`, `ParsedSource`, `Symbol`, and `Import` models. Files are
sorted by repository-relative POSIX path.

`index_repository(root)` stores repositories, files, symbols, and imports in
`.context-hub/index.db` through `IndexDatabase`. It compares content hashes and
tracks new, modified, unchanged, deleted, and parsed counts in `IndexResult`.
Updates are transactional. Run `ctx index` after changing the repository.

## Code graph and retrieval

`build_code_graph(repository)` creates repository/file/symbol/external nodes and
IMPORTS, DEPENDS_ON, DEFINES, and CONTAINS relationships in an in-memory
`CodeGraph`. `ctx graph`, `ctx deps`, and `ctx dependents` expose graph views.

`RetrievalEngine.search(RetrievalQuery)` loads indexed files, symbols, and
imports. It tokenizes the task, scores path/import matches and exact symbol
matches, adds bounded dependency/dependent signals, and returns deterministic
`RetrievalResult` objects sorted by score, path, and symbol. `ctx search` prints
paths, symbols, scores, signals, reasons, and estimated tokens.

## Context packet assembly

`ContextOrchestrator.build(task)` combines provider task analysis, indexed
retrieval, repository scanning, graph expansion, evidence prioritization, and
budgeting. The final `ContextPacket` contains only safe files that fit the
configured `ContextBudget`; its `ContextStatistics` reports selected files and
estimated tokens. `context_plan.candidate_paths` are candidates, not delivered
evidence. `ctx pack --no-llm` uses `MockProvider`; normal packet analysis uses
the configured provider.

## MCP boundary

`ctx mcp serve` starts `serve_stdio()`, which creates a FastMCP server and
registers four read-only tools: `search_context`, `inspect_file`,
`get_dependencies`, and `build_context_packet`. Path validation rejects
absolute paths, traversal, symlink escapes, and sensitive files. Returned packet
content is redacted for common secret assignments. The only implemented MCP
transport is stdio.

## Agent harness

`AgentHarness` is planning-only. It builds a packet, asks the configured
provider for validated `AgentModelResult` or `RepositoryPlan` data, bounds
iterations, and returns `AgentOutcome`/`RepositoryPlan`. `ToolExecutor` exposes
only bounded read-only search, inspect, dependency, and packet tools. It cannot
run arbitrary shell commands or write files.

`ProposalGenerator` creates evidence-bounded `ChangeProposal` objects containing
unified diffs for existing safe files. `ProposalValidator` performs structural
checks first and executes only explicitly approved `pytest` or `py_compile`
checks with `--execute`; proposals are never applied by these components.

## Trust boundaries

Provider output is untrusted structured data and is validated with Pydantic.
Credentials stay in the launching environment. Repository paths are resolved
against the selected root. Evaluation and performance commands use mocks or
temporary copies where applicable, and do not change the production index.
