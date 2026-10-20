from pathlib import Path

from context_hub.storage import IndexDatabase, index_repository


def test_incremental_indexing(tmp_path: Path):
    (tmp_path / "a.py").write_text("import b\ndef a(): pass\n")
    (tmp_path / "b.py").write_text("def b(): pass\n")
    db = tmp_path / "index.db"
    first = index_repository(tmp_path, database_path=db)
    second = index_repository(tmp_path, database_path=db)
    assert (first.new, first.parsed) == (2, 2)
    assert (second.new, second.modified, second.unchanged, second.parsed) == (0, 0, 2, 0)
    (tmp_path / "b.py").write_text("def changed(): pass\n")
    changed = index_repository(tmp_path, database_path=db)
    assert (changed.modified, changed.parsed) == (1, 1)


def test_deleted_file_and_schema(tmp_path: Path):
    file_path = tmp_path / "gone.py"
    file_path.write_text("def gone(): pass\n")
    db_path = tmp_path / "index.db"
    index_repository(tmp_path, database_path=db_path)
    file_path.unlink()
    result = index_repository(tmp_path, database_path=db_path)
    assert result.deleted == 1
    with IndexDatabase(db_path) as database:
        assert database.connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == "1"


def test_reindex_removes_files_that_become_excluded(tmp_path: Path):
    cached_file = tmp_path / "generated.py"
    cached_file.write_text("def generated(): pass\n")
    db_path = tmp_path / "index.db"
    index_repository(tmp_path, database_path=db_path)
    cache = tmp_path / ".uv-cache"
    cache.mkdir()
    cached_file.replace(cache / "generated.py")
    with IndexDatabase(db_path) as database:
        assert database.connection.execute("SELECT COUNT(*) FROM files WHERE relative_path='generated.py'").fetchone()[0] == 1

    result = index_repository(tmp_path, database_path=db_path)
    assert result.deleted >= 1
    with IndexDatabase(db_path) as database:
        assert database.connection.execute("SELECT COUNT(*) FROM files WHERE relative_path='generated.py'").fetchone()[0] == 0
        assert database.connection.execute("SELECT COUNT(*) FROM files WHERE relative_path='.uv-cache/generated.py'").fetchone()[0] == 0

