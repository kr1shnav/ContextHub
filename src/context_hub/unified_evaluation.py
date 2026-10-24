"""Unified Phase 10.6 evaluation orchestration and regression gates."""
from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .agent_evaluation import AgentTaskDataset, evaluate_agent_dataset
from .benchmark import load_dataset, verify_expected_evidence
from .evaluation import evaluate_dataset, index_metadata
from .orchestration import ContextBudget, ContextOrchestrator
from .packet_evaluation import evaluate_packets
from .performance import run_performance_benchmark
from .providers import MockProvider
from .retrieval import RetrievalEngine

REPORT_SCHEMA_VERSION = "1.0"
SUITES = ("retrieval", "packets", "performance", "agent")


class SuiteReport(BaseModel):
    name: str
    status: Literal["completed", "skipped", "blocked", "failed"]
    dataset_version: str | None = None
    aggregate: dict[str, object] = Field(default_factory=dict)
    tasks: list[dict[str, object]] = Field(default_factory=list)
    report: dict[str, object] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    reason: str | None = None


class BaselineComparison(BaseModel):
    supplied: bool
    compatible: bool
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, dict[str, float | None]] = Field(default_factory=dict)


class UnifiedReport(BaseModel):
    schema_version: str
    dataset_versions: dict[str, str | None]
    configuration: dict[str, object]
    environment: dict[str, str | int]
    repository: dict[str, object]
    suites: list[SuiteReport]
    failures: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)
    quality_gate_failures: list[str] = Field(default_factory=list)
    baseline: BaselineComparison

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


def _environment() -> dict[str, str | int]:
    return {"python": sys.version.split()[0], "platform": platform.platform()}


def _suite_from(name: str, status: str, *, dataset_version: str | None = None, report: BaseModel | None = None, reason: str | None = None, failures: list[str] | None = None) -> SuiteReport:
    data = report.model_dump(mode="json") if report else {}
    return SuiteReport(name=name, status=status, dataset_version=dataset_version, aggregate=data.get("aggregate", {}), tasks=data.get("queries", data.get("cases", [])), report=data, reason=reason, failures=failures or [])


