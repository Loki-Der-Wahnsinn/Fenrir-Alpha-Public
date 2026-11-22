import json
import math
import os
import time


class VectorCortex:
    """Episodic vector memory using an optional local GGUF embedder."""

    def __init__(self, workspace: str, ollama_url: str = None):
        self.workspace = workspace
        self.db_dir = os.path.join(workspace, "memory", "episodic_db")
        self.metadata_file = os.path.join(self.db_dir, "metadata.json")
        self.embeddings = []
        self.metadata = []
        self.embedder = None

        model_path = os.path.join(self.workspace, "brain_weights", "all-MiniLM-L6-v2.Q4_K_M.gguf")
        if os.path.exists(model_path):
            try:
                from llama_cpp import Llama

                self.embedder = Llama(
                    model_path=model_path,
                    n_gpu_layers=0,
                    n_ctx=0,
                    embedding=True,
                    verbose=False,
                )
            except Exception:
                self.embedder = None

        self._load_db()

    def _load_db(self):
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.metadata = data.get("metadata", [])
                self.embeddings = data.get("embeddings", [])
            except Exception:
                self.metadata = []
                self.embeddings = []

    def _save_db(self):
        os.makedirs(self.db_dir, exist_ok=True)
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump({"metadata": self.metadata, "embeddings": self.embeddings}, f, indent=2)

    def get_embedding(self, text: str) -> list:
        if self.embedder is None:
            return []
        try:
            resp = self.embedder.create_embedding(text)
            return resp["data"][0]["embedding"]
        except Exception:
            return []

    def store_memory(self, text: str, context: str, dopamine: float):
        vector = self.get_embedding(text)
        if not vector:
            return
        self.embeddings.append(vector)
        self.metadata.append(
            {
                "text": text,
                "context": context,
                "dopamine": dopamine,
                "timestamp": time.time(),
            }
        )
        self._save_db()

    def retrieve_memory(self, query: str, top_k: int = 3) -> list:
        if not self.embeddings:
            return []
        q_vec = self.get_embedding(query)
        if not q_vec:
            return []
        norm_q = math.sqrt(sum(x * x for x in q_vec))
        if norm_q == 0.0:
            return []
        scored = []
        for idx, vec in enumerate(self.embeddings):
            norm_v = math.sqrt(sum(x * x for x in vec))
            if norm_v == 0.0 or len(vec) != len(q_vec):
                continue
            sim = sum(a * b for a, b in zip(q_vec, vec)) / (norm_q * norm_v)
            if sim > 0.4:
                mem = self.metadata[idx].copy()
                mem["similarity"] = float(sim)
                scored.append(mem)
        scored.sort(key=lambda m: m["similarity"], reverse=True)
        return scored[:top_k]
