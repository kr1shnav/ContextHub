from pathlib import Path

from context_hub.proposals import ChangeProposal, ProposedFileDiff
from context_hub.validation import CheckKind, ProposalValidator, ValidationCheck, ValidationRequest, ValidationStatus

PATCH = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"

def proposal():
    return ChangeProposal(summary="Update", rationale="Test", files=[ProposedFileDiff(path="app.py", patch=PATCH)])

def test_default_validation_is_structural_and_skips_checks(tmp_path: Path):
    (tmp_path / "app.py").write_text("old\n", encoding="utf-8")
    report = ProposalValidator(tmp_path).validate(proposal(), ValidationRequest(checks=[ValidationCheck(kind=CheckKind.PYTEST)]))
    assert report.status == ValidationStatus.NOT_RUN
    assert report.checks[0].status == ValidationStatus.NOT_RUN

def test_explicit_check_uses_fixed_command_and_reports_nonzero(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("old\n", encoding="utf-8")
    calls = []
    class Completed: returncode = 2; stdout = "safe"; stderr = "failure"
    def fake_run(command, **kwargs): calls.append((command, kwargs)); return Completed()
    monkeypatch.setattr("context_hub.validation.subprocess.run", fake_run)
    report = ProposalValidator(tmp_path).validate(proposal(), ValidationRequest(execute=True, checks=[ValidationCheck(kind=CheckKind.PYTEST)]))
    assert report.status == ValidationStatus.FAILED
    assert report.checks[0].exit_code == 2
    assert calls[0][0][-2:] == ["-m", "pytest"]
    assert calls[0][1]["shell"] is False and calls[0][1]["cwd"] == tmp_path.resolve()

def test_timeout_is_not_reported_as_passing(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("old\n", encoding="utf-8")
    def timeout(*args, **kwargs):
        import subprocess
        raise subprocess.TimeoutExpired("pytest", 1)
    monkeypatch.setattr("context_hub.validation.subprocess.run", timeout)
    report = ProposalValidator(tmp_path).validate(proposal(), ValidationRequest(execute=True, checks=[ValidationCheck(kind=CheckKind.PYTEST)]))
    assert report.status == ValidationStatus.FAILED
    assert "timed out" in report.checks[0].summary

def test_invalid_target_fails_before_execution(tmp_path):
    (tmp_path / "app.py").write_text("old\n", encoding="utf-8")
    bad = ChangeProposal(summary="x", rationale="x", files=[ProposedFileDiff(path="missing.py", patch=PATCH.replace("app.py", "missing.py"))])
    report = ProposalValidator(tmp_path).validate(bad)
    assert report.status == ValidationStatus.FAILED
