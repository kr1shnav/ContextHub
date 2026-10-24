"""Offline structural evaluation for agent plans, proposals, and validation reports."""
from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .agent_harness import RepositoryPlan
from .benchmark import verify_expected_evidence
from .proposals import ChangeProposal, ProposalLimits
from .validation import ValidationReport, ValidationStatus, ProposalValidator


class AgentTaskCase(BaseModel):
    id: str = Field(pattern=r"^agent-[0-9]{3}$")
    description: str = Field(min_length=10)
    kind: Literal["explanation", "investigation", "code_change", "test_proposal", "error_handling"]
    expected_files: list[str] = Field(min_length=1)
    expected_symbols: list[str] = Field(default_factory=list)
    criteria: list[str] = Field(min_length=1)
    objective_checks: bool = True
    require_risks: bool = False
    require_validation_recommendations: bool = False


class AgentTaskDataset(BaseModel):
    version: str = Field(pattern=r"^1\.0$")
    name: str = Field(min_length=1)
    tasks: list[AgentTaskCase] = Field(min_length=5)

    @field_validator("tasks")
    @classmethod
    def unique_ids(cls, value: list[AgentTaskCase]) -> list[AgentTaskCase]:
        ids = [task.id for task in value]
        if len(ids) != len(set(ids)):
            raise ValueError("agent task IDs must be unique")
        return value

    @classmethod
    def load(cls, path: Path) -> "AgentTaskDataset":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    @classmethod
    def default(cls) -> "AgentTaskDataset":
        return cls.load(Path(__file__).with_name("data") / "agent_benchmark_v1.json")


class ValidationCounts(BaseModel):
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    blocked: int = 0


class AgentCaseResult(BaseModel):
    id: str
    kind: str
    status: Literal["evaluated", "not_provided", "failed"]
    objective_checks: bool
    plan_score: float | None = None
    proposal_score: float | None = None
    evidence_coverage: float | None = None
    relevant_file_coverage: float | None = None
    dependency_structure_valid: bool | None = None
    unsupported_claims: list[str] = Field(default_factory=list)
    validation: ValidationCounts | None = None
    failures: list[str] = Field(default_factory=list)


class AgentEvaluationReport(BaseModel):
    dataset_version: str
    dataset_name: str
    configuration: dict[str, object]
    environment: dict[str, str]
    aggregate: dict[str, float | int | None]
    cases: list[AgentCaseResult]

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


def _repo_symbols(root: Path) -> set[str]:
    from .scanner import scan_repository
    return {symbol.name for item in scan_repository(root).files if item.parsed for symbol in item.parsed.symbols}


def _plan_checks(case: AgentTaskCase, plan: RepositoryPlan, root: Path) -> AgentCaseResult:
    expected = set(case.expected_files)
    referenced = set(plan.evidence_files) | {path for step in plan.steps for path in step.files}
    actual_files = {path for path in referenced if (root / path).is_file()}
    unsupported = sorted(referenced - actual_files)
    symbols = _repo_symbols(root)
    unsupported += [f"symbol:{symbol}" for symbol in sorted(set(plan.evidence_symbols) | {symbol for step in plan.steps for symbol in step.symbols}) if symbol not in symbols]
    covered = len(expected & set(plan.evidence_files))
    dependencies_valid = True
    ids = {step.id for step in plan.steps}
    if len(ids) != len(plan.steps) or any(dep not in ids or dep == step.id for step in plan.steps for dep in step.depends_on):
        dependencies_valid = False
    failures = []
    if not covered == len(expected): failures.append("required expected evidence is incomplete")
    if unsupported: failures.append("plan contains unsupported repository claims")
    if not dependencies_valid: failures.append("step dependency structure is invalid")
    if case.require_risks and not plan.risks: failures.append("risks are required for this task")
    if case.require_validation_recommendations and not plan.validation_commands: failures.append("validation recommendations are required for this task")
    checks = [covered == len(expected), not bool(unsupported), dependencies_valid]
    if case.require_risks: checks.append(bool(plan.risks))
    if case.require_validation_recommendations: checks.append(bool(plan.validation_commands))
    score = sum(checks) / len(checks)
    return AgentCaseResult(id=case.id, kind=case.kind, status="evaluated", objective_checks=case.objective_checks, plan_score=score,
        evidence_coverage=covered / len(expected), relevant_file_coverage=len(actual_files & expected) / len(expected),
        dependency_structure_valid=dependencies_valid, unsupported_claims=unsupported, failures=failures)


