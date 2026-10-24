from pathlib import Path
import tomllib

from typer.testing import CliRunner

from context_hub import __version__
from context_hub.cli import app


ROOT = Path(__file__).parents[1]


def test_package_metadata_declares_supported_installation_contract():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    assert project["requires-python"] == ">=3.12"
    assert project["scripts"]["ctx"] == "context_hub.cli:app"
    assert "pydantic" in " ".join(project["dependencies"])
    assert metadata["build-system"]["build-backend"] == "hatchling.build"


def test_cli_entrypoint_version_is_available_without_provider_configuration():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"Context Hub {__version__}" in result.stdout


def test_offline_pack_command_exposes_no_llm_option():
    result = CliRunner().invoke(
        app,
        ["pack", "--help"],
        color=False,
        terminal_width=120,
    )
    assert result.exit_code == 0
    assert "--no-llm" in result.stdout
