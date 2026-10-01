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

