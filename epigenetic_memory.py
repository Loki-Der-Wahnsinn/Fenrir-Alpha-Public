import json
import os
import time


class EpigeneticMemory:
    """Stores learned workflow patterns inside the local workspace."""

    def __init__(self, workspace: str = None):
        base_root = workspace or os.path.dirname(os.path.abspath(__file__))
        self._base = os.path.join(base_root, "memory")
        self._file = os.path.join(self._base, "epigenetic_markers.json")
        self._markers = self._load()

    def _load(self) -> dict:
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "evolution_level": 1,
            "core_directives": [
                "Ausgaben praezise als valides JSON strukturieren.",
                "Vorhandene sichere Werkzeuge bevorzugen.",
                "Neue Module erst im Sandbox-Evaluator pruefen.",
                "Lokale HTTP-Dienste an 127.0.0.1 binden und Host/Origin pruefen.",
                "Nur belegte Ergebnisse als verified melden; niemals Tokens oder Zugangsdaten einbetten.",
            ],
            "learned_patterns": [],
            "cycle_count": 0,
        }

    def _save(self):
        try:
            os.makedirs(self._base, exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._markers, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add_pattern(self, pattern: str):
        self._markers.setdefault("learned_patterns", []).append(
            {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "pattern": pattern}
        )
        self._markers["learned_patterns"] = self._markers["learned_patterns"][-20:]
        self._save()

    def get_god_prompt_additions(self) -> str:
        directives = self._markers.get("core_directives", [])
        patterns = self._markers.get("learned_patterns", [])
        level = self._markers.get("evolution_level", 1)
        lines = [f"[EPIGENETISCHES GEDAECHTNIS - Stufe {level}]:"]
        if directives:
            lines.append("[KERN-DIREKTIVEN]:")
            for d in directives:
                lines.append(f"  - {d}")
        if patterns:
            lines.append("[LETZTE MUSTER]:")
            for p in patterns[-3:]:
                lines.append(f"  - [{p['ts']}] {p['pattern']}")
        lines.append("")
        return "\n".join(lines)


epigenetics = EpigeneticMemory()
