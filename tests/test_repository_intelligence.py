from pathlib import Path

from context_hub.languages import detect_language
from context_hub.parsing import PythonParser, RegexParser
from context_hub.scanner import scan_repository


def test_scan_hashes_and_ignores_secrets(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("import os\ndef run():\n    pass\n")
    (tmp_path / ".env").write_text("TOKEN=private")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("function x() {}")
    repo = scan_repository(tmp_path)
    assert [f.path for f in repo.files] == ["src/app.py"]
    assert repo.files[0].content_hash


def test_language_registry():
    assert detect_language(Path("main.py")) == "Python"
    assert detect_language(Path("main.ts")) == "TypeScript"
    assert detect_language(Path("schema.sql")) == "SQL"


def test_python_symbols_and_imports():
    parsed = PythonParser().parse("import os\nclass A:\n    def go(self):\n        pass\n", file="a.py", language="Python")
    assert {s.name for s in parsed.symbols} == {"A", "go"}
    assert parsed.symbols[1].parent == "A"
    assert parsed.imports[0].name == "os"


def test_additional_language_and_malformed_python():
    parsed = RegexParser().parse("class Widget {}\nfunction run() {}", file="x.js", language="JavaScript")
    assert {s.name for s in parsed.symbols} == {"Widget", "run"}
    assert PythonParser().parse("def broken(", file="bad.py", language="Python").parse_error

