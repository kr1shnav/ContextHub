# Continuous integration

The repository’s primary branch is `master`. `.github/workflows/ci.yml` runs on
pushes to `master` and on pull requests targeting `master`.

The workflow has three required jobs:

- Tests on Ubuntu for Python 3.12, 3.13, and 3.14, matching the package’s
  declared `requires-python = ">=3.12"` support floor. Dependencies are
  installed with the committed `uv.lock` using `uv sync --locked`.
- A package build on Python 3.12 using the configured Hatchling backend through
  `uv build`.
- A pinned `pip-audit` dependency audit against the locked environment. No
  source code, credentials, or provider API calls are sent to an external
  service by this check. GitHub’s repository-level secret scanning remains
  complementary when enabled for the repository.

There is no configured lint, formatter, or type checker in this project, so CI
does not introduce a new opinionated tool in this phase. Required jobs have no
`continue-on-error`; a failed test, build, or audit fails the workflow.

To reproduce the checks locally:

```bash
uv sync --locked
uv run --locked --with pytest==8.3.5 pytest
uv build
uv run --locked --with pip-audit==2.9.0 pip-audit --strict
```

The test suite uses mocks and deterministic fixtures for provider behavior; no
API keys are required. The matrix is Linux-only because the package does not
declare a platform-specific support policy and the existing environment gives
no established Windows CI convention. The workflow has not been claimed as
passing until it executes on GitHub; local verification remains subject to the
available Python/uv installation and network access.
