# Agent task evaluation

Phase 10.5 provides an offline structural evaluator for representative agent
tasks in `src/context_hub/data/agent_benchmark_v1.json`. The cases cover
explanation, investigation, code changes, test proposals, and error handling.
Each case identifies expected files/symbols and explicit criteria, and marks
whether checks are objective or require human judgment.

Run it without artifacts to inspect the dataset and get an explicit
`not_provided` report:

```bash
uv run ctx eval agent
uv run ctx eval agent --artifacts agent-results.json --json --output agent-evaluation.json
```

The artifact bundle is a JSON object keyed by stable task ID. Each value may
contain `plan` (a `RepositoryPlan` object), `proposal` (a `ChangeProposal`), and
`validation` (a `ValidationReport`). No patch is applied and no arbitrary command
is executed by this evaluator.

Plan checks cover expected evidence, actual repository paths/symbols, step IDs
and dependencies, and required risks/validation recommendations. Proposal checks
reuse `ProposalValidator` for unified-diff structure, safe existing paths, and
configured size limits. Validation checks count `passed`, `failed`, `not_run` as
skipped, and `incomplete` as blocked; skipped checks never count as passing.

Aggregate scores average only evaluated artifacts. Missing artifacts and malformed
artifacts remain distinct failures and are not converted to zero-quality scores.
Structural correctness cannot prove semantic correctness, and automatic scores
are not a substitute for human review. Optional model-backed judgments are not
implemented in this phase and would be reported separately from objective checks.
