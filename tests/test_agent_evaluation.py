from pathlib import Path

import pytest

from context_hub.agent_evaluation import AgentTaskDataset, evaluate_agent_dataset
from context_hub.validation import ValidationStatus


ROOT = Path(__file__).parents[1]


def dataset(expected_files=None):
    return AgentTaskDataset.model_validate({"version": "1.0", "name": "test", "tasks": [{"id": f"agent-{i:03d}", "description": "Evaluate this repository task", "kind": "code_change", "expected_files": expected_files or ["src/context_hub/agent_harness.py"], "criteria": ["check evidence"], "require_risks": True, "require_validation_recommendations": True} for i in range(1, 6)]})


def plan(**overrides):
    value = {"summary": "Safe plan", "objective": "Inspect and change code", "steps": [{"id": "inspect", "description": "Inspect the harness", "files": ["src/context_hub/agent_harness.py"]}], "evidence_files": ["src/context_hub/agent_harness.py"], "evidence_symbols": ["AgentHarness"], "risks": ["semantic behavior may change"], "validation_commands": ["pytest tests/test_agent_harness.py"]}
    value.update(overrides)
    return value


def test_correct_plan_has_evidence_and_valid_dependencies():
    report = evaluate_agent_dataset(dataset(), ROOT, artifacts={f"agent-{i:03d}": {"plan": plan()} for i in range(1, 6)})
    assert report.aggregate["average_plan_score"] == 1
    assert report.aggregate["average_evidence_coverage"] == 1


def test_incorrect_plan_reports_missing_evidence_and_unsupported_claims():
    report = evaluate_agent_dataset(dataset(), ROOT, artifacts={"agent-001": {"plan": plan(evidence_files=["missing.py"], risks=[], validation_commands=[])}})
    case = report.cases[0]
    assert case.plan_score < 1
    assert case.unsupported_claims
    assert case.failures


def test_malformed_plan_is_a_failed_case():
    report = evaluate_agent_dataset(dataset(), ROOT, artifacts={"agent-001": {"plan": {"summary": "bad"}}})
    assert report.failed_cases == 1
    assert report.cases[0].status == "failed"


def test_malformed_patch_is_failed_without_applying_anything():
    proposal = {"summary": "Change", "rationale": "Test", "files": [{"path": "src/context_hub/agent_harness.py", "patch": "not a diff"}]}
    report = evaluate_agent_dataset(dataset(), ROOT, artifacts={"agent-001": {"proposal": proposal}})
    assert report.cases[0].proposal_score < 1
    assert "static validation" in report.cases[0].failures[0]


def test_unsafe_proposal_path_is_rejected():
    proposal = {"summary": "Change", "rationale": "Test", "files": [{"path": "../secrets.py", "patch": "--- a/../secrets.py\n+++ b/../secrets.py\n@@ -1 +1 @@\n-x\n+y\n"}]}
    report = evaluate_agent_dataset(dataset(), ROOT, artifacts={"agent-001": {"proposal": proposal}})
    assert report.cases[0].status == "failed"


def test_missing_artifact_is_not_provided_not_zero_score():
    report = evaluate_agent_dataset(dataset(), ROOT)
    assert report.aggregate["not_provided_cases"] == 5
    assert report.aggregate["average_plan_score"] is None


def test_validation_skipped_and_blocked_are_distinct():
    validation = {"proposal_id": "x", "status": "not_run", "checks": [{"kind": "pytest", "status": "not_run"}, {"kind": "py_compile", "status": "incomplete"}]}
    report = evaluate_agent_dataset(dataset(), ROOT, artifacts={"agent-001": {"validation": validation}})
    counts = report.cases[0].validation
    assert counts.skipped == 1
    assert counts.blocked == 1
    assert counts.passed == 0


def test_duplicate_agent_ids_rejected():
    with pytest.raises(ValueError, match="unique"):
        AgentTaskDataset.model_validate({"version": "1.0", "name": "x", "tasks": [{"id": "agent-001", "description": "A valid task description", "kind": "explanation", "expected_files": ["a.py"], "criteria": ["criterion"]}] * 5})
