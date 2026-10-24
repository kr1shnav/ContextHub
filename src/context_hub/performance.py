"""Isolated, reproducible performance measurements for Context Hub."""
from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from .benchmark import BenchmarkDataset
from .orchestration import ContextBudget, ContextOrchestrator
from .providers import MockProvider
from .retrieval import RetrievalEngine, RetrievalQuery
from .storage import IndexResult, index_repository


class TimingStats(BaseModel):
    samples: int
    median_seconds: float | None
    p95_seconds: float | None


class TimedOperation(BaseModel):
    operation: str
    warmup_seconds: list[float] = Field(default_factory=list)
    timings_seconds: list[float] = Field(default_factory=list)
    stats: TimingStats
    index_counts: list[dict[str, int]] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    per_query_seconds: dict[str, list[float]] = Field(default_factory=dict)


class IncrementalScenario(BaseModel):
    name: str
    warmup_seconds: list[float] = Field(default_factory=list)
    timings_seconds: list[float] = Field(default_factory=list)
    stats: TimingStats
    index_results: list[dict[str, int]] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


class PerformanceReport(BaseModel):
    dataset_version: str
    repository: dict[str, int | str]
    environment: dict[str, str | int | bool]
    repeat_count: int
    warmup_count: int
    provider_mode: str
    initial_indexing: TimedOperation
    search: TimedOperation
    packet: TimedOperation
    incremental_indexing: list[IncrementalScenario]
    notes: list[str] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


def validate_repeats(repeats: int, warmups: int) -> tuple[int, int]:
    if repeats <= 0 or warmups < 0 or repeats > 100 or warmups > 20:
        raise ValueError("repeats must be 1..100 and warmups must be 0..20")
    return repeats, warmups


