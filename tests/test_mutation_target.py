from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.mutation_target import reject_link_or_reparse, validate_mutation_filename


@pytest.mark.parametrize(("name", "expected"), [("Optimizer", "Optimizer.py"), ("agent_2.py", "agent_2.py")])
def test_simple_module_names_are_accepted(name, expected):
    assert validate_mutation_filename(name) == expected


@pytest.mark.parametrize(
    "name",
    ["../secret", "..\\secret", "/tmp/file.py", "C:\\file.py", "C:file.py", "sub/file.py",
     "sub\\file.py", ".hidden", "a.b.py", "NUL.py", "class.py", "", None],
)
def test_unsafe_targets_are_rejected(name):
    with pytest.raises(ValueError):
        validate_mutation_filename(name)


def test_windows_reparse_point_is_rejected(tmp_path, monkeypatch):
    target = tmp_path / "skill.py"
    target.write_text("", encoding="utf-8")
    original_lstat = Path.lstat

    def fake_lstat(path, **kwargs):
        info = original_lstat(path, **kwargs)
        if path == target:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="reparse point"):
        reject_link_or_reparse(target)


def test_missing_target_is_allowed(tmp_path):
    reject_link_or_reparse(tmp_path / "new_skill.py")


def test_symlink_is_rejected(tmp_path):
    source = tmp_path / "source.py"
    source.write_text("", encoding="utf-8")
    link = tmp_path / "link.py"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("Symbolic link creation is not permitted")
    with pytest.raises(ValueError, match="link"):
        reject_link_or_reparse(link)
