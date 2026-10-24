# Unified evaluation and regression gates

Phase 10.6 combines the implemented retrieval, packet, performance, and agent
evaluation suites:

```bash
uv run ctx eval all --json --output evaluation.json
uv run ctx eval all --suite retrieval --suite agent --json
uv run ctx eval all --baseline evaluation-baseline.json --min-retrieval-precision 0.70 --min-packet-coverage 0.60
uv run ctx eval all --save-baseline evaluation-baseline.json
```

The default is offline. Retrieval and packet suites use the existing local index
and packet path with `MockProvider`; performance uses isolated temporary copies;
agent evaluation is structural and consumes optional artifact bundles. A missing
index blocks only retrieval and packet suites. A suite not selected is explicitly
reported as `skipped`. The command exits nonzero for blocked or failed selected
suites and for failed configured quality gates.

The JSON report has schema version `1.0`, dataset versions, selected-suite
configuration, budgets/K/repeat settings, repository/index and environment
metadata, each suite’s raw per-task results and aggregates, failures/skips/blocks,
and baseline comparison data. Save a successful report as a baseline and pass it
to `--baseline`; the loader validates the full report schema. Comparisons are
marked incompatible when schema, dataset versions, selected suites, Python, or
platform differ, and incompatible metrics are not presented as trustworthy.

Regression gates are opt-in because no project baseline justifies universal
defaults. Available thresholds are `--min-retrieval-precision`,
`--min-packet-coverage`, `--max-budget-violation-rate`, and
`--max-latency-regression` (fractional values, for example `0.10` for 10%). A
CI job can save the JSON artifact and fail on the command’s exit status:

```bash
uv run ctx eval all --baseline ci-baseline.json \
  --min-retrieval-precision 0.70 \
  --max-budget-violation-rate 0.00 \
  --output ci-evaluation.json
```

These are structural and empirical checks, not proof of semantic correctness.
Performance measurements are environment-dependent, packet tokens are estimates,
and human review remains necessary for plan meaning, patch correctness, and
overall agent task quality.
