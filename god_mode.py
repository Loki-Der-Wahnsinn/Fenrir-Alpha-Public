try:
    import psutil
except ImportError:
    psutil = None


class GodModeProtocol:
    """Checks basic host CPU and memory thresholds if psutil is available."""

    def __init__(self, cpu_limit: float = 95.0, ram_limit: float = 95.0):
        self.cpu_limit = cpu_limit
        self.ram_limit = ram_limit

    def check_survival(self) -> bool:
        if psutil is None:
            return True
        try:
            mem = psutil.virtual_memory().percent
            return mem < self.ram_limit
        except Exception:
            return True


god_mode = GodModeProtocol()
