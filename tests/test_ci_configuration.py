from pathlib import Path
import tomllib


ROOT = Path(__file__).parents[1]


def test_ci_targets_actual_primary_branch_and_supported_python_floor():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "branches: [master]" in workflow
    assert 'python-version: ["3.12", "3.13", "3.14"]' in workflow
    assert metadata["project"]["requires-python"] == ">=3.12"


def test_ci_uses_locked_install_build_and_required_failure_steps():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "uv sync --locked" in workflow
    assert "uv build" in workflow
    assert "pip-audit==2.9.0" in workflow
    assert "continue-on-error" not in workflow
    assert "API_KEY" not in workflow