def percentile(values: list[float], percent: float) -> float | None:
    """Nearest-rank percentile; a one-sample p95 equals that sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int((percent / 100) * len(ordered) + 0.999999))
    return ordered[rank - 1]


def timing_stats(values: list[float]) -> TimingStats:
    ordered = sorted(values)
    median = None if not ordered else ordered[(len(ordered) - 1) // 2] if len(ordered) % 2 else (ordered[len(ordered)//2 - 1] + ordered[len(ordered)//2]) / 2
    return TimingStats(samples=len(values), median_seconds=median, p95_seconds=percentile(values, 95))


def _time(call: Callable[[], object]) -> tuple[float, object]:
    started = time.perf_counter()
    result = call()
    return time.perf_counter() - started, result


def _copy_repository(source: Path, destination: Path) -> None:
    ignored = shutil.ignore_patterns(".git", ".venv", ".uv-cache*", ".pytest_cache", ".context-hub", "__pycache__", "dist", "build")
    shutil.copytree(source, destination, ignore=ignored)


def _index_once(source: Path) -> tuple[float, IndexResult]:
    database = source / ".context-hub" / "index.db"
    return _time(lambda: index_repository(source, database_path=database))


def _operation(name: str, warmups: list[float], timings: list[float], failures: list[str]) -> TimedOperation:
    return TimedOperation(operation=name, warmup_seconds=warmups, timings_seconds=timings, stats=timing_stats(timings), failures=failures)


def _result_counts(result: IndexResult) -> dict[str, int]:
    return {field: getattr(result, field) for field in ("scanned", "new", "modified", "unchanged", "deleted", "parsed")}


def _incremental(source: Path, scenario: str, repeats: int, warmups: int) -> IncrementalScenario:
    timings: list[float] = []
    warmup_times: list[float] = []
    results: list[dict[str, int]] = []
    failures: list[str] = []
    for run in range(repeats + warmups):
        with tempfile.TemporaryDirectory(prefix="ctx-perf-inc-") as temp:
            root = Path(temp) / "repo"
            _copy_repository(source, root)
            _, initial = _index_once(root)
            if scenario == "modified":
                target = root / "src" / "context_hub" / "benchmark.py"
                target.write_text(target.read_text(encoding="utf-8") + "\n# isolated benchmark mutation\n", encoding="utf-8")
            elif scenario == "added":
                (root / "src" / "context_hub" / "_perf_added.py").write_text("value = 1\n", encoding="utf-8")
            elif scenario == "deleted":
                (root / "src" / "context_hub" / "_perf_deleted.py").write_text("value = 1\n", encoding="utf-8")
                index_repository(root, database_path=root / ".context-hub" / "index.db")
                (root / "src" / "context_hub" / "_perf_deleted.py").unlink()
            try:
                elapsed, result = _index_once(root)
                if run < warmups: warmup_times.append(elapsed)
                else:
                    timings.append(elapsed); results.append(_result_counts(result))
            except Exception as exc:
                failures.append(f"run {run}: {type(exc).__name__}: {exc}")
    return IncrementalScenario(name=scenario, warmup_seconds=warmup_times, timings_seconds=timings, stats=timing_stats(timings), index_results=results, failures=failures)


def run_performance_benchmark(source: Path, dataset: BenchmarkDataset, *, repeats: int = 3, warmups: int = 1,
                              budget: ContextBudget | None = None) -> PerformanceReport:
    validate_repeats(repeats, warmups)
    source = source.resolve()
    queries = [task.query for task in dataset.tasks]
    budget = budget or ContextBudget()
    initial_warmups: list[float] = []; initial_timings: list[float] = []; initial_failures: list[str] = []; index_counts: list[dict[str, int]] = []
    search_warmups: list[float] = []; search_timings: list[float] = []; search_failures: list[str] = []; search_per_query: dict[str, list[float]] = {task.id: [] for task in dataset.tasks}
    packet_warmups: list[float] = []; packet_timings: list[float] = []; packet_failures: list[str] = []; packet_per_query: dict[str, list[float]] = {task.id: [] for task in dataset.tasks}
    with tempfile.TemporaryDirectory(prefix="ctx-perf-base-") as temp:
        prepared = Path(temp) / "repo"
        _copy_repository(source, prepared)
        for run in range(repeats + warmups):
            with tempfile.TemporaryDirectory(prefix="ctx-perf-index-") as index_temp:
                repo = Path(index_temp) / "repo"
                _copy_repository(source, repo)
                try:
                    elapsed, result = _index_once(repo)
                    if run < warmups: initial_warmups.append(elapsed)
                    else: initial_timings.append(elapsed); index_counts.append(_result_counts(result))
                except Exception as exc: initial_failures.append(f"run {run}: {type(exc).__name__}: {exc}")
        _, initial = _index_once(prepared)
        engine = RetrievalEngine(prepared / ".context-hub" / "index.db")
        orchestrator = ContextOrchestrator(prepared, MockProvider(), budget=budget)
        for run in range(repeats + warmups):
            for task, query in zip(dataset.tasks, queries):
                try:
                    elapsed, _ = _time(lambda query=query: engine.search(RetrievalQuery(task=query, max_results=20)))
                    if run < warmups: search_warmups.append(elapsed)
                    else: search_timings.append(elapsed); search_per_query[task.id].append(elapsed)
                except Exception as exc: search_failures.append(f"run {run}: {type(exc).__name__}: {exc}")
            for task, query in zip(dataset.tasks, queries):
                try:
                    elapsed, _ = _time(lambda query=query: orchestrator.build(query))
                    if run < warmups: packet_warmups.append(elapsed)
                    else: packet_timings.append(elapsed); packet_per_query[task.id].append(elapsed)
                except Exception as exc: packet_failures.append(f"run {run}: {type(exc).__name__}: {exc}")
        repo_files = sum(1 for path in prepared.rglob("*") if path.is_file() and ".context-hub" not in path.parts)
        repo_bytes = sum(path.stat().st_size for path in prepared.rglob("*") if path.is_file() and ".context-hub" not in path.parts)
    incremental = [_incremental(source, scenario, repeats, warmups) for scenario in ("unchanged", "modified", "added", "deleted")]
    initial_op = _operation("initial_indexing", initial_warmups, initial_timings, initial_failures)
    initial_op = initial_op.model_copy(update={"index_counts": index_counts})
    return PerformanceReport(dataset_version=dataset.version, repository={"files": repo_files, "bytes": repo_bytes, "indexed_files": initial.scanned, "parsed": initial.parsed, "skipped": initial.scanned - initial.parsed},
        environment={"python": sys.version.split()[0], "platform": platform.platform(), "processor": platform.processor() or "unknown", "cpu_count": os.cpu_count() or 1, "isolated": True},
        repeat_count=repeats, warmup_count=warmups, provider_mode="mock (deterministic; packet timing is total wall-clock)",
        initial_indexing=initial_op, search=_operation("search", search_warmups, search_timings, search_failures).model_copy(update={"per_query_seconds": search_per_query}), packet=_operation("packet", packet_warmups, packet_timings, packet_failures).model_copy(update={"per_query_seconds": packet_per_query}), incremental_indexing=incremental,
        notes=["Wall-clock timings are environment-dependent.", "p95 uses nearest-rank and is not a cross-environment comparison.", "Initial index counts are per measured isolated run; search and packet samples are per query and repeat."])


def render_performance_summary(report: PerformanceReport) -> str:
    lines = [f"Performance benchmark — dataset {report.dataset_version} | repeats={report.repeat_count}, warmups={report.warmup_count}",
             f"Repository: {report.repository['files']} files, {report.repository['bytes']} bytes (isolated={report.environment['isolated']})"]
    for item in (report.initial_indexing, report.search, report.packet):
        lines.append(f"{item.operation}: median={item.stats.median_seconds} s, p95={item.stats.p95_seconds} s, samples={item.stats.samples}, failures={len(item.failures)}")
    for item in report.incremental_indexing:
        lines.append(f"incremental/{item.name}: median={item.stats.median_seconds} s, p95={item.stats.p95_seconds} s, samples={item.stats.samples}")
    return "\n".join(lines)
