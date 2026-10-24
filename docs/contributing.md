# Contributing

Context Hub targets Python 3.12+ and uses `uv` with the committed `uv.lock`.
Install the project with `uv sync`. Tests use pytest as an ephemeral tool:

```bash
uv sync --locked
uv run --locked --with pytest==8.3.5 pytest
```

The project has no configured formatter, linter, or type checker. Keep changes
focused, use the existing Pydantic/Typer model and CLI conventions, preserve
read-only and path-safety boundaries, and add deterministic tests for behavior
changes. Provider tests should use mocks; never commit API keys.

For CI-equivalent checks, run `uv build` and
`uv run --locked --with pip-audit==2.9.0 pip-audit --strict`. Pull requests to
and pushes on `master` run the GitHub Actions workflow in `.github/workflows`.
Review documentation examples against `ctx --help` and the relevant command
implementation. Use focused conventional commits and describe any checks that
could not run locally.
