from pathlib import Path

from context_hub.graph import build_code_graph
from context_hub.scanner import scan_repository


def test_graph_contains_symbols_and_resolves_imports(tmp_path: Path):
    (tmp_path / "app.py").write_text("from auth import login\n\ndef run():\n    return login()\n")
    (tmp_path / "auth.py").write_text("def login():\n    return True\n")
    graph = build_code_graph(scan_repository(tmp_path))
    assert "app.py:run" in graph.nodes
    assert any(edge.kind == "imports" and edge.target == "auth.py" for edge in graph.edges)
    assert "app.py" in graph.dependents("auth.py")


def test_graph_neighbors_and_containment(tmp_path: Path):
    (tmp_path / "mod.py").write_text("class Store:\n    def get(self):\n        pass\n")
    graph = build_code_graph(scan_repository(tmp_path))
    assert "mod.py:Store" in graph.neighbors("mod.py")
    assert "mod.py:Store:get" in graph.nodes or any(edge.target.endswith(":get") for edge in graph.edges)

