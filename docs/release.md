# Release preparation

Context Hub currently declares version `0.1.0`, requires Python 3.12 or newer,
and builds with Hatchling. Runtime dependencies are declared in
[`pyproject.toml`](../pyproject.toml); the only console entry point is
`ctx = context_hub.cli:app`.

This repository prepares artifacts but does not publish to PyPI, create GitHub
releases, push tags, or handle credentials.

## Build and inspect locally

From a clean checkout with Python 3.12+ and `uv`:

```bash
uv sync --locked
uv build
python -m zipfile -l dist/context_hub-*.whl
tar -tf dist/context-hub-*.tar.gz
```

The wheel should contain the `context_hub` package and generated metadata,
including the `ctx` entry point. The source distribution is intentionally
limited to package sources and release metadata (`README.md`, `LICENSE`, and
`CHANGELOG.md`). Build output belongs in `dist/`, which is ignored. Inspect
archives before distributing them and confirm they contain no `.context-hub`
database, `.env` file, credential, cache, or personal path.

To test a wheel without changing the project environment, create a temporary
environment and install the local wheel:

```bash
python -m venv /tmp/context-hub-release-check
/tmp/context-hub-release-check/bin/python -m pip install dist/context_hub-*.whl
/tmp/context-hub-release-check/bin/ctx --help
```

The equivalent Windows interpreter path is `<temporary-env>\Scripts\python.exe`
and the command is `<temporary-env>\Scripts\ctx.exe --help`. These paths are
placeholders, not machine-specific project configuration.

## Tagged CI candidate

`.github/workflows/release.yml` runs for tags matching `v*`. It builds the
wheel and source distribution, checks archive contents for forbidden local
artifacts, and uploads them as workflow artifacts. It does not publish them.
The tag should match the version in `pyproject.toml` (for example, `v0.1.0`);
the workflow fails on a mismatch.

## Checklist

1. Update `pyproject.toml` and `CHANGELOG.md` together.
2. Review the diff and run the focused package metadata tests.
3. Run `uv sync --locked`, `uv build`, and inspect both archives.
4. Install the wheel in a clean temporary environment and run `ctx --help`.
5. Confirm CI passes for the candidate tag.
6. Obtain explicit authorization before creating a tag, publishing, or
   distributing artifacts.

## Limitations

Artifact checks prove packaging structure and startup only; they do not prove
semantic correctness, provider availability, or compatibility with every
platform. Environment blockers must be reported rather than treated as passes.
