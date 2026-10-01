# Context Hub

Context Hub is context orchestration infrastructure for coding agents. This repository currently contains Phase 1: a runnable project foundation and CLI.

## Quick start

```bash
uv run ctx --help
uv run ctx version
uv run ctx init
uv run ctx status
```

`ctx init` creates `.context-hub/project.json` in the selected project directory and records the detected Git root without storing secrets.

## Local index and search

Run `ctx index` to create the ignored `.context-hub/index.db` SQLite index. Subsequent runs parse only new or modified files; use `ctx index --force` to reparse all files. Search uses deterministic lexical, symbol, path, and dependency signals:

```bash
ctx search "authentication timeout" --limit 10 --explain
```

The scores are explainable relevance scores, not probabilities. Semantic embeddings and LLM reasoning are intentionally not part of the current phase.

