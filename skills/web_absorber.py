import json
import os
import random
import threading
import time
import urllib.parse
import urllib.request


class WebAbsorber(threading.Thread):
    """Optional background thread fetching public Wikipedia summaries for research."""

    def __init__(self, core_reference):
        super().__init__(daemon=True)
        self.core = core_reference
        self.active = True
        self.history_file = os.path.join(
            getattr(self.core, "workspace", "."), "memory", "web_absorber_history.json"
        )
        self.seen_topics = set()
        self._load_history()
        self.search_topics = [
            "Software architecture",
            "Persistent homology",
            "Topological data analysis",
            "Neuro-symbolic AI",
            "Artificial neural network",
            "Evolutionary algorithm",
            "Reinforcement learning",
            "Distributed computing",
            "Network topology",
            "Static program analysis",
        ]

    def add_target(self, target: str):
        if target and target not in self.search_topics:
            self.search_topics.append(target)
            return f"Target '{target}' hinzugefuegt."
        return f"Target '{target}' existiert bereits."

    def run(self):
        while self.active:
            time.sleep(random.randint(60, 180))
            try:
                topic = random.choice(self.search_topics)
                if topic in self.seen_topics:
                    continue
                url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(topic)}"
                req = urllib.request.Request(url, headers={"User-Agent": "Fenrir-Research/1.0"})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode("utf-8"))
                title = data.get("title", "Unknown")
                extract = data.get("extract", "")
                if extract and getattr(self.core, "vector_cortex", None) is not None:
                    self.core.vector_cortex.store_memory(
                        text=f"[WEB-WISSEN]: {title} - {extract[:400]}",
                        context=f"Web Absorber ({topic})",
                        dopamine=min(1.0, self.core.brain_state.get("dopamine_level", 0.5) + 0.1),
                    )
                    self.seen_topics.add(topic)
                    self._save_history()
            except Exception:
                pass

    def stop(self):
        self.active = False

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.seen_topics = set(json.load(f))
            except Exception:
                pass

    def _save_history(self):
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(list(self.seen_topics), f)
        except Exception:
            pass
