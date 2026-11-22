import pytest

from tools.module_preflight import inspect_entry


def test_static_inventory_distinguishes_local_reference_and_external(tmp_path):
    root = tmp_path / "repo"
    reference = tmp_path / "reference"
    root.mkdir()
    reference.mkdir()
    (root / "tools").mkdir()
    (root / "tools" / "present.py").write_text("", encoding="utf-8")
    (reference / "missing.py").write_text("", encoding="utf-8")
    (root / "main.py").write_text(
        "import json\nfrom tools.present import thing\n"
        "if False:\n    import missing\nimport external_package\nfrom . import sibling\n",
        encoding="utf-8",
    )
    result = inspect_entry(root, "main.py", reference)
    entries = {item["module"]: item for item in result["imports"]}
    assert entries["json"]["standard_library_top_level"] is True
    assert entries["tools.present"]["repository_candidate"] == "present"
    assert entries["missing"]["reference_candidate"] == "present"
    assert entries["missing"]["repository_candidate"] == "absent"
    assert entries["external_package"]["reference_candidate"] == "absent"
    assert result["unresolved"] == 2
    assert result["candidate_only_in_reference"] == 1
    assert result["relative_import_statements_unresolved"] == 1


@pytest.mark.parametrize("entry", ["../outside.py", ".", "missing.py"])
def test_invalid_entry_is_rejected(tmp_path, entry):
    with pytest.raises(ValueError):
        inspect_entry(tmp_path, entry)


def test_syntax_error_fails_without_executing_code(tmp_path):
    (tmp_path / "broken.py").write_text("raise Exception('not executed')\ndef broken(", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot parse"):
        inspect_entry(tmp_path, "broken.py")


def test_reference_module_is_not_executed(tmp_path):
    root, reference = tmp_path / "repo", tmp_path / "reference"
    root.mkdir()
    reference.mkdir()
    (root / "main.py").write_text("import risky\n", encoding="utf-8")
    (reference / "risky.py").write_text("raise RuntimeError('must not run')\n", encoding="utf-8")
    result = inspect_entry(root, "main.py", reference)
    assert result["candidate_only_in_reference"] == 1


def test_linked_candidates_are_reported_as_skipped(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "main.py").write_text("import linked\n", encoding="utf-8")
    (root / "linked.py").write_text("", encoding="utf-8")
    monkeypatch.setattr("tools.module_preflight._is_link_or_reparse", lambda path: path.name == "linked.py")
    result = inspect_entry(root, "main.py")
    assert result["imports"][0]["repository_candidate"] == "link_skipped"
    assert result["unresolved"] == 1


def test_module_prefix_that_is_a_file_is_not_a_package(tmp_path):
    (tmp_path / "main.py").write_text("import not_a_package.child\n", encoding="utf-8")
    (tmp_path / "not_a_package").write_text("", encoding="utf-8")
    result = inspect_entry(tmp_path, "main.py")
    assert result["imports"][0]["repository_candidate"] == "absent"
