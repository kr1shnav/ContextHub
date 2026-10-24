# Reproducible offline demo

This demo uses the checked-in [`examples/demo-repository`](../examples/demo-repository)
fixture. It contains three small Python modules with real imports and symbols,
so the output is understandable without a model provider.

## Prerequisites

Use Python 3.12+ and the project’s documented `uv` workflow. From a Context Hub
checkout, run the commands below in a temporary copy of the fixture. The copy
keeps the sample’s `.context-hub` index separate from both this checkout and
your own repository.

### POSIX shell

```bash
DEMO_DIR="$(mktemp -d)"
cp -R examples/demo-repository/. "$DEMO_DIR/"
cd "$DEMO_DIR"
uv run --project /path/to/ContextHub ctx init .
uv run --project /path/to/ContextHub ctx scan .
uv run --project /path/to/ContextHub ctx index .
uv run --project /path/to/ContextHub ctx search "where are tasks queued" --limit 5
uv run --project /path/to/ContextHub ctx inspect queue.py
uv run --project /path/to/ContextHub ctx deps worker.py
uv run --project /path/to/ContextHub ctx pack "Explain how a task is submitted and processed" --no-llm
```

`/path/to/ContextHub` is an illustrative checkout path; replace it with the
actual checkout location. It is not a command to copy literally.

### PowerShell

```powershell
$demo = Join-Path ([System.IO.Path]::GetTempPath()) ("ctx-demo-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $demo | Out-Null
Copy-Item examples/demo-repository\* $demo -Recurse
Set-Location $demo
uv run --project C:\path\to\ContextHub ctx init .
uv run --project C:\path\to\ContextHub ctx scan .
uv run --project C:\path\to\ContextHub ctx index .
uv run --project C:\path\to\ContextHub ctx search "where are tasks queued" --limit 5
uv run --project C:\path\to\ContextHub ctx inspect queue.py
uv run --project C:\path\to\ContextHub ctx deps worker.py
uv run --project C:\path\to\ContextHub ctx pack "Explain how a task is submitted and processed" --no-llm
```

The provider-free `--no-llm` flag is explicit and affects only this command;
normal provider-backed commands retain their existing behavior.

## What to observe

- `scan` reports three parsed Python files and their discovered symbols/imports.
- `index` creates the isolated `.context-hub/index.db`.
- `search` should surface `queue.py` for queue-related wording; ranking is
  evidence produced by the current index and should not be treated as a
  guaranteed benchmark score.
- `inspect queue.py` shows `TaskQueue`, `add`, and `pop`.
- `deps worker.py` shows its dependency on `queue.py`.
- `pack --no-llm` builds a bounded packet locally. The packet’s selected files
  and estimated token count are the delivered evidence; estimates are not
  exact model-token measurements.

## Troubleshooting

- If search reports no index, run `ctx init .` and `ctx index .` from the demo
  directory.
- If a command cannot find a file, confirm the current directory is the copied
  demo directory and use repository-relative paths such as `queue.py`.
- Provider-backed commands may require credentials; use `--no-llm` for this
  offline walkthrough.
- If `uv` cannot start in a restricted environment, install the project using
  the procedure in the main README; do not copy a production index into the
  demo directory.

## Short portfolio recording checklist

1. Show the three fixture files and their import relationship.
2. Run `scan` and `index` in a temporary directory.
3. Search for queue behavior and point to the returned path/symbol.
4. Inspect `queue.py` and show `deps worker.py`.
5. Run the explicit `pack --no-llm` command and show selected evidence and
   estimated tokens.
6. Mention that the demo is deterministic/offline and does not prove semantic
   correctness or provider-backed behavior.
