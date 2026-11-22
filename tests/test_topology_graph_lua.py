import importlib
import random
from pathlib import Path

import pytest

from tools.topology_features import topology_features

lupa = pytest.importorskip("lupa", reason="Lua comparison tests require the optional lupa package")


@pytest.fixture(scope="module", params=["lua54", "lua55"])
def lua(request):
    try:
        backend = importlib.import_module(f"lupa.{request.param}")
    except ImportError:
        pytest.skip(f"Optional Lupa runtime {request.param} is not available")
    runtime = backend.LuaRuntime(unpack_returned_tuples=True)
    source = (Path(__file__).resolve().parents[1] / "tools" / "topology_graph.lua").read_text(
        encoding="utf-8"
    )
    return runtime, runtime.execute(source)["analyze"], backend.LuaError


def lua_features(lua, vertices, edges):
    runtime, analyze, _ = lua
    result = analyze(runtime.table_from(list(vertices)), runtime.table_from([list(e) for e in edges], recursive=True))
    return {
        "modules": result["modules"],
        "directed_imports": result["directed_imports"],
        "undirected_edges": result["undirected_edges"],
        "reciprocal_pairs": result["reciprocal_pairs"],
        "h0_deaths": [result["h0_deaths"][i] for i in range(1, len(result["h0_deaths"]) + 1)],
        "h0_essential": result["h0_essential"],
        "h1_births_essential": [
            result["h1_births_essential"][i] for i in range(1, len(result["h1_births_essential"]) + 1)
        ],
        "circular_import_groups": [
            [result["circular_import_groups"][i][j]
             for j in range(1, len(result["circular_import_groups"][i]) + 1)]
            for i in range(1, len(result["circular_import_groups"]) + 1)
        ],
        "components_by_scale": {str(i): result["components_by_scale"][str(i)] for i in range(3)},
    }


def test_lua_features_match_python_for_random_directed_graphs(lua):
    rng = random.Random(422)
    for _ in range(200):
        vertices = {f"m{i}" for i in range(rng.randrange(12))}
        edges = {
            (a, b) for a in vertices for b in vertices if a != b and rng.random() < 0.25
        }
        assert lua_features(lua, vertices, edges) == topology_features(vertices, edges)


def test_deep_chain_and_duplicate_entries(lua):
    vertices = [f"m{i}" for i in range(1500)]
    edges = list(zip(vertices, vertices[1:]))
    result = lua_features(lua, vertices + [vertices[0]], edges + [edges[0]])
    assert result == topology_features(set(vertices), set(edges))


def test_invalid_edges_and_sparse_arrays_fail(lua):
    runtime, analyze, lua_error = lua
    vertices = runtime.table_from(["a"])
    for edges in ([["a", "missing"]], [["a", "a"]], [["a"]]):
        with pytest.raises(lua_error):
            analyze(vertices, runtime.table_from(edges, recursive=True))
    sparse = runtime.table_from({1: "a", 3: "b"})
    with pytest.raises(lua_error, match="dense array"):
        analyze(sparse, runtime.table())
