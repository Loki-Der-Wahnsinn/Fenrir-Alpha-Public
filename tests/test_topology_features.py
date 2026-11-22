import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools.topology_features import _is_link_or_reparse, dependency_graph, topology_features


def test_filtration_and_cycles():
    result = topology_features(
        {"a", "b", "c", "isolated"},
        {("a", "b"), ("b", "a"), ("b", "c"), ("c", "a")},
    )
    assert result["h0_deaths"] == [1, 2]
    assert result["h0_essential"] == 2
    assert result["h1_births_essential"] == [2]
    assert result["circular_import_groups"] == [["a", "b", "c"]]
    assert result["components_by_scale"] == {"0": 4, "1": 3, "2": 2}


def test_undirected_graph_cycle_is_not_always_a_circular_import():
    result = topology_features(
        {"a", "b", "c", "d", "e"},
        {("a", "b"), ("a", "c"), ("b", "c"), ("d", "e"), ("e", "d")},
    )
    assert result["h1_births_essential"] == [2]
    assert result["circular_import_groups"] == [["d", "e"]]


def test_deep_dependency_chain_does_not_exhaust_recursion_limit():
    vertices = {str(i) for i in range(1500)}
    edges = {(str(i), str(i + 1)) for i in range(1499)}
    assert topology_features(vertices, edges)["circular_import_groups"] == []


def test_graph_edges_must_reference_distinct_vertices():
    with pytest.raises(ValueError):
        topology_features({"a"}, {("a", "missing")})
    with pytest.raises(ValueError):
        topology_features({"a"}, {("a", "a")})


def test_static_imports_and_relative_packages(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "a.py").write_text(
        "from . import b\nimport external\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "b.py").write_text(
        "from . import a\n", encoding="utf-8"
    )
    (tmp_path / "outside.py").write_text("import pkg.a\n", encoding="utf-8")
    vertices, edges = dependency_graph(tmp_path)
    assert vertices == {"pkg", "pkg.a", "pkg.b", "outside"}
    assert edges == {("pkg.a", "pkg"), ("pkg.a", "pkg.b"),
                     ("pkg.b", "pkg"), ("pkg.b", "pkg.a"),
                     ("outside", "pkg.a")}


def test_invalid_python_is_reported(tmp_path):
    (tmp_path / "broken.py").write_text("def broken(", encoding="utf-8")
    with pytest.raises(ValueError, match="broken.py"):
        dependency_graph(tmp_path)


def test_explicit_partial_analysis_reports_and_excludes_invalid_modules(tmp_path):
    (tmp_path / "broken.py").write_text("def broken(", encoding="utf-8")
    (tmp_path / "valid.py").write_text("import broken\n", encoding="utf-8")
    errors = []
    vertices, edges = dependency_graph(tmp_path, on_parse_error=lambda path, error: errors.append((path, error)))
    assert vertices == {"valid"}
    assert edges == set()
    assert len(errors) == 1
    assert errors[0][0].name == "broken.py"
    assert isinstance(errors[0][1], SyntaxError)


def test_exclude_directory_omits_only_selected_subtree(tmp_path):
    (tmp_path / "memory" / "quarantine").mkdir(parents=True)
    (tmp_path / "memory" / "quarantine" / "bad.py").write_text("def broken(", encoding="utf-8")
    (tmp_path / "memory" / "other.py").write_text("value = 1", encoding="utf-8")
    (tmp_path / "main.py").write_text("import memory.other", encoding="utf-8")
    vertices, edges = dependency_graph(tmp_path, exclude_directories=["memory/quarantine"])
    assert vertices == {"main", "memory.other"}
    assert edges == {("main", "memory.other")}


def test_cli_reports_explicit_exclusions(tmp_path):
    (tmp_path / "excluded").mkdir()
    (tmp_path / "excluded" / "bad.py").write_text("def broken(", encoding="utf-8")
    (tmp_path / "main.py").write_text("value = 1", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "tools" / "topology_features.py"
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path), "--exclude", "excluded"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True,
    )
    output = json.loads(result.stdout)
    assert output["modules"] == 1
    assert output["excluded_directories"] == ["excluded"]


@pytest.mark.parametrize("excluded", ["..", ".", "not-present"])
def test_invalid_excluded_directory_fails(tmp_path, excluded):
    with pytest.raises((OSError, ValueError)):
        dependency_graph(tmp_path, exclude_directories=[excluded])


def test_inaccessible_directory_is_reported(tmp_path, monkeypatch):
    def failing_walk(root, *, followlinks, onerror):
        onerror(PermissionError("directory unavailable"))

    monkeypatch.setattr("tools.topology_features.os.walk", failing_walk)
    with pytest.raises(PermissionError, match="directory unavailable"):
        dependency_graph(tmp_path)


def test_windows_reparse_points_are_not_followed(monkeypatch):
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda self: SimpleNamespace(st_mode=0, st_file_attributes=0x400),
    )
    assert _is_link_or_reparse(Path("junction"))
