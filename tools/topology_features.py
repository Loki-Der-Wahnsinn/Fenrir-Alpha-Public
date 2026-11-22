"""Read-only topology of static Python imports.

The undirected dependency graph is treated as a one-dimensional simplicial
complex: reciprocal imports enter at scale 1, other imports at scale 2.
This is not a clique complex; graph cycles therefore never die.
"""

import argparse
import ast
import json
import os
import stat
import tokenize
from pathlib import Path


SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}


def _is_link_or_reparse(path):
    info = path.lstat()
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _module_name(root, path):
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def dependency_graph(root, *, exclude_directories=(), on_parse_error=None):
    """Return local imports; optionally report and exclude files that cannot be parsed."""
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    excluded = set()
    for raw in exclude_directories:
        relative = Path(raw)
        if relative.anchor or not relative.parts or ".." in relative.parts:
            raise ValueError(f"Excluded directory must be relative to the analysis root: {raw}")
        candidate = root
        for part in relative.parts:
            candidate = candidate / part
            if _is_link_or_reparse(candidate):
                raise ValueError(f"Excluded directory must not contain links: {raw}")
        if not candidate.is_dir():
            raise ValueError(f"Excluded directory does not exist: {raw}")
        excluded.add(relative)

    def raise_walk_error(error):
        raise error

    modules = {}
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=raise_walk_error):
        dirs[:] = sorted(
            name for name in dirs
            if name not in SKIP_DIRS and not name.startswith(".")
            and not _is_link_or_reparse(Path(directory) / name)
            and (Path(directory) / name).relative_to(root) not in excluded
        )
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix != ".py" or _is_link_or_reparse(path):
                continue
            module = _module_name(root, path)
            if module:
                if module in modules:
                    raise ValueError(f"Ambiguous module name: {module}")
                modules[module] = path

    edges = set()
    invalid_modules = set()
    for source, path in sorted(modules.items()):
        try:
            with tokenize.open(path) as file:
                tree = ast.parse(file.read(), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            if on_parse_error is None:
                raise ValueError(f"Cannot parse {path}: {exc}") from exc
            on_parse_error(path, exc)
            invalid_modules.add(source)
            continue
        package = source if path.name == "__init__.py" else source.rpartition(".")[0]
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = package.split(".") if package else []
                    if node.level > len(parts):
                        continue
                    base = ".".join(parts[:len(parts) - node.level + 1])
                    base = ".".join(filter(None, (base, node.module)))
                else:
                    base = node.module or ""
                names = [base] + [f"{base}.{alias.name}" for alias in node.names if alias.name != "*"]
            for name in names:
                if name in modules and name != source:
                    edges.add((source, name))
    valid_modules = set(modules) - invalid_modules
    return valid_modules, {
        (source, target) for source, target in edges
        if source in valid_modules and target in valid_modules
    }


def _circular_import_groups(vertices, edges):
    outgoing = {vertex: [] for vertex in vertices}
    incoming = {vertex: [] for vertex in vertices}
    for source, target in edges:
        outgoing[source].append(target)
        incoming[target].append(source)
    for neighbors in (*outgoing.values(), *incoming.values()):
        neighbors.sort()

    visited = set()
    finishing_order = []
    for vertex in sorted(vertices):
        if vertex in visited:
            continue
        visited.add(vertex)
        stack = [(vertex, iter(outgoing[vertex]))]
        while stack:
            current, neighbors = stack[-1]
            neighbor = next(neighbors, None)
            if neighbor is None:
                finishing_order.append(current)
                stack.pop()
            elif neighbor not in visited:
                visited.add(neighbor)
                stack.append((neighbor, iter(outgoing[neighbor])))

    visited.clear()
    groups = []
    for vertex in reversed(finishing_order):
        if vertex in visited:
            continue
        visited.add(vertex)
        group = []
        stack = [vertex]
        while stack:
            current = stack.pop()
            group.append(current)
            for neighbor in incoming[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        if len(group) > 1:
            groups.append(sorted(group))
    return sorted(groups)


def topology_features(vertices, directed_edges):
    """Calculate H0 intervals and essential H1 births for the import graph."""
    vertices = set(vertices)
    directed_edges = set(directed_edges)
    for source, target in directed_edges:
        if source not in vertices or target not in vertices or source == target:
            raise ValueError("Edges must connect two distinct known vertices")

    parent = {vertex: vertex for vertex in vertices}
    size = {vertex: 1 for vertex in vertices}

    def find(vertex):
        while parent[vertex] != vertex:
            parent[vertex] = parent[parent[vertex]]
            vertex = parent[vertex]
        return vertex

    undirected = {tuple(sorted(edge)) for edge in directed_edges}
    weighted = sorted(
        (1 if (a, b) in directed_edges and (b, a) in directed_edges else 2, a, b)
        for a, b in undirected
    )
    h0_deaths = []
    h1_births = []
    for scale, a, b in weighted:
        first, second = find(a), find(b)
        if first == second:
            h1_births.append(scale)
            continue
        if size[first] < size[second]:
            first, second = second, first
        parent[second] = first
        size[first] += size[second]
        h0_deaths.append(scale)

    components = len(vertices) - len(h0_deaths)
    return {
        "modules": len(vertices),
        "directed_imports": len(directed_edges),
        "undirected_edges": len(undirected),
        "reciprocal_pairs": sum(scale == 1 for scale, _, _ in weighted),
        "h0_deaths": h0_deaths,
        "h0_essential": components,
        "h1_births_essential": h1_births,
        "circular_import_groups": _circular_import_groups(vertices, directed_edges),
        "components_by_scale": {
            "0": len(vertices),
            "1": len(vertices) - h0_deaths.count(1),
            "2": components,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Python source directory to inspect")
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="DIRECTORY",
        help="Exclude an existing directory relative to the source root; may be repeated",
    )
    args = parser.parse_args()
    try:
        vertices, edges = dependency_graph(args.directory, exclude_directories=args.exclude)
        result = topology_features(vertices, edges)
        if args.exclude:
            result["excluded_directories"] = args.exclude
        print(json.dumps(result, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Analysis failed: {exc}\n")


if __name__ == "__main__":
    main()
