import ast
import json
import os


def extract_class_manifest(file_path: str) -> dict:
    """Parses a Python file and extracts class, inheritance, and method metadata."""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            node = ast.parse(f.read())
    except Exception as e:
        print(f"Graph Generator Fehler beim Lesen von {file_path}: {e}")
        return {}

    manifest = {}
    for item in node.body:
        if isinstance(item, ast.ClassDef):
            inherits = [base.id for base in item.bases if isinstance(base, ast.Name)]
            methods = [n.name for n in item.body if isinstance(n, ast.FunctionDef)]
            docstring = ast.get_docstring(item)
            manifest[item.name] = {
                "file": file_path,
                "inherits_from": inherits[0] if inherits else None,
                "methods": methods,
                "docstring": docstring[:200] if docstring else None,
                "dependencies": inherits,
            }
    return manifest


def update_brain_state(file_path: str, brain_state_path: str = "memory/brain_state.json"):
    """Integrates the extracted manifest atomically into brain_state.json."""
    new_manifest = extract_class_manifest(file_path)
    if not new_manifest:
        return
    try:
        with open(brain_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {"architecture_graph": {}}

    state.setdefault("architecture_graph", {}).update(new_manifest)
    os.makedirs(os.path.dirname(os.path.abspath(brain_state_path)), exist_ok=True)
    tmp_path = brain_state_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)
    os.replace(tmp_path, brain_state_path)
