from pathlib import Path

import pytest

from context_hub.providers.config import ProviderSettings
from context_hub.scanner import scan_repository
from context_hub.validation import CheckKind, ProposalValidator, ValidationCheck, ValidationRequest
from context_hub.proposals import ChangeProposal, ProposedFileDiff


def _proposal():
    return ChangeProposal(
        summary="Update", rationale="Test",
        files=[ProposedFileDiff(path="app.py", patch="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n")],
    )


def test_scanner_excludes_sensitive_variants(tmp_path: Path):
    (tmp_path / "credentials.json").write_text("secret", encoding="utf-8")
    (tmp_path / "secrets.yaml").write_text("secret", encoding="utf-8")
    (tmp_path / "safe.py").write_text("x = 1\n", encoding="utf-8")
    assert [item.path for item in scan_repository(tmp_path).files] == ["safe.py"]


def test_scanner_does_not_follow_file_symlink_outside_root(tmp_path: Path):
    outside = tmp_path.parent / "scanner-outside.py"
    outside.write_text("token = 'outside'\n", encoding="utf-8")
    link = tmp_path / "linked.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")
    assert all(item.path != "linked.py" for item in scan_repository(tmp_path).files)


def test_provider_url_rejects_non_http_and_embedded_credentials():
    with pytest.raises(ValueError, match="HTTP"):
        ProviderSettings(base_url="file:///tmp/index")
    with pytest.raises(ValueError, match="credentials"):
        ProviderSettings(base_url="https://user:password@example.test/v1")


def test_validation_output_redacts_secret_like_text(monkeypatch, tmp_path: Path):
    (tmp_path / "app.py").write_text("old\n", encoding="utf-8")

    class Completed:
        returncode = 2
        stdout = "API_KEY=super-secret"
        stderr = "Bearer abc123"

    monkeypatch.setattr("context_hub.validation.subprocess.run", lambda *args, **kwargs: Completed())
    report = ProposalValidator(tmp_path).validate(
        _proposal(), ValidationRequest(execute=True, checks=[ValidationCheck(kind=CheckKind.PYTEST)])
    )
    assert "super-secret" not in report.failure_output
    assert "abc123" not in report.failure_output
    assert "<redacted>" in report.failure_output
