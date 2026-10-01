from pathlib import Path

from context_hub.retrieval import RetrievalEngine, RetrievalQuery
from context_hub.storage import index_repository


def test_query_tokenization_and_explainable_results(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth_session.py").write_text("class SessionManager:\n    def refresh_token(self): pass\n")
    (tmp_path / "src" / "other.py").write_text("def unrelated(): pass\n")
    db = tmp_path / "index.db"
    index_repository(tmp_path, database_path=db)
    results = RetrievalEngine(db).search(RetrievalQuery(task="Fix SessionManager refresh token", max_results=10))
    assert results
    assert any(result.path == "src/auth_session.py" and "symbol_match" in result.signals for result in results)
    assert all(result.estimated_tokens > 0 and result.reasons for result in results)


def test_empty_and_limited_queries(tmp_path: Path):
    (tmp_path / "readme.md").write_text("authentication timeout")
    db = tmp_path / "index.db"
    index_repository(tmp_path, database_path=db)
    assert RetrievalEngine(db).search("the and") == []
    assert len(RetrievalEngine(db).search(RetrievalQuery(task="authentication", max_results=1))) <= 1

