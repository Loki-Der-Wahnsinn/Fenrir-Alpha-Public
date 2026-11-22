"""Suggest graph-only import changes using structural rules and online feedback.

No source files are executed or changed. Suggestions are simulations, not
instructions to remove an import.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

if __package__:
    from .topology_features import dependency_graph, topology_features
else:
    from topology_features import dependency_graph, topology_features


MODEL_VERSION = 1
FEATURE_COUNT = 4
MAX_FEEDBACK = 2048
LEARNING_RATE = 0.1


def new_model():
    return {"version": MODEL_VERSION, "weights": [0.0] * FEATURE_COUNT, "observations": 0, "seen": []}


def validate_model(model):
    if not isinstance(model, dict) or set(model) != {"version", "weights", "observations", "seen"}:
        raise ValueError("Invalid model structure")
    if type(model["version"]) is not int or model["version"] != MODEL_VERSION:
        raise ValueError("Unsupported model version")
    weights = model["weights"]
    if not isinstance(weights, list) or len(weights) != FEATURE_COUNT:
        raise ValueError("Invalid model weights")
    if any(type(w) not in (int, float) or not math.isfinite(w) or abs(w) > 20 for w in weights):
        raise ValueError("Model weights must be finite numbers between -20 and 20")
    observations = model["observations"]
    if type(observations) is not int or observations < 0:
        raise ValueError("Invalid model observation count")
    seen = model["seen"]
    if (
        not isinstance(seen, list)
        or len(seen) > MAX_FEEDBACK
        or any(not isinstance(item, str) or len(item) != 64 or any(c not in "0123456789abcdef" for c in item) for item in seen)
        or len(set(seen)) != len(seen)
        or observations < len(seen)
    ):
        raise ValueError("Invalid model feedback history")
    return {"version": MODEL_VERSION, "weights": [float(w) for w in weights], "observations": observations, "seen": list(seen)}


def _probability(weights, features):
    value = sum(weight * feature for weight, feature in zip(weights, features))
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, value))))


def _objective(features):
    return (
        sum(len(group) for group in features["circular_import_groups"]),
        len(features["h1_births_essential"]),
    )


def _graph_hash(vertices, edges):
    data = json.dumps([sorted(vertices), sorted(edges)], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _edge_features(edge, vertices, edges, group_of, degree):
    source, target = edge
    same_group = source in group_of and group_of[source] == group_of.get(target)
    reciprocal = (target, source) in edges
    density = (degree[source] + degree[target]) / (2 * max(1, len(vertices) - 1) * 2)
    return [1.0, float(same_group), float(reciprocal), density], same_group


def _learn(model, features, label, fingerprint):
    if fingerprint in model["seen"]:
        return False
    probability = _probability(model["weights"], features)
    for i, feature in enumerate(features):
        updated = model["weights"][i] + LEARNING_RATE * (label - probability) * feature
        model["weights"][i] = max(-20.0, min(20.0, updated))
    model["observations"] += 1
    model["seen"].append(fingerprint)
    if len(model["seen"]) > MAX_FEEDBACK:
        del model["seen"][0]
    return True


def optimize(vertices, directed_edges, *, steps=3, budget=50, model=None):
    """Simulate bounded removals, preserving components and learning from outcomes."""
    if type(steps) is not int or not 1 <= steps <= 10:
        raise ValueError("steps must be an integer between 1 and 10")
    if type(budget) is not int or not 1 <= budget <= 500:
        raise ValueError("budget must be an integer between 1 and 500")
    vertices = set(vertices)
    edges = set(directed_edges)
    if any(not isinstance(vertex, str) for vertex in vertices):
        raise ValueError("vertices must be module-name strings")
    current = topology_features(vertices, edges)
    model = validate_model(new_model() if model is None else model)
    original = current
    rounds = []
    reason = "step_limit"

    for _ in range(steps):
        if not edges:
            reason = "no_edges"
            break
        group_of = {
            name: index for index, group in enumerate(current["circular_import_groups"])
            for name in group
        }
        degree = {name: 0 for name in vertices}
        for source, target in edges:
            degree[source] += 1
            degree[target] += 1

        observations_before = model["observations"]
        candidates = []
        for edge in sorted(edges):
            vector, same_group = _edge_features(edge, vertices, edges, group_of, degree)
            probability = _probability(model["weights"], vector)
            # A symbolic circular-import rule guides order; all accepted changes
            # still require an independently computed structural improvement.
            rank = probability + (0.25 if same_group else 0.0)
            candidates.append((-rank, edge, vector, probability, same_group))
        candidates.sort(key=lambda item: (item[0], item[1]))
        graph_hash = _graph_hash(vertices, edges)
        previous_objective = _objective(current)
        evaluated = 0
        learned = 0
        best = None
        for _, edge, vector, probability, same_group in candidates[:budget]:
            trial = topology_features(vertices, edges - {edge})
            trial_objective = _objective(trial)
            improves = (
                trial["h0_essential"] == current["h0_essential"]
                and trial_objective < previous_objective
            )
            fingerprint = hashlib.sha256(
                json.dumps([graph_hash, *edge], ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            learned += int(_learn(model, vector, int(improves), fingerprint))
            evaluated += 1
            if improves and (best is None or (trial_objective, edge) < (best[0], best[1])):
                best = (trial_objective, edge, trial, probability, same_group)
        if best is None:
            reason = "candidate_budget" if evaluated < len(candidates) else "local_optimum"
            rounds.append({"evaluated": evaluated, "candidates": len(candidates), "learned": learned, "selected": None})
            break
        _, selected, trial, probability, same_group = best
        rounds.append({
            "evaluated": evaluated,
            "candidates": len(candidates),
            "learned": learned,
            "selected": list(selected),
            "model_probability_before_feedback": probability,
            "model_observations_before": observations_before,
            "same_circular_group": same_group,
            "before": list(previous_objective),
            "after": list(_objective(trial)),
        })
        edges.remove(selected)
        current = trial

    return {
        "initial": original,
        "final": current,
        "rounds": rounds,
        "stop_reason": reason,
        "model": model,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Python source directory to inspect")
    parser.add_argument("--exclude", action="append", default=[], metavar="DIRECTORY")
    parser.add_argument("--steps", type=int, default=3, help="Maximum optimization rounds (1–10)")
    parser.add_argument("--budget", type=int, default=50, help="Candidates examined per round (1–500)")
    parser.add_argument("--model-in", type=Path, help="Previously saved model to read")
    parser.add_argument("--model-out", type=Path, help="New model file to create; existing files are never overwritten")
    args = parser.parse_args()
    try:
        if args.model_out is not None and args.model_out.exists():
            raise ValueError("Model output already exists; choose a new path")
        model = new_model()
        if args.model_in is not None:
            with args.model_in.open(encoding="utf-8") as file:
                model = validate_model(json.load(file))
        vertices, edges = dependency_graph(args.directory, exclude_directories=args.exclude)
        result = optimize(vertices, edges, steps=args.steps, budget=args.budget, model=model)
        result["excluded_directories"] = args.exclude
        if args.model_out is not None:
            with args.model_out.open("x", encoding="utf-8") as file:
                json.dump(result["model"], file, indent=2)
                file.write("\n")
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Analysis failed: {exc}\n")


if __name__ == "__main__":
    main()
