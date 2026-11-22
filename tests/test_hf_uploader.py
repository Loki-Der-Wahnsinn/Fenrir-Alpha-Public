import pytest
from pathlib import Path
from types import SimpleNamespace

import hf_uploader


def test_preview_does_not_upload(tmp_path, monkeypatch, capsys):
    (tmp_path / "readme.md").write_text("reviewed", encoding="utf-8")
    monkeypatch.setattr(hf_uploader, "HfApi", lambda **kwargs: pytest.fail("unexpected network client"))
    monkeypatch.setattr(
        "sys.argv",
        ["hf_uploader.py", "--folder", str(tmp_path), "--repo-id", "user/repo", "--file", "readme.md"],
    )
    hf_uploader.main()
    assert "Preview only; nothing uploaded." in capsys.readouterr().out


def test_upload_requires_explicit_token_and_checks_all_files_before_connecting(tmp_path, monkeypatch):
    (tmp_path / "safe.txt").write_text("reviewed", encoding="utf-8")
    monkeypatch.setattr(hf_uploader, "HfApi", lambda **kwargs: pytest.fail("unexpected network client"))
    with pytest.raises(ValueError, match="HF_TOKEN"):
        hf_uploader.upload_fenrir_to_hf(tmp_path, "user/repo", ["safe.txt"], "")
    with pytest.raises(ValueError, match="Private file"):
        hf_uploader.upload_fenrir_to_hf(tmp_path, "user/repo", ["safe.txt", ".env"], "example-token")


def test_upload_sends_only_selected_files_to_specified_repository(tmp_path, monkeypatch):
    (tmp_path / "safe.txt").write_text("reviewed", encoding="utf-8")
    (tmp_path / "not_selected.txt").write_text("private", encoding="utf-8")
    calls = []

    class FakeApi:
        def __init__(self, *, token):
            assert token == "example-token"

        def upload_file(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(hf_uploader, "HfApi", FakeApi)
    hf_uploader.upload_fenrir_to_hf(tmp_path, "user/repo", ["safe.txt"], "example-token")
    assert calls == [{
        "path_or_fileobj": str(tmp_path / "safe.txt"),
        "path_in_repo": "safe.txt",
        "repo_id": "user/repo",
        "repo_type": "model",
    }]


@pytest.mark.parametrize("name", ["../private.txt", ".git/config", "memory/notes.md", "projects/notes.md", "api_key.txt"])
def test_private_and_escaping_paths_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        hf_uploader.select_files(tmp_path, [name])


def test_symbolic_link_is_rejected(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("private", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symbolic link creation is not permitted")
    with pytest.raises(ValueError, match="Symlinks"):
        hf_uploader.select_files(tmp_path, ["link.txt"])


@pytest.mark.parametrize("linked_part", ["ancestor", "selected_directory"])
def test_windows_reparse_points_are_rejected(tmp_path, monkeypatch, linked_part):
    source = tmp_path / "source"
    selected_directory = source / "nested"
    selected_directory.mkdir(parents=True)
    (selected_directory / "file.txt").write_text("data", encoding="utf-8")
    target = tmp_path if linked_part == "ancestor" else selected_directory
    original_lstat = Path.lstat

    def fake_lstat(path, **kwargs):
        info = original_lstat(path, **kwargs)
        if path == target:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="reparse points"):
        hf_uploader.select_files(source, ["nested/file.txt"])
