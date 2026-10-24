from pathlib import Path
import re


ROOT = Path(__file__).parents[1]


def test_readme_links_point_to_checked_in_guides():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\((docs/[^)]+)\)", readme)
    assert links
    assert all((ROOT / link).is_file() for link in links)


def test_documented_quickstart_uses_registered_commands():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for command in ("ctx init .", "ctx index .", "ctx search", "ctx inspect", "ctx pack"):
        assert command in readme
    assert "--no-llm" in readme


def test_documentation_does_not_contain_merge_markers_or_api_key_values():
    for path in [ROOT / "README.md", *((ROOT / "docs").glob("*.md"))]:
        text = path.read_text(encoding="utf-8")
        assert "<<<<<<<" not in text
        assert "=======" not in text
        assert ">>>>>>>" not in text
        assert "test-key" not in text
