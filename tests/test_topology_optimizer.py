import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.topology_optimizer import new_model, optimize, validate_model


def test_optimizer_removes_simulated_cycle_without_disconnecting_graph():
    vertices = {"a", "b"}
    edges = {("a", "b"), ("b", "a")}
    model = new_model()
    result = optimize(vertices, edges, steps=1, budget=10, model=model)
    assert result["initial"]["circular_import_groups"] == [["a", "b"]]
    assert result["final"]["circular_import_groups"] == []
    assert result["final"]["h0_essential"] == result["initial"]["h0_essential"]
    assert result["rounds"][0]["selected"] in [["a", "b"], ["b", "a"]]
    assert result["rounds"][0]["same_circular_group"] is True
    assert result["rounds"][0]["model_observations_before"] == 0
    assert result["rounds"][0]["model_probability_before_feedback"] == 0.5
    assert result["model"]["observations"] == 2
    assert any(weight != 0 for weight in result["model"]["weights"])
    assert model == new_model()
    assert edges == {("a", "b"), ("b", "a")}

    repeated = optimize(vertices, edges, steps=1, budget=10, model=result["model"])
    assert repeated["model"]["observations"] == 2
    assert repeated["rounds"][0]["learned"] == 0


def test_optimizer_can_reduce_an_undirected_cycle_without_directed_cycle():
    result = optimize(
        {"a", "b", "c"}, {("a", "b"), ("a", "c"), ("b", "c")}, steps=1
    )
    assert result["initial"]["h1_births_essential"] == [2]
    assert result["final"]["h1_births_essential"] == []
    assert result["final"]["h0_essential"] == 1
    assert result["rounds"][0]["after"] < result["rounds"][0]["before"]


def test_bridges_are_never_removed_and_budget_exhaustion_is_reported():
    vertices = {"a", "b", "c"}
    edges = {("a", "b"), ("b", "c")}
    limited = optimize(vertices, edges, budget=1)
    assert limited["stop_reason"] == "candidate_budget"
    assert limited["rounds"][0]["selected"] is None
    assert limited["final"] == limited["initial"]

    exhaustive = optimize(vertices, edges, budget=10)
    assert exhaustive["stop_reason"] == "local_optimum"
    assert exhaustive["final"] == exhaustive["initial"]


def test_optimistic_model_cannot_override_connectivity_rule():
    model = new_model()
    model["weights"] = [20, 20, 20, 20]
    result = optimize({"a", "b", "c"}, {("a", "b"), ("b", "c")}, model=model)
    assert result["rounds"][0]["selected"] is None
    assert result["final"]["h0_essential"] == 1


@pytest.mark.parametrize("kwargs", [{"steps": 0}, {"steps": 11}, {"budget": 0}, {"budget": 501}])
def test_limits_are_enforced(kwargs):
    with pytest.raises(ValueError):
        optimize({"a"}, set(), **kwargs)


@pytest.mark.parametrize("invalid", [
    {},
    {"version": True, "weights": [0, 0, 0, 0], "observations": 0, "seen": []},
    {"version": 1, "weights": [float("nan"), 0, 0, 0], "observations": 0, "seen": []},
    {"version": 1, "weights": [0, 0, 0, 0], "observations": 0, "seen": ["x" * 64]},
])
def test_invalid_model_is_rejected(invalid):
    with pytest.raises(ValueError):
        validate_model(invalid)


def test_cli_persists_feedback_without_overwriting_existing_files(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("import b\n", encoding="utf-8")
    (project / "b.py").write_text("import a\n", encoding="utf-8")
    model1 = tmp_path / "first.json"
    model2 = tmp_path / "second.json"
    script = Path(__file__).resolve().parents[1] / "tools" / "topology_optimizer.py"
    command = [sys.executable, str(script), str(project), "--steps", "1", "--budget", "10"]
    first = subprocess.run(
        command + ["--model-out", str(model1)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True,
    )
    output = json.loads(first.stdout)
    assert output["model"]["observations"] == 2
    assert json.loads(model1.read_text(encoding="utf-8")) == output["model"]

    second = subprocess.run(
        command + ["--model-in", str(model1), "--model-out", str(model2)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True,
    )
    assert json.loads(second.stdout)["model"]["observations"] == 2
    before = model1.read_bytes()
    failed = subprocess.run(
        command + ["--model-out", str(model1)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    assert failed.returncode != 0
    assert model1.read_bytes() == before
    assert (project / "a.py").read_text(encoding="utf-8") == "import b\n"
    assert (project / "b.py").read_text(encoding="utf-8") == "import a\n"
