# Retrieval baseline evaluation

Phase 10.2 evaluates the validated Phase 10.1 dataset with the existing
`RetrievalEngine`; it does not change ranking, call a provider, or use a network.

```bash
uv run ctx eval retrieval --k 1 3 5
uv run ctx eval retrieval --k 1 3 5 --json --output retrieval-baseline.json
```

An index must exist at `.context-hub/index.db`; otherwise the command fails with
an instruction to run `ctx index`. JSON includes the dataset version, available
index metadata, K values, aggregate metrics, and every query’s metrics.

For each query, expected evidence is converted to unique relevance units. An
expected path with no symbols is one file unit `(path, file)`. When symbols are
listed, each `(path, symbol)` is its own unit and a file-only result does not
match it. A result matches an exact symbol unit or a file unit at its path.
Duplicate result identities and duplicate matched units count once.

For K, `hits@K` is the number of unique matched units in the first K returned
results. `Precision@K = hits@K / K`; `Recall@K = hits@K / total relevant units`;
`MRR@K` is `1 / rank` for the first matching result, or zero if none appears in
the first K. Aggregate values are arithmetic means over all queries, including
explicitly labelled ambiguous cases. An omitted relevance grade is validated as
the schema’s default relevance grade 3; it is not silently treated as irrelevant.
K values must be positive integers and are deduplicated and sorted.
