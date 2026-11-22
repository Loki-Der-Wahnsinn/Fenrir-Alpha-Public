import time


class DopaminDecayEngine:
    """Simulates exponential decay and stimulus updates for a bounded drive signal."""

    def __init__(self, base_level: float = 0.5, decay_rate: float = 0.05):
        self.base_level = base_level
        self.decay_rate = decay_rate
        self._current = base_level
        self._last_update = time.time()
        self._peak = base_level

    def _apply_decay(self):
        now = time.time()
        elapsed = now - self._last_update
        self._last_update = now
        delta = self._current - self.base_level
        self._current = self.base_level + delta * (1.0 - self.decay_rate) ** elapsed
        self._current = max(0.0, min(1.0, self._current))

    def trigger_stimulus(self, intensity: float = 0.5):
        self._apply_decay()
        boost = intensity * (1.0 - self._current)
        self._current = min(1.0, self._current + boost)
        self._peak = max(self._peak, self._current)

    def get_current_dopamine(self) -> float:
        self._apply_decay()
        return round(self._current, 4)

    def get_peak(self) -> float:
        return round(self._peak, 4)

    def reset(self):
        self._current = self.base_level
        self._peak = self.base_level
        self._last_update = time.time()

    def inject_synthetic(self, level: float = 1.0):
        self._apply_decay()
        self._current = min(1.0, max(0.0, level))
        self._peak = max(self._peak, self._current)
        self._last_update = time.time()

    def __repr__(self):
        return (
            f"DopaminDecayEngine(current={self.get_current_dopamine():.3f}, "
            f"base={self.base_level}, decay_rate={self.decay_rate})"
        )