def _baseline_compare(current: UnifiedReport, baseline_path: Path | None) -> BaselineComparison:
    if not baseline_path:
        return BaselineComparison(supplied=False, compatible=False, reasons=["No baseline supplied."])
    try:
        baseline = UnifiedReport.model_validate_json(baseline_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return BaselineComparison(supplied=True, compatible=False, reasons=[f"Baseline schema invalid: {type(exc).__name__}: {exc}"])
    reasons: list[str] = []
    if baseline.schema_version != current.schema_version: reasons.append("report schema versions differ")
    if baseline.dataset_versions != current.dataset_versions: reasons.append("dataset versions differ")
    if baseline.configuration.get("suites") != current.configuration.get("suites"): reasons.append("selected suites differ")
    if baseline.environment != current.environment: reasons.append("Python or platform environment differs")
    if reasons:
        return BaselineComparison(supplied=True, compatible=False, reasons=reasons)
    metrics: dict[str, dict[str, float | None]] = {}
    for name in SUITES:
        old = next((item for item in baseline.suites if item.name == name and item.status == "completed"), None)
        new = next((item for item in current.suites if item.name == name and item.status == "completed"), None)
        if not old or not new: continue
        for key in ("precision", "recall", "mrr", "relevant_evidence_coverage", "median_seconds"):
            old_value = _metric(old, key); new_value = _metric(new, key)
            if old_value is not None and new_value is not None: metrics[f"{name}.{key}"] = {"baseline": old_value, "current": new_value, "delta": new_value - old_value}
    return BaselineComparison(supplied=True, compatible=True, reasons=[], metrics=metrics)


def _metric(suite: SuiteReport, key: str) -> float | None:
    if key == "precision": return _as_float(suite.aggregate.get("1", {}).get("precision"))
    if key == "recall": return _as_float(suite.aggregate.get("1", {}).get("recall"))
    if key == "mrr": return _as_float(suite.aggregate.get("1", {}).get("mrr"))
    if key == "relevant_evidence_coverage": return _as_float(suite.aggregate.get("relevant_evidence_coverage"))
    return _as_float(suite.report.get("initial_indexing", {}).get("stats", {}).get("median_seconds"))


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def run_unified_evaluation(root: Path, *, suites: list[str] | None = None, baseline: Path | None = None, repeats: int = 3, warmups: int = 1, ks: list[int] | None = None,
                           budget: ContextBudget | None = None, gates: dict[str, float] | None = None) -> UnifiedReport:
    selected = suites or list(SUITES)
    invalid = sorted(set(selected) - set(SUITES))
    if invalid: raise ValueError(f"unsupported suites: {', '.join(invalid)}")
    root = root.resolve(); dataset = load_dataset(); agent_dataset = AgentTaskDataset.default(); budget = budget or ContextBudget(); ks = ks or [1, 3, 5]; gates = gates or {}
    versions = {"retrieval": dataset.version if "retrieval" in selected else None, "packets": dataset.version if "packets" in selected else None, "performance": dataset.version if "performance" in selected else None, "agent": agent_dataset.version if "agent" in selected else None}
    suites_out: list[SuiteReport] = []; failures: list[str] = []; skipped: list[str] = [name for name in SUITES if name not in selected]; blocked: list[str] = []
    for name in skipped:
        suites_out.append(_suite_from(name, "skipped", reason="Suite was not selected."))
    db = root / ".context-hub" / "index.db"
    evidence_errors = verify_expected_evidence(dataset, root) if db.is_file() else []
    for name in selected:
        try:
            if name in {"retrieval", "packets"} and not db.is_file():
                reason = "No Context Hub index found; run `ctx index` first."
                suites_out.append(_suite_from(name, "blocked", dataset_version=dataset.version, reason=reason)); blocked.append(name); continue
            if name in {"retrieval", "packets"} and evidence_errors:
                reason = "; ".join(evidence_errors); suites_out.append(_suite_from(name, "blocked", dataset_version=dataset.version, reason=reason)); blocked.append(name); continue
            if name == "retrieval":
                result = evaluate_dataset(dataset, RetrievalEngine(db), ks, index_metadata=index_metadata(db, root))
                suites_out.append(_suite_from(name, "completed", dataset_version=dataset.version, report=result))
            elif name == "packets":
                result = evaluate_packets(dataset, ContextOrchestrator(root, MockProvider(), budget=budget), budget, index_metadata=index_metadata(db, root))
                suites_out.append(_suite_from(name, "completed", dataset_version=dataset.version, report=result))
            elif name == "performance":
                result = run_performance_benchmark(root, dataset, repeats=repeats, warmups=warmups, budget=budget)
                suites_out.append(_suite_from(name, "completed", dataset_version=dataset.version, report=result))
            elif name == "agent":
                result = evaluate_agent_dataset(agent_dataset, root)
                suites_out.append(_suite_from(name, "completed", dataset_version=agent_dataset.version, report=result))
        except Exception as exc:
            suites_out.append(_suite_from(name, "failed", dataset_version=versions[name], reason=str(exc), failures=[f"{type(exc).__name__}: {exc}"])); failures.append(name)
    report = UnifiedReport(schema_version=REPORT_SCHEMA_VERSION, dataset_versions=versions, configuration={"suites": selected, "k_values": ks, "repeats": repeats, "warmups": warmups, "budgets": budget.model_dump(mode="json"), "offline": True}, environment=_environment(), repository={"root": str(root), "index_present": db.is_file()}, suites=suites_out, failures=failures, skipped=skipped, blocked=blocked, baseline=BaselineComparison(supplied=False, compatible=False, reasons=["comparison pending"]))
    comparison = _baseline_compare(report, baseline); report.baseline = comparison
    if gates:
        retrieval = next((s for s in suites_out if s.name == "retrieval"), None); packets = next((s for s in suites_out if s.name == "packets"), None)
        if "min_retrieval_precision" in gates and (not retrieval or retrieval.status != "completed" or (_metric(retrieval, "precision") or 0) < gates["min_retrieval_precision"]): report.quality_gate_failures.append("minimum retrieval precision gate failed")
        if "min_packet_coverage" in gates and (not packets or packets.status != "completed" or (_metric(packets, "relevant_evidence_coverage") or 0) < gates["min_packet_coverage"]): report.quality_gate_failures.append("minimum packet coverage gate failed")
        if "max_budget_violation_rate" in gates and packets and packets.status == "completed":
            compliance = _as_float(packets.aggregate.get("budget_compliance_rate")); violations = 1 - compliance if compliance is not None else 1
            if violations > gates["max_budget_violation_rate"]: report.quality_gate_failures.append("maximum packet budget-violation gate failed")
        if "max_latency_regression" in gates and comparison.compatible:
            metric = comparison.metrics.get("performance.median_seconds")
            if metric and metric["baseline"] and (metric["current"] - metric["baseline"]) / metric["baseline"] > gates["max_latency_regression"]: report.quality_gate_failures.append("maximum latency regression gate failed")
    return report


def render_unified_summary(report: UnifiedReport) -> str:
    lines = [f"Unified evaluation {report.schema_version}", f"Datasets: {report.dataset_versions}"]
    for suite in report.suites: lines.append(f"{suite.name}: {suite.status}" + (f" ({suite.reason})" if suite.reason else ""))
    lines.append(f"Failures: {len(report.failures)} | Blocked: {len(report.blocked)} | Gates failed: {len(report.quality_gate_failures)}")
    if report.baseline.supplied: lines.append(f"Baseline compatible: {report.baseline.compatible}")
    return "\n".join(lines)
