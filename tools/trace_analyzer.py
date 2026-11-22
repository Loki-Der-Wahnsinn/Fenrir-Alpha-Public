import os
import json
from datetime import datetime, timedelta


class TraceAnalyzer:
    def __init__(self, workspace: str, core_log_callback):
        self.workspace = workspace
        self.core_log = core_log_callback
        self.log_file = os.path.join(workspace, "memory", "core_log.jsonl")

    def extract_recent_friction(self, minutes_back: int = 60) -> str:
        if not os.path.exists(self.log_file):
            return "Keine Logs vorhanden."

        cutoff_time = datetime.now() - timedelta(minutes=minutes_back)
        friction_points = []

        try:
            with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        entry_time = datetime.fromisoformat(entry["timestamp"])
                        if entry_time >= cutoff_time and entry["level"] in ["WARN", "ERROR", "CRITICAL"]:
                            friction_points.append(
                                f"[{entry['level']}] {entry.get('category', '')}: {entry['message']}"
                            )
                    except Exception:
                        continue
        except Exception as e:
            self.core_log("ERROR", "TRACE", f"Fehler beim Lesen der Logs: {e}")

        if not friction_points:
            return "Keine nennenswerte Reibung in den letzten Zyklen."

        return "\n".join(friction_points[-30:])
