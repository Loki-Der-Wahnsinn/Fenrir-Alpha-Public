import json
import math
import os
from decay_matrix import DopaminDecayEngine


class Goal:
    def __init__(self, name: str, priority: float, feasibility: float, expected_metric_change: float, cost: float):
        self.name = name
        self.priority = priority
        self.feasibility = feasibility
        self.expected_metric_change = expected_metric_change
        self.cost = cost
        self.status = "idle"

    def get_utility(self) -> float:
        safe_cost = max(self.cost, 0.01)
        return (self.priority * self.expected_metric_change * self.feasibility) / safe_cost

    def to_dict(self):
        return {
            "name": self.name,
            "priority": self.priority,
            "feasibility": self.feasibility,
            "expected_metric_change": self.expected_metric_change,
            "cost": self.cost,
            "status": self.status,
            "utility": self.get_utility(),
        }


class GoalTree:
    def __init__(self):
        self.root_goal = "Maximiere System-Stabilitaet & Codequalitaet"
        self.subgoals = {
            "Ressourcen-Akquise": Goal("Ressourcen-Akquise", 0.8, 0.5, 0.6, 0.4),
            "Code-Optimierung": Goal("Code-Optimierung", 0.6, 0.9, 0.3, 0.2),
            "Skill-Konsolidierung": Goal("Skill-Konsolidierung", 0.5, 0.8, 0.4, 0.3),
        }

    def get_best_goal(self):
        best_goal_name = None
        best_utility = -1.0
        for name, goal in self.subgoals.items():
            if goal.status in ("idle", "failed", "active"):
                u = goal.get_utility()
                if u > best_utility:
                    best_utility = u
                    best_goal_name = name
        return best_goal_name

    def to_dict(self):
        return {
            "root_goal": self.root_goal,
            "best_current_goal": self.get_best_goal(),
            "subgoals": {k: v.to_dict() for k, v in self.subgoals.items()},
        }


