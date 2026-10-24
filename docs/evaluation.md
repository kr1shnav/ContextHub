# Evaluation and benchmarks

The checked-in retrieval dataset is
`src/context_hub/data/retrieval_benchmark_v1.json` (version 1.0). Agent tasks
are in `agent_benchmark_v1.json`. Validate the retrieval dataset with
`ctx benchmark-validate`.

Available commands:

```bash
uv run ctx eval retrieval --k 1 3 5 --json --output retrieval.json
uv run ctx eval packets --max-files 10 --max-tokens 6000 --json --output packets.json
uv run ctx eval performance --repeats 3 --warmups 1 --json --output performance.json
uv run ctx eval agent --json --output agent.json
uv run ctx eval all --suite retrieval --suite packets --json --output evaluation.json
```

Retrieval reports Precision@K, Recall@K, MRR, per-query results, dataset
version, and index metadata. Packet reports file/symbol evidence precision and
recall, relevant coverage, estimated token usage, budgets, and compliance.
Performance reports isolated indexing/search/packet/incremental timings,
nearest-rank median/p95 values, and environment metadata. Agent reports
structural plan/proposal checks, validation passed/failed/skipped/blocked counts,
and explicit missing artifacts. `ctx eval all` combines these reports and can
save/load a schema-validated baseline with opt-in gates.

Metrics are implementation measurements, not semantic correctness proofs.
Tokens are estimates, latency is environment-dependent, model-backed judgments
are not ground truth, and human review remains required. Missing indexes,
invalid data, unavailable providers, and failed packet builds are reported as
blocked or failed rather than converted into zero scores.