def _proposal_checks(case: AgentTaskCase, proposal: ChangeProposal, root: Path) -> AgentCaseResult:
    failures: list[str] = []
    try:
        report = ProposalValidator(root, limits=ProposalLimits()).validate(proposal)
        if report.status == ValidationStatus.FAILED: failures.append("proposal failed static validation")
    except Exception as exc:
        failures.append(f"proposal validation error: {type(exc).__name__}: {exc}")
    paths = {item.path for item in proposal.files}
    expected = set(case.expected_files)
    covered = len(paths & expected)
    if not expected <= paths: failures.append("required expected change paths are missing")
    if case.require_risks and not proposal.risks: failures.append("risks are required for this task")
    if case.require_validation_recommendations and not proposal.validation_recommendations: failures.append("validation recommendations are required for this task")
    score = 1.0 if not failures else 0.5 * covered / len(expected)
    return AgentCaseResult(id=case.id, kind=case.kind, status="evaluated", objective_checks=case.objective_checks, proposal_score=score, relevant_file_coverage=covered / len(expected), failures=failures)


def _validation_counts(report: ValidationReport) -> ValidationCounts:
    counts = ValidationCounts()
    for check in report.checks:
        if check.status == ValidationStatus.PASSED: counts.passed += 1
        elif check.status == ValidationStatus.FAILED: counts.failed += 1
        elif check.status == ValidationStatus.NOT_RUN: counts.skipped += 1
        else: counts.blocked += 1
    return counts


def evaluate_agent_dataset(dataset: AgentTaskDataset, root: Path, *, artifacts: dict[str, dict[str, object]] | None = None) -> AgentEvaluationReport:
    artifacts = artifacts or {}
    cases: list[AgentCaseResult] = []
    for case in dataset.tasks:
        artifact = artifacts.get(case.id)
        if not artifact:
            cases.append(AgentCaseResult(id=case.id, kind=case.kind, status="not_provided", objective_checks=case.objective_checks, failures=["no plan/proposal/validation artifact supplied"]))
            continue
        try:
            result: AgentCaseResult | None = None
            if artifact.get("plan") is not None:
                result = _plan_checks(case, RepositoryPlan.model_validate(artifact["plan"]), root)
            if artifact.get("proposal") is not None:
                result = _proposal_checks(case, ChangeProposal.model_validate(artifact["proposal"]), root)
            if result is None:
                result = AgentCaseResult(id=case.id, kind=case.kind, status="evaluated", objective_checks=case.objective_checks, failures=["artifact has no plan or proposal"])
            if artifact.get("validation") is not None:
                result.validation = _validation_counts(ValidationReport.model_validate(artifact["validation"]))
            cases.append(result)
        except Exception as exc:
            cases.append(AgentCaseResult(id=case.id, kind=case.kind, status="failed", objective_checks=case.objective_checks, failures=[f"{type(exc).__name__}: {exc}"]))
    evaluated = [case for case in cases if case.status == "evaluated"]
    def average(field: str) -> float | None:
        values = [getattr(case, field) for case in evaluated if getattr(case, field) is not None]
        return sum(values) / len(values) if values else None
    aggregate = {"evaluated_cases": len(evaluated), "not_provided_cases": sum(case.status == "not_provided" for case in cases), "failed_cases": sum(case.status == "failed" for case in cases),
                 "average_plan_score": average("plan_score"), "average_proposal_score": average("proposal_score"), "average_evidence_coverage": average("evidence_coverage"), "average_relevant_file_coverage": average("relevant_file_coverage")}
    return AgentEvaluationReport(dataset_version=dataset.version, dataset_name=dataset.name, configuration={"offline": True, "artifacts_supplied": len(artifacts)},
        environment={"python": sys.version.split()[0], "platform": platform.platform()}, aggregate=aggregate, cases=cases)


def render_agent_summary(report: AgentEvaluationReport) -> str:
    a = report.aggregate
    return "\n".join([f"Agent evaluation — dataset {report.dataset_version} ({a['evaluated_cases']}/{len(report.cases)} evaluated)",
        f"Plan score: {a['average_plan_score']} | Proposal score: {a['average_proposal_score']}",
        f"Evidence coverage: {a['average_evidence_coverage']} | Relevant-file coverage: {a['average_relevant_file_coverage']}",
        f"Not provided: {a['not_provided_cases']} | Failed: {a['failed_cases']}"])