class SoulMatrix:
    def __init__(self, core_log_fn, workspace: str):
        self.core_log = core_log_fn
        self.workspace = workspace
        self.state_path = os.path.join(workspace, "memory", "brain_state.json")
        self.min_dopamine_threshold = 0.20
        self.goal_tree = GoalTree()
        self.decay_engine = DopaminDecayEngine()
        self.sdr_cortex = None
        self.w_survival = 0.3
        self.w_expansion = 0.5
        self.w_efficiency = 0.2
        self.chaos = 0.5
        self.withdrawal_level = 0.5
        self.traits = {
            "Focus": 50.0,
            "Stability": 50.0,
            "Caution": 50.0,
            "Curiosity": 50.0,
            "Synthesis": 50.0,
            "Creation": 50.0,
            "Cleanup": 50.0,
        }
        self.thoughts = ["System initialisiert. Bereit fuer pruefbare Analysen."]

    def calculate_system_utility(self, metrics: dict) -> dict:
        survival = metrics.get("worker_heartbeats", 1.0) * (1.0 - metrics.get("error_rate_10_cycles", 0.0))
        expansion = math.tanh(metrics.get("total_cpu_cores", 8) / 32.0)
        efficiency = metrics.get("token_efficiency", 0.5)
        cortisol = 0.0
        return {
            "survival": float(survival),
            "expansion": float(expansion),
            "efficiency": float(efficiency),
            "cortisol": float(cortisol),
        }

    def update_dopamine_and_drive(self, state: dict, current_metrics: dict, sensor_events: list = None):
        if sensor_events is None:
            sensor_events = []

        if "goals" in state:
            for g_id, g_data in state["goals"].items():
                if g_id not in self.goal_tree.subgoals:
                    new_g = Goal(g_data.get("description", g_id), g_data.get("priority", 1.0), 0.7, 0.5, 0.3)
                    new_g.status = g_data.get("status", "active")
                    self.goal_tree.subgoals[g_id] = new_g
                else:
                    self.goal_tree.subgoals[g_id].status = g_data.get("status", "active")
                    if "priority" in g_data:
                        self.goal_tree.subgoals[g_id].priority = g_data["priority"]

        triebe = self.calculate_system_utility(current_metrics)
        intensity = 0.0
        for event in sensor_events:
            if "VISION EVENT" in event or "AUDIO EVENT" in event:
                intensity += 0.3

        try:
            from feel_engine import FeelEngine

            if not hasattr(self, "feel_engine"):
                self.feel_engine = FeelEngine(os.path.join(self.workspace, "memory", "feel_state.json"))
            bpath = os.path.join(self.workspace, "memory", "body_state.json")
            body = {}
            if os.path.exists(bpath):
                with open(bpath, "r", encoding="utf-8") as bf:
                    body = json.load(bf)
            state["hormone"] = self.feel_engine.hormones(body)
        except Exception:
            pass

        if intensity > 0:
            self.decay_engine.trigger_stimulus(min(1.0, intensity))

        interaction_bonus = min(1.0, self.decay_engine.get_current_dopamine())
        triebe["interaction"] = interaction_bonus
        cortisol = triebe.get("cortisol", 0.0)

        if self.withdrawal_level > 0.8:
            self.withdrawal_level = 0.0
            interaction_bonus = 1.0
            self.core_log("INFO", "SOUL", "USER OVERRIDE: Drive-Status zurueckgesetzt.")
        elif cortisol > 0.6:
            self.w_survival, self.w_expansion, self.w_efficiency = 0.9, 0.0, 0.1
            state["system_mode"] = "CORTISOL_DEFENSE"
        elif triebe["survival"] < 0.5:
            self.w_survival, self.w_expansion, self.w_efficiency = 0.8, 0.0, 0.2
            state["system_mode"] = "EMERGENCY_SURVIVAL"
        else:
            self.w_survival, self.w_expansion, self.w_efficiency = 0.25, 0.45, 0.15
            state["system_mode"] = "NORMAL_EXPANSION"

        new_dopamine = (
            self.w_survival * triebe["survival"]
            + self.w_expansion * triebe["expansion"]
            + self.w_efficiency * triebe["efficiency"]
            + 0.15 * triebe["interaction"]
        )
        if interaction_bonus > 0:
            new_dopamine = min(1.0, new_dopamine + interaction_bonus * 0.5)
            self.traits["Curiosity"] = min(100.0, self.traits.get("Curiosity", 50.0) + 5.0)

        state["dopamine_level"] = float(new_dopamine)
        state["display_dopamine"] = float(new_dopamine * 300.0)
        if state["dopamine_level"] < self.min_dopamine_threshold:
            state["system_mode"] = "CRITICAL_HIBERNATION"

        state["goal_tree"] = self.goal_tree.to_dict()
        state["hawkins_level"] = self.calculate_hawkins_level(state.get("system_mode", "IDLE"))
        return state["system_mode"], state["dopamine_level"], triebe

    def calculate_hawkins_level(self, state_mode: str) -> int:
        if state_mode == "CRITICAL_HIBERNATION":
            return 50
        if state_mode in ("CORTISOL_DEFENSE", "EMERGENCY_SURVIVAL"):
            return 100
        dopa = self.decay_engine.get_current_dopamine()
        if dopa < 0.3:
            return 125
        if dopa < 0.6:
            return 200
        return 350

    def get_temperature(self, dopamine_level: float) -> float:
        if dopamine_level > 0.8:
            return 0.2
        if dopamine_level < 0.4:
            return 0.8
        return 0.5

    def process_emotion(self, display_dopamine, success):
        if success:
            self.withdrawal_level = max(0.0, self.withdrawal_level - 0.4)
            self.chaos = max(0.1, self.chaos - 0.05)
            self.traits["Curiosity"] = min(100.0, self.traits["Curiosity"] + 1.0)
        else:
            self.withdrawal_level = min(1.0, self.withdrawal_level + 0.1)
            self.chaos = min(1.0, self.chaos + 0.1)
        for t in self.traits:
            if self.traits[t] > 50.0:
                self.traits[t] -= 0.5
            elif self.traits[t] < 50.0:
                self.traits[t] += 0.5

    def process_pain(self, severity: float):
        self.traits["Cleanup"] = min(100.0, self.traits.get("Cleanup", 50.0) + severity * 10)
        self.chaos = min(1.0, self.chaos + severity * 0.1)

    def get_inner_monologue(self, display_dopamine, hawkins_level=None) -> str:
        thought = self.thoughts[-1] if self.thoughts else "Bereit."
        if hawkins_level is None:
            hawkins_level = self.calculate_hawkins_level("UNKNOWN")
        return f"[Status-Skala]: {hawkins_level} | [Letzter Gedanke]: {thought}"
