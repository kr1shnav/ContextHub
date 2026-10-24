from pathlib import Path
import tomllib


ROOT = Path(__file__).parents[1]


def test_package_metadata_and_console_entry_point():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    assert project["name"] == "context-hub"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.12"
    assert project["scripts"] == {"ctx": "context_hub.cli:app"}
    assert project["dependencies"]
    assert (ROOT / "LICENSE").is_file()
    assert project["license"]["file"] == "LICENSE"


def test_build_configuration_isolated_to_package_and_release_metadata():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["build-system"]["build-backend"] == "hatchling.build"
    assert config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/context_hub"]
    assert set(config["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]) == {
        "src/context_hub/**", "README.md", "LICENSE", "CHANGELOG.md"
    }
    assert not list(ROOT.glob("*.db"))
    assert not list(ROOT.glob("*.whl"))
