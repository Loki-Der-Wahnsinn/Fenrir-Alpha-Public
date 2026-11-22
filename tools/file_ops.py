import os
from pathlib import Path
from typing import Any, Dict
from .base_tool import BaseTool


def _resolve_workspace_path(filepath: str, workspace_root: str) -> Path:
    """Resolve a path strictly inside workspace_root."""
    root = Path(workspace_root).resolve()
    candidate = Path(filepath)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Path outside workspace is not allowed: {filepath}")
    return resolved


class FileWriteTool(BaseTool):
    def __init__(self, workspace_root: str = None):
        self.workspace_root = workspace_root or os.getcwd()

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return "Writes text or code to a file inside the configured workspace."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Workspace-relative file path."},
                "content": {"type": "string", "description": "Text content to write."},
            },
            "required": ["filepath", "content"],
        }

    def execute(self, filepath: str, content: str, **kwargs) -> Any:
        try:
            target = _resolve_workspace_path(filepath, self.workspace_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Datei {target} erfolgreich geschrieben."
        except Exception as e:
            return f"Fehler beim Schreiben der Datei: {str(e)}"


class FileReadTool(BaseTool):
    def __init__(self, workspace_root: str = None):
        self.workspace_root = workspace_root or os.getcwd()

    @property
    def name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return "Reads a text file from the configured workspace."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Workspace-relative file path."},
                "encoding": {"type": "string", "description": "Optional encoding (default utf-8)."},
            },
            "required": ["filepath"],
        }

    def execute(self, filepath: str, encoding: str = "utf-8", **kwargs) -> Any:
        try:
            if "path" in kwargs and not filepath:
                filepath = kwargs["path"]
            target = _resolve_workspace_path(filepath, self.workspace_root)
            if not target.is_file():
                return f"Fehler: Datei {filepath} existiert nicht."
            return target.read_text(encoding=encoding, errors="replace")
        except Exception as e:
            return f"Fehler beim Lesen der Datei: {str(e)}"
