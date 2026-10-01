# Context Hub

> Context orchestration for AI coding agents.

Context Hub builds a structured, local-first understanding of a software repository so coding agents receive task-specific context instead of an arbitrary pile of files. It combines repository intelligence, a code graph, incremental indexing, and explainable hybrid retrieval.

## Project status

| Phase | Status |
| --- | --- |
| 1 — Foundation | ✅ Complete |
| 2 — Repository Intelligence | ✅ Complete |
| 3 — Code Graph | ✅ Complete |
| 4 — Persistent Index | ✅ Complete |
| 5 — Hybrid Retrieval | ✅ Complete |
| 6 — Nebius + NVIDIA Nemotron | Planned |
| 7 — Context Orchestrator | Planned |
| 8 — MCP / Agent Integration | Planned |
| 9 — Developer Experience / Demo | Planned |

## The problem

Coding agents often receive too little context, too much irrelevant context, or manually selected files. A keyword search or simple top-k retrieval can miss the relationships that explain how a change propagates through a repository.

For “fix the authentication timeout,” useful context may span `src/auth/session.py`, `src/auth/token.py`, `src/api/routes.py`, `src/models/user.py`, related tests, and documentation. The important question is which symbols, dependencies, callers, tests, and documents are connected to the task.

## The solution

Context Hub incrementally scans a repository, extracts structure, builds a code graph, persists metadata locally, and ranks context using multiple deterministic signals.

```text
Developer Task → Query Normalization → Repository Retrieval
      → Code Graph Signals → Relevance Ranking → Explainable Results
      → Future Context Packet → AI Coding Agent
```

Task planning, context packets, and model-assisted orchestration are planned for later phases.

## Why it is different

Context Hub is not primarily a chatbot, vector database, or generic RAG wrapper:

```text
Query → Embeddings → Top 5 chunks → LLM
```

Its current relationship-aware path is:

```text
Task → Query normalization → Lexical/symbol/path matching
     → Structural and dependency signals → Code-graph expansion
     → Explainable ranking → Relevant repository context
```

Semantic embeddings are intentionally not part of the current implementation.

## Current capabilities

- Repository scanning that respects `.gitignore` and excludes sensitive files
- SHA-256 file hashing, language detection, symbol extraction, and import extraction
- Python AST parsing plus heuristic fallback parsing for other supported languages
- Deterministic repository, file, symbol, and external graph nodes
- Import, dependency, containment, and definition relationships
- Local SQLite index at `.context-hub/index.db`
- Incremental new, modified, unchanged, and deleted-file detection
- Transactional updates and `--force` reindexing
- Lexical, symbol, path, import, dependency, and dependent retrieval
- Deterministic scoring, result limits, explanations, and token-size estimates

## Supported languages

Language detection supports Python, JavaScript, TypeScript, Java, C, C++, Go, Rust, HTML, CSS, JSON, YAML, Markdown, SQL, and Shell. Python uses the built-in AST parser. Several other languages use conservative heuristic parsing; a Tree-sitter integration boundary is available for future grammar support. Detection support does not imply equivalent structural parsing quality.

## Architecture

```text
                         CONTEXT HUB
                              │
              ┌───────────────┴───────────────┐
              │                               │
         Repository                       Developer Task
              ↓                               ↓
     Repository Intelligence          Query Processing
              ↓                               ↓
          Code Graph                 Hybrid Retrieval
              └───────────────┬───────────────┘
                              ↓
                    Explainable Ranking
                              ↓
                     Future Context Packet
                              ↓
                      AI Coding Agent
```

### Code graph

```text
File ── DEFINES ──→ Symbol
File ── IMPORTS ──→ Module or external package
File ── DEPENDS_ON → File
Symbol ── DEFINED_IN → File
```

If `session.py` is relevant, dependencies and dependents can surface related modules instead of treating it as an isolated text chunk. Unresolved imports remain observable and are marked unresolved.

### Retrieval

```text
Task → Query normalization → Candidate generation
     ├─ symbol matching
     ├─ path matching
     ├─ lexical/import matching
     └─ dependency/dependent matching
     → Score, merge, deduplicate → Deterministic ranking
     → Explainable results
```

Scores are bounded relevance scores, not probabilities. Token estimates use a simple character-based approximation.

## CLI

| Command | Purpose |
| --- | --- |
| `ctx --help` / `ctx version` | Help and version |
| `ctx init` / `ctx status` | Project and index metadata |
| `ctx scan` | Scan repository intelligence |
| `ctx inspect <path>` | Inspect a file |
| `ctx symbols <path>` | List file symbols |
| `ctx graph` | Summarize the in-memory graph |
| `ctx deps <path>` / `ctx dependents <path>` | Dependency queries |
| `ctx index` / `ctx index --force` | Create or update the SQLite index |
| `ctx search "<query>"` | Search indexed context |
| `ctx search "<query>" --explain` | Show retrieval explanations |

## Quick start

```bash
git clone https://github.com/kr1shnav/ContextHub.git
cd ContextHub
uv sync
uv run ctx init
uv run ctx index
uv run ctx status
uv run ctx search "authentication timeout"
```

Example output varies with the indexed repository, but every result includes its path, score, signals, reason, and estimated token size.

## Project structure

```text
src/context_hub/
├── cli.py, config.py, languages.py, models.py
├── parsing.py, scanner.py, graph.py
├── storage/       # database.py, indexer.py
└── retrieval/     # engine.py, models.py, query.py
tests/
├── test_foundation.py, test_repository_intelligence.py
├── test_graph.py, test_storage.py, test_retrieval.py
```

## Design and security

Context Hub is local-first, deterministic where possible, explainable, repository-aware, incremental, modular, provider-independent, and graph-aware. The scanner respects `.gitignore` and excludes `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `credentials.*`, and `secrets.*`. Source contents are not stored in the graph or persistent index. The SQLite database is local generated state; never commit API keys, credentials, tokens, or private keys.

## Development

```bash
uv sync
uv run pytest
```

Tests use temporary repositories and databases and do not require network access.

## Roadmap

- ✅ Phases 1–5: Foundation, Repository Intelligence, Code Graph, Persistent Index, Hybrid Retrieval
- Planned: Phase 6 Nebius + NVIDIA Nemotron
- Planned: Phase 7 Context Orchestrator
- Planned: Phase 8 MCP / Agent Integration
- Planned: Phase 9 Developer Experience / Demo

## Hackathon direction

Context Hub is being developed for the Coding and Agentic Engineering track of the Nebius × NVIDIA Global AI Hackathon. The planned Phase 6 integration will use Nebius Token Factory and NVIDIA Nemotron for task analysis and context orchestration. That integration is not yet implemented; the current core is deterministic and provider-independent.

## Contributing

Fork or clone the repository, create a feature branch, make a focused change with tests, run `uv run pytest` and `git diff --check`, then open a pull request.

## Technology

Python 3.12+, Typer, Rich, Pydantic v2, SQLite through Python’s standard library, and a Tree-sitter integration boundary. No vector database, search server, LLM, or cloud service is required for the current phases.
