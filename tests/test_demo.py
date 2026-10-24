from pathlib import Path
import shutil

from typer.testing import CliRunner

from context_hub.cli import app
from context_hub.orchestration import ContextBudget, ContextOrchestrator
from context_hub.providers import MockProvider
from context_hub.retrieval import RetrievalEngine
from context_hub.retrieval.query import RetrievalQuery
from context_hub.storage import index_repository


FIXTURE = Path(__file__).parents[1] / "examples" / "demo-repository"


def test_offline_demo_workflow_is_isolated_and_returns_expected_evidence(tmp_path: Path, monkeypatch):
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    monkeypatch.chdir(tmp_path)

    index_repository(tmp_path)
    results = RetrievalEngine(tmp_path / ".context-hub" / "index.db").search(
        RetrievalQuery(task="where are tasks queued", max_results=5)
    )
    assert any(result.path == "queue.py" for result in results)

    packet = ContextOrchestrator(
        tmp_path, MockProvider(), budget=ContextBudget(max_files=3, max_tokens=1000)
    ).build("Explain how a task is submitted and processed")
    selected = {item.path for item in packet.files}
    assert selected & {"app.py", "queue.py", "worker.py"}
    assert packet.statistics.files_selected == len(packet.files)
    assert packet.statistics.estimated_tokens <= 1000


def test_documented_demo_cli_commands_work_without_provider(tmp_path: Path, monkeypatch):
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, ["init", "."]).exit_code == 0
    assert runner.invoke(app, ["scan", "."]).exit_code == 0
    assert runner.invoke(app, ["index", "."]).exit_code == 0
    assert runner.invoke(app, ["inspect", "queue.py"]).exit_code == 0
    assert runner.invoke(app, ["deps", "worker.py"]).exit_code == 0
    result = runner.invoke(app, ["pack", "Explain task processing", "--no-llm"])
    assert result.exit_code == 0
    assert "Context Packet" in result.stdout
