from pathlib import Path

from context_hub.orchestration.orchestrator import _apply_reasoning, _budget, _evidence, _packet
from context_hub.orchestration.models import ContextPlan, ContextBudget
from context_hub.retrieval.models import RetrievalResult
from context_hub.providers.models import TaskAnalysis


def test_explicit_candidate_path_is_materialized_and_prioritized(tmp_path: Path):
    (tmp_path / "orchestrator.py").write_text("class ContextOrchestrator: pass\n")
    result = _evidence([], [], tmp_path, {"orchestrator.py"}, priority_paths=["orchestrator.py"])
    assert len(result) == 1
    assert result[0].path == "orchestrator.py"
    assert result[0].source == "analysis"


def test_explicit_candidate_precedes_higher_scoring_non_candidate(tmp_path: Path):
    (tmp_path / "orchestrator.py").write_text("class ContextOrchestrator: pass\n")
    (tmp_path / "models.py").write_text("class ContextPacket: pass\n")
    result = _evidence([RetrievalResult(item_id="models", path="models.py", score=1, reason="symbol", estimated_tokens=10)], [], tmp_path, {"orchestrator.py", "models.py"}, priority_paths=["orchestrator.py"])
    assert [item.path for item in result] == ["orchestrator.py", "models.py"]


def test_reasoning_resort_preserves_explicit_candidate_priority():
    evidence = [
        RetrievalResult(item_id="models", path="models.py", score=1, reason="symbol"),
        RetrievalResult(item_id="orchestrator", path="orchestrator.py", score=.9, reason="candidate"),
    ]
    result = _apply_reasoning(evidence, {"priority_paths": []}, set(), priority_paths=["orchestrator.py"])
    assert [item.path for item in result] == ["orchestrator.py", "models.py"]


def test_packet_selects_explicit_implementation_when_it_fits_budget(tmp_path: Path):
    (tmp_path / "orchestrator.py").write_text("class ContextOrchestrator:\n    def build(self):\n        return ContextPacket()\n")
    (tmp_path / "models.py").write_text("class ContextPacket: pass\n")
    evidence = _evidence(
        [RetrievalResult(item_id="models", path="models.py", score=1, reason="symbol", estimated_tokens=10)],
        [], tmp_path, {"orchestrator.py", "models.py"}, priority_paths=["orchestrator.py"],
    )
    analysis = TaskAnalysis(task="explain", task_type="explanation", confidence=0.5, reasoning="test")
    packet = _packet("explain", analysis, ContextPlan(task="explain", task_type="explanation"), evidence, 2, 2, tmp_path, [], ContextBudget(max_files=3, max_tokens=100))
    assert [item.path for item in packet.files] == ["orchestrator.py", "models.py"]
    assert packet.statistics.files_selected == 2
    assert packet.statistics.graph_nodes_selected == 0


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
