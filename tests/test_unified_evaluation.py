from pathlib import Path

import pytest

from context_hub.unified_evaluation import BaselineComparison, UnifiedReport, _baseline_compare, run_unified_evaluation


def report(*, platform="test", datasets=None):
    return UnifiedReport(schema_version="1.0", dataset_versions=datasets or {"retrieval": "1.0"}, configuration={"suites": ["retrieval"]}, environment={"python": "3.12", "platform": platform}, repository={}, suites=[], baseline=BaselineComparison(supplied=False, compatible=False, reasons=[]))


def test_unified_report_round_trips_and_baseline_schema_is_validated(tmp_path: Path):
    path = tmp_path / "baseline.json"
    path.write_text(report().model_dump_json(), encoding="utf-8")
    comparison = _baseline_compare(report(), path)
    assert comparison.compatible is True
    path.write_text("{}", encoding="utf-8")
    invalid = _baseline_compare(report(), path)
    assert invalid.compatible is False
    assert invalid.reasons


def test_incompatible_environment_and_dataset_are_not_comparable(tmp_path: Path):
    path = tmp_path / "baseline.json"
    path.write_text(report(platform="other").model_dump_json(), encoding="utf-8")
    comparison = _baseline_compare(report(), path)
    assert comparison.compatible is False
    assert comparison.reasons


def test_missing_index_blocks_selected_retrieval_and_packet_suites(tmp_path: Path):
    result = run_unified_evaluation(tmp_path, suites=["retrieval", "packets", "agent"], repeats=1, warmups=0)
    assert set(result.blocked) == {"retrieval", "packets"}
    assert result.suites[-1].status == "completed"


def test_unknown_suite_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="unsupported suites"):
        run_unified_evaluation(tmp_path, suites=["missing"])


def test_gate_threshold_fails_when_required_suite_is_blocked(tmp_path: Path):
    result = run_unified_evaluation(tmp_path, suites=["retrieval"], gates={"min_retrieval_precision": 0.5})
    assert result.quality_gate_failures
