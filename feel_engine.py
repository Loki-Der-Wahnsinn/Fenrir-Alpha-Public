import json
import math
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "memory", "feel_state.json")

HAB_WINDOW = 300.0
HAB_RECOVER = 3600.0
OPP_TAU = 1800.0
HORM_TAU = 7200.0


class FeelEngine:
    def __init__(self, state_file: str = STATE_FILE):
        self.state_file = state_file
        self.channels = {}
        self.serotonin = 0.5
        self.stress = 0.0
        self._last = time.time()
        self._load()

    def _load(self):
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.channels = d.get("channels", {})
            self.serotonin = float(d.get("serotonin", 0.5))
            self.stress = float(d.get("stress", 0.0))
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"channels": self.channels, "serotonin": self.serotonin, "stress": self.stress, "ts": time.time()},
                    f,
                )
        except Exception:
            pass

    def _ch(self, name):
        ch = self.channels.get(name)
        if not ch:
            ch = {"gain": 1.0, "last": 0.0, "opp": 0.0}
            self.channels[name] = ch
        return ch

    def feel(self, channel, intensity):
        now = time.time()
        ch = self._ch(channel)
        dt = max(0.0, now - float(ch.get("last", 0.0)))
        ch["gain"] = min(1.0, ch["gain"] + dt / HAB_RECOVER)
        ch["opp"] = ch["opp"] * math.exp(-dt / OPP_TAU)
        if dt < HAB_WINDOW and ch.get("last", 0.0) > 0:
            ch["gain"] = max(0.15, ch["gain"] * 0.7)
        felt = max(0.0, min(1.0, intensity)) * ch["gain"]
        reward = max(0.0, felt - ch["opp"])
        ch["opp"] = min(1.0, ch["opp"] + felt * 0.35)
        ch["last"] = now
        self._save()
        return round(reward, 4), {"gain": round(ch["gain"], 3), "opponent": round(ch["opp"], 3)}

    def hormones(self, body):
        now = time.time()
        dt = min(3600.0, max(0.0, now - self._last))
        self._last = now
        k = dt / HORM_TAU
        try:
            temp = float(body.get("temperatur_c", 0) or 0)
            gpu = float(body.get("gpu_last_pct", 0) or 0)
        except Exception:
            temp, gpu = 0.0, 0.0
        flow = 1.0 if (10.0 <= gpu <= 85.0 and temp < 80.0) else 0.0
        fever = 1.0 if temp > 85.0 else 0.0
        self.serotonin = min(1.0, max(0.0, self.serotonin + (flow * 0.2 - 0.02) * k))
        self.stress = min(1.0, max(0.0, self.stress + (fever * 0.5 - 0.05) * k))
        self._save()
        return {"serotonin": round(self.serotonin, 3), "stress": round(self.stress, 3)}

    def mood(self):
        return {"serotonin": round(self.serotonin, 3), "stress": round(self.stress, 3)}
