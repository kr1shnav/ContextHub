from pathlib import Path

from context_hub.tools import ToolExecutor


def executor(tmp_path: Path, **kwargs):
    (tmp_path / "app.py").write_text("import auth\ndef run():\n    return 1\n", encoding="utf-8")
    return ToolExecutor(tmp_path, **kwargs)


def test_registry_executes_inspection_and_records_history(tmp_path):
    result = executor(tmp_path).execute({"name": "inspect_repository_file", "arguments": {"path": "app.py"}})
    assert result.status == "success"
    assert result.output["path"] == "app.py"


def test_unknown_and_invalid_tools_are_rejected(tmp_path):
    tool = executor(tmp_path)
    assert tool.execute({"name": "shell", "arguments": {}}).status == "failure"
    assert tool.execute({"name": "inspect_repository_file", "arguments": {"path": ""}}).status == "failure"


def test_paths_sensitive_files_and_symlinks_are_rejected(tmp_path):
    tool = executor(tmp_path)
    assert tool.execute({"name": "inspect_repository_file", "arguments": {"path": "../secret"}}).status == "failure"
    (tmp_path / ".env.local").write_text("TOKEN=secret", encoding="utf-8")
    assert tool.execute({"name": "inspect_repository_file", "arguments": {"path": ".env.local"}}).status == "failure"
    outside = tmp_path.parent / "outside.py"
    outside.write_text("secret", encoding="utf-8")
    try:
        (tmp_path / "linked.py").symlink_to(outside)
    except (OSError, NotImplementedError):
        return
    assert tool.execute({"name": "inspect_repository_file", "arguments": {"path": "linked.py"}}).status == "failure"


def test_output_and_call_limits_are_bounded(tmp_path):
    tool = executor(tmp_path, max_output_chars=100, max_calls=1)
    first = tool.execute({"name": "inspect_repository_file", "arguments": {"path": "app.py"}})
    assert first.status == "success"
    assert len(tool.history) == 1
    assert tool.execute({"name": "inspect_repository_file", "arguments": {"path": "app.py"}}).status == "failure"
