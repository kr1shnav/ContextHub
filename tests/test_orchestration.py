from pathlib import Path

from context_hub.orchestration.orchestrator import _budget, _evidence
from context_hub.orchestration.models import ContextBudget
from context_hub.retrieval.models import RetrievalResult


def test_explicit_candidate_path_is_materialized_and_prioritized(tmp_path: Path):
    (tmp_path / "orchestrator.py").write_text("class ContextOrchestrator: pass\n")
    result = _evidence([], [], tmp_path, {"orchestrator.py"}, priority_paths=["orchestrator.py"])
    assert len(result) == 1
    assert result[0].path == "orchestrator.py"
    assert result[0].source == "analysis"


def test_evidence_deduplication_and_graph_counts_use_unique_paths(tmp_path: Path):
    (tmp_path / "a.py").write_text("x\n")
    result = _evidence([], [("a.py", "imports", 1, "root.py"), ("a.py", "imports", 2, "other.py")], tmp_path, {"a.py"})
    assert len(result) == 1
    assert len({item.path for item in result}) == 1


def test_budget_respects_file_and_token_limits():
    evidence = [
        RetrievalResult(item_id="a", path="a.py", score=1, reason="a", estimated_tokens=40),
        RetrievalResult(item_id="b", path="b.py", score=.9, reason="b", estimated_tokens=40),
        RetrievalResult(item_id="c", path="c.py", score=.8, reason="c", estimated_tokens=40),
    ]
    selected = _budget(evidence, ContextBudget(max_files=2, max_tokens=70))
    assert [item.path for item in selected] == ["a.py"]
