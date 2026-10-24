# Performance and scalability benchmarks

Phase 10.4 measures the existing indexing, retrieval, and packet-building
implementations without changing them. The benchmark command copies the selected
repository into temporary directories and creates SQLite indexes there; the
user’s repository and `.context-hub/index.db` are never mutated.

```bash
uv run ctx eval performance --repeats 3 --warmups 1
uv run ctx eval performance --repeats 5 --warmups 2 --json --output performance.json
```

The dataset is validated before running. Each initial-index sample uses a fresh
isolated copy. Search and packet timings use all Phase 10.1 queries for each
measured repeat. Incremental samples use fresh copies for unchanged, modified,
added, and deleted scenarios. Index counts include the existing `IndexResult`
fields (`scanned`, `new`, `modified`, `unchanged`, `deleted`, `parsed`); skipped
is reported as `scanned - parsed` because the indexer does not expose a separate
skipped count.

Timings are wall-clock `perf_counter` measurements and are environment-dependent.
Median is the middle sample (the average of the two middle samples for an even
count). p95 uses nearest rank: `ceil(0.95 * N)`, with one sample returning that
sample. Warmups are exported separately and excluded from measured statistics.
Repeat counts are limited to 1–100 and warmups to 0–20.

Packet measurements use `MockProvider` and are labelled deterministic; the
reported packet time is total wall-clock orchestrator time because the current
interfaces do not instrument provider versus local phases separately. No live
provider or network access is required. Failures are recorded per operation and
are not converted into fabricated timing samples. Measurements from different
machines or configurations should not be compared as equivalent.
