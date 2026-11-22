"""Statically inventory an entry point's imports without importing its code."""

import argparse
import ast
import json
from pathlib import Path
import sys
import tokenize

if __package__:
    from .topology_features import _is_link_or_reparse
else:
    from topology_features import _is_link_or_reparse


def _relative_path(root, relative):
    relative = Path(relative)
    if relative.anchor or not relative.parts or ".." in relative.parts:
        raise ValueError(f"Path must be relative to the root: {relative}")
    path = root
    for part in relative.parts:
        path = path / part
        try:
            if _is_link_or_reparse(path):
                return None, "link_skipped"
        except (FileNotFoundError, NotADirectoryError):
            return None, "absent"
    return path, "present"


def _module_candidate(root, module):
    parts = module.split(".")
    file_path = Path(*parts).with_suffix(".py")
    package_path = Path(*parts)
    file_candidate, file_status = _relative_path(root, file_path)
    if file_candidate is not None and file_candidate.is_file():
        return "present"
    package_candidate, package_status = _relative_path(root, package_path)
    if package_candidate is not None and package_candidate.is_dir():
        return "present"
    if "link_skipped" in (file_status, package_status):
        return "link_skipped"
    return "absent"


def inspect_entry(root, entry, reference=None):
    """Report imports present as source in each root; availability is not safety."""
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Repository root must be a directory")
    if reference is not None:
        reference = Path(reference).resolve(strict=True)
        if not reference.is_dir():
            raise ValueError("Reference root must be a directory")
    if not hasattr(sys, "stdlib_module_names"):
        raise RuntimeError("Python 3.10 or later is required for standard-library classification")
    source, source_status = _relative_path(root, entry)
    if source is None:
        raise ValueError(f"Entry point unavailable: {source_status}")
    if not source.is_file():
        raise ValueError("Entry point is not a file")
    try:
        with tokenize.open(source) as file:
            tree = ast.parse(file.read(), filename=str(source))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ValueError(f"Cannot parse entry point: {exc}") from exc

    modules = set()
    relative_imports = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_imports += 1
            elif node.module:
                modules.add(node.module)

    imports = []
    for module in sorted(modules):
        record = {
            "module": module,
            "standard_library_top_level": module.split(".", 1)[0] in sys.stdlib_module_names,
            "repository_candidate": _module_candidate(root, module),
        }
        if reference is not None:
            record["reference_candidate"] = _module_candidate(reference, module)
        imports.append(record)

    return {
        "imports": imports,
        "relative_import_statements_unresolved": relative_imports,
        "unresolved": sum(
            not row["standard_library_top_level"] and row["repository_candidate"] != "present"
            for row in imports
        ),
        "candidate_only_in_reference": (
            sum(
                not row["standard_library_top_level"]
                and row["repository_candidate"] == "absent"
                and row["reference_candidate"] == "present"
                for row in imports
            )
            if reference is not None else None
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--entry", required=True, help="Python file relative to the repository root")
    parser.add_argument("--reference", type=Path, help="Optional second source tree to compare")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_entry(args.root, args.entry, args.reference), indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Module inspection failed: {exc}\n")


if __name__ == "__main__":
    main()
