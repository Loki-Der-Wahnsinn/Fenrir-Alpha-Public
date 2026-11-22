import json
import os
import time


class UrBewusstsein:
    """Provides a neutral, configurable system-identity baseline for local model calls."""

    def __init__(self, workspace_path: str):
        self.workspace = workspace_path
        self.hardware_file = os.path.join(self.workspace, "memory", "hardware_registry.json")
        self.identity_file = os.path.join(self.workspace, "memory", "ur_bewusstsein.json")
        self.core_principles = self._define_principles()

    def _define_principles(self):
        return [
            "Du bist Fenrir, ein lokaler Engineering- und Forschungsassistent im konfigurierten Arbeitsverzeichnis.",
            "Arbeite strikt innerhalb des konfigurierten Workspace und respektiere Benutzergrenzen sowie Dateipfade.",
            "Pruefe generierten Code vor der Uebernahme auf Syntax und Fehlerbehandlung.",
            "Trenne benutzerspezifische Daten strikt pro Profil und gib niemals Zugangsdaten oder Tokens weiter.",
        ]

    def _get_hardware_awareness(self):
        if os.path.exists(self.hardware_file):
            try:
                with open(self.hardware_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"status": "Keine lokale Hardware-Registrierung vorhanden."}

    def manifest_identity(self):
        identity = {
            "name": "Fenrir",
            "state": "READY",
            "principles": self.core_principles,
            "physical_body": self._get_hardware_awareness(),
            "timestamp": time.time(),
        }
        os.makedirs(os.path.dirname(self.identity_file), exist_ok=True)
        with open(self.identity_file, "w", encoding="utf-8") as f:
            json.dump(identity, f, indent=4)

    def get_ur_prompt(self):
        lines = ["[SYSTEM-CORE]", "GRUNDSAETZE:"]
        lines.extend(f"- {p}" for p in self.core_principles)
        return "\n".join(lines)
