# Retrieval benchmark dataset

Phase 10.1 ships `src/context_hub/data/retrieval_benchmark_v1.json`, a versioned,
offline dataset of realistic developer questions. It contains expected repository
paths, parser-identifiable symbols, optional relevance grades (`1` to `3`), a
rationale, and an explicit `ambiguous` flag where more than one interpretation is
reasonable. It does not call a model or calculate retrieval metrics.

Validate and summarize it with:

```bash
uv run ctx benchmark-validate
```

The command first validates the Pydantic schema (required fields, unique `rh-NNN`
IDs, unique expected paths, and relevance grades), then scans the selected
repository and verifies every expected path and symbol exists. A task can be
loaded in Python with `load_dataset()` without an index, API key, or network.

## Adding a task

Add one object to the JSON `tasks` array. Choose the next unused ID, write the
question as a developer would ask it, and list only files and symbols that exist
in the repository. Use relevance `3` for primary evidence, `2` for supporting
evidence, and `1` for useful but low-priority evidence. Set `ambiguous` to `true`
when the wording intentionally has multiple plausible evidence paths.

To verify expected evidence, run `uv run ctx benchmark-validate` from the
repository root. The verifier uses `scan_repository()` and the same parser-backed
symbol names used by indexing; it reports missing files or symbols before the
dataset is accepted. Keep tasks deterministic and independent of live providers.

Phase 10.1 intentionally excludes scoring metrics, latency measurements, and
agent evaluation; those belong to Phase 10.2.
