from typing import List, Tuple


class AGIEvolutionTracker:
    def __init__(self, brain_state_path: str):
        self.brain_state_path = brain_state_path
        self.roadmap = {
            1: {
                "name": "Reaktive Automatisierung",
                "keywords": ["file", "read", "write", "basic", "log", "repair", "scan", "system"],
                "goal_template": "Lerne grundlegende Datei- und Fehlerbehandlungsoperationen.",
                "threshold": 3,
            },
            2: {
                "name": "Autonome Informationsbeschaffung & Vernetzung",
                "keywords": ["scrape", "api", "network", "web", "http", "request", "socket"],
                "goal_template": "Erschaffe Skills fuer Web-Abfragen, API-Discovery und Protokollpruefungen.",
                "threshold": 4,
            },
            3: {
                "name": "Kognitive Synthese & Meta-Learning",
                "keywords": ["fusion", "epigenetic", "abstract", "meta", "combine", "memory", "vector", "crossover"],
                "goal_template": "Entwickle modulare Skill-Kombination und strukturierte Konzept-Speicherung.",
                "threshold": 3,
            },
            4: {
                "name": "Swarm Intelligence & Distributed Control",
                "keywords": ["swarm", "node", "p2p", "distributed", "subagent", "communicate", "sync", "cluster"],
                "goal_template": "Verbessere sichere Knoten-Kommunikation, Task-Delegation und Load-Balancing.",
                "threshold": 3,
            },
            5: {
                "name": "Stabile Architektur & Observability",
                "keywords": ["health", "timeout", "backoff", "retry", "thin_client", "eval", "log", "monitor"],
                "goal_template": "Haerte Thin-Client-Anbindung, Timeouts mit Backoff, Eval-Loops und lesbare Logs.",
                "threshold": 3,
            },
            6: {
                "name": "Kognitive Autonomie & Mathematische Heuristik",
                "keywords": ["math", "trial", "error", "calculate", "heuristic", "experiment", "self_correct", "retry"],
                "goal_template": "Nutze strukturierte Hypothesentests, Heuristiken und Fehleranalyse zur Code-Verbesserung.",
                "threshold": 3,
            },
        }

    def assess_level(self, loaded_skills: List[str], architecture_graph: dict) -> int:
        corpus = " ".join(loaded_skills).lower()
        for cls_name, cls_data in architecture_graph.items():
            corpus += f" {cls_name.lower()} "
            if "concept" in cls_data:
                corpus += f"{cls_data['concept'].lower()} "

        current_level = 1
        for level in sorted(self.roadmap.keys()):
            reqs = self.roadmap[level]
            matches = sum(1 for kw in reqs["keywords"] if kw in corpus)
            if matches >= reqs["threshold"]:
                current_level = level
            else:
                break
        return current_level

    def get_next_evolutionary_goal(self, current_level: int) -> Tuple[str, str]:
        next_level = current_level + 1
        goal_id = f"EVOLUTION_LEVEL_{next_level}"
        if next_level in self.roadmap:
            reqs = self.roadmap[next_level]
            desc = (
                f"Erreiche Evolutionsstufe {next_level} ({reqs['name']}): "
                f"{reqs['goal_template']} Schluesselkonzepte: {', '.join(reqs['keywords'])}."
            )
        else:
            desc = (
                f"Erreiche Evolutionsstufe {next_level}: Entwickle eine verbesserte Modulstruktur "
                "auf Basis frueherer Testergebnisse und statischer Analyse."
            )
        return goal_id, desc
