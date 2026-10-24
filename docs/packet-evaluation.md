# Context packet quality evaluation

Phase 10.3 evaluates the actual `ContextPacket` returned by
`ContextOrchestrator.build`. It uses `MockProvider` in the CLI, so it does not
call a live model. This is a deterministic provider-backed path through the
real orchestrator; a future provider-backed run should be reported separately.

```bash
uv run ctx eval packets --max-files 10 --max-tokens 6000
uv run ctx eval packets --max-files 10 --max-tokens 6000 --json --output packet-baseline.json
```

The command requires `.context-hub/index.db`, validates the benchmark evidence,
and reports packet-construction failures separately. It uses only `packet.files`
and the packet’s selected evidence collections, plus
`packet.statistics.files_selected` and `packet.statistics.estimated_tokens`.
Candidate paths in `context_plan` are never treated as delivered evidence.

File precision is `relevant selected paths / selected paths`; file recall is
`relevant selected paths / expected paths`. Expected entries with symbols also
contribute their path to file metrics. Symbol precision and recall use exact
`(path, symbol)` pairs and are `n/a` for a query with no expected symbols.
Relevant evidence coverage is the fraction of expected units covered, where a
symbol-bearing entry contributes one unit per symbol and a symbol-less entry
contributes one file unit. Duplicate selected evidence is counted once.

Token values are explicitly estimates because the existing packet model exposes
`estimated_tokens`, not an exact tokenizer count. Average, p50, and p95 are
computed over successful cases using nearest-rank percentiles. Budget compliance
requires both estimated tokens `<= max_tokens` and selected files `<= max_files`.
Aggregate quality and usage averages exclude failed packet builds; failures stay
in the per-task JSON. Ambiguous tasks remain included and are marked in each
per-task result. Missing symbol labels are not treated as negative evidence.
