import gc
import os

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

from ur_bewusstsein import UrBewusstsein


def core_log_gateway(level: str, category: str, message: str):
    print(f"[{level}] [{category}] {message}")


class GGUFGateway:
    """Optional local GGUF inference gateway using user-configured model paths."""

    def __init__(self, config_path: str = "config.json", workspace: str = None):
        self.workspace = workspace or os.path.dirname(os.path.abspath(__file__))
        self.ur_bewusstsein = UrBewusstsein(self.workspace)
        self.ur_prompt = self.ur_bewusstsein.get_ur_prompt()
        self.current_model = None
        self.current_model_path = ""
        self.loaded_models_pool = {}

    def _load_model(self, model_path: str, n_ctx: int = 4096):
        if not Llama:
            raise RuntimeError("llama-cpp-python is not installed")
        if model_path in self.loaded_models_pool:
            self.current_model = self.loaded_models_pool[model_path]
            self.current_model_path = model_path
            return

        cpu_cores = 4
        try:
            import psutil

            cpu_cores = min(4, psutil.cpu_count(logical=False) or 4)
            if psutil.virtual_memory().percent > 95.0:
                for k in list(self.loaded_models_pool):
                    if k != model_path:
                        del self.loaded_models_pool[k]
                gc.collect()
        except Exception:
            pass

        gpu_layers = int(os.environ.get("FENRIR_DYNAMIC_LAYERS", "0"))
        self.current_model = Llama(
            model_path=model_path,
            n_ctx=min(n_ctx, 4096) if n_ctx else 4096,
            n_gpu_layers=gpu_layers,
            n_threads=cpu_cores,
            verbose=False,
        )
        self.loaded_models_pool[model_path] = self.current_model
        self.current_model_path = model_path

    def call_llm(
        self,
        model: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.5,
        keep_alive: str = "10m",
        num_ctx: int = 4096,
        response_format=None,
    ) -> str:
        if not Llama:
            return "ERROR: llama-cpp-python not installed."
        if not model or not os.path.exists(model):
            return "ERROR: Model file not found."
        try:
            self._load_model(model, n_ctx=num_ctx)
            full_system = f"{self.ur_prompt}\n\n{system}".strip()
            response = self.current_model.create_chat_completion(
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=1024,
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            core_log_gateway("ERROR", "GGUF", f"Inference failed: {e}")
            return f"ERROR: {str(e)}"
