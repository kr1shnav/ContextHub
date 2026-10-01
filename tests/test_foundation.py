from context_hub.project import init_project, project_status


def test_init_creates_metadata(tmp_path):
    directory, has_git = init_project(tmp_path)
    assert directory == tmp_path / ".context-hub"
    assert has_git is False
    assert project_status(tmp_path)["project_root"] == str(tmp_path)

