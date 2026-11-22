class Agent:
    """Base class for specialized cognitive lobe agents."""

    def __init__(self, name: str, role: str, instruction: str, core, model_name: str = None, keep_alive: str = "10m"):
        self.name = name
        self.role = role
        self.instruction = instruction
        self.core = core
        self.model_name = model_name
        self.keep_alive = keep_alive

    def execute(self, task_context: str, temperature: float = 0.5, max_tokens: int = -1) -> str:
        if hasattr(self.core, "core_log_func"):
            self.core.core_log_func("INFO", f"AGENT:{self.name}", f"({self.role}) fuehrt Aktion aus...")
        model = self.model_name if self.model_name else self.core.master_model
        sys_ext = (
            self.core.stealth_prompt_extension
            if model == self.core.master_model
            else self.core.master_prompt_extension
        )
        system_prompt = f"Du bist {self.name}, {self.role}.\n{self.instruction}\n{sys_ext}"
        return self.core.call_llm(
            model,
            task_context,
            system=system_prompt,
            temperature=temperature,
            keep_alive=self.keep_alive,
            max_tokens=max_tokens,
        )
