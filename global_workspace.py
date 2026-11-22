import json
import os
import time


class GlobalWorkspace:
    """Global Workspace coordinator for selecting the highest-priority signal."""

    def __init__(self, workspace_path=None):
        if workspace_path is None:
            workspace_path = os.path.dirname(os.path.abspath(__file__))
        self.workspace_path = workspace_path
        self.raw_dir = os.path.join(workspace_path, "memory", "raw_pitches")
        self.clean_file = os.path.join(workspace_path, "memory", "clean_workspace.json")
        self.current_conscious_thought = None

    def receive_pitch(self, agent_name, content, intensity):
        os.makedirs(self.raw_dir, exist_ok=True)
        pitch = {
            "agent": agent_name,
            "content": content,
            "intensity": float(intensity),
            "timestamp": time.time(),
        }
        filename = os.path.join(self.raw_dir, f"pitch_{agent_name}_{time.time()}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(pitch, f, indent=4)

    def resolve_workspace(self, llm_callback=None):
        if not os.path.exists(self.clean_file):
            return None
        try:
            with open(self.clean_file, "r", encoding="utf-8") as f:
                pitches = json.load(f)
        except Exception:
            return None

        if not pitches:
            return None

        pitches.sort(key=lambda x: x["intensity"], reverse=True)
        winner = pitches[0]

        if len(pitches) > 1 and (winner["intensity"] - pitches[1]["intensity"] < 10.0) and llm_callback:
            prompt = (
                "Antworte ausschliesslich auf Deutsch in Textform (kein Code).\n"
                "Welcher dieser beiden Gedanken ist fuer Systemstabilitaet und Codequalitaet wichtiger?\n"
                f"Gedanke A ({winner['agent']}): {winner['content']}\n"
                f"Gedanke B ({pitches[1]['agent']}): {pitches[1]['content']}\n"
                "Antworte mit 'A' oder 'B' und einer kurzen Begruendung."
            )
            decision = llm_callback(prompt)
            if decision and "B" in decision.split(".")[0].upper():
                winner = pitches[1]

        self.current_conscious_thought = winner
        with open(self.clean_file, "w", encoding="utf-8"):
            pass
        return winner

    def broadcast(self):
        return self.current_conscious_thought


workspace = GlobalWorkspace()
