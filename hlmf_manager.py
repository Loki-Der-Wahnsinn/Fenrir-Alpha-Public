import json
import math
import os
import time
import requests


def cosine_similarity(vec1, vec2):
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class HLMF_Manager:
    """Hierarchical Latent Memory Fabric (L1/L2/L3) using configurable local Ollama embeddings."""

    def __init__(self, workspace: str, ollama_url: str = None):
        self.workspace = workspace
        self.ollama_url = ollama_url or os.environ.get("FENRIR_OLLAMA_URL", "http://127.0.0.1:11434")
        self.embedding_model = os.environ.get("FENRIR_EMBEDDING_MODEL", "nomic-embed-text")
        self.l3_dir = os.path.join(workspace, "memory", "hlmf_l3")
        self.l3_file = os.path.join(self.l3_dir, "episodic_l3.json")
        self.l1_cache = {}
        self.l2_latent = []
        self._load_l3()

    def get_embedding(self, text: str) -> list:
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.embedding_model, "prompt": text},
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json().get("embedding", [])
        except Exception:
            pass
        return []

    def _load_l3(self):
        if os.path.exists(self.l3_file):
            try:
                with open(self.l3_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.l2_latent = data.get("l2_latent", [])
            except Exception:
                self.l2_latent = []

    def _save_l3(self):
        os.makedirs(self.l3_dir, exist_ok=True)
        with open(self.l3_file, "w", encoding="utf-8") as f:
            json.dump({"l2_latent": self.l2_latent}, f, indent=2)

    def garbage_collection(self):
        current_time = time.time()
        survivors = []
        for item in self.l2_latent:
            age_hours = max(0.0, (current_time - item.get("last_used", current_time)) / 3600.0)
            item["decay_score"] = item.get("decay_score", 1.0) * (0.95 ** age_hours)
            if item["decay_score"] > 0.1:
                survivors.append(item)
        if len(survivors) < len(self.l2_latent):
            self.l2_latent = survivors
            self._save_l3()

    def store(self, concept: str, content: str):
        self.l1_cache[concept] = content
        new_vec = self.get_embedding(content)
        if not new_vec:
            return
        max_sim = 0.0
        for item in self.l2_latent:
            if item["concept"] == concept:
                max_sim = max(max_sim, cosine_similarity(new_vec, item.get("vector", [])))
        if 1.0 - max_sim > 0.3:
            self.l2_latent.append(
                {
                    "vector": new_vec,
                    "concept": concept,
                    "content_preview": content[:100],
                    "last_used": time.time(),
                    "decay_score": 1.0,
                }
            )
            self._save_l3()

    def retrieve(self, query: str, top_k: int = 3) -> list:
        if query in self.l1_cache:
            return [{"concept": query, "content": self.l1_cache[query], "source": "L1"}]
        q_vec = self.get_embedding(query)
        if not q_vec:
            return []
        results = []
        for item in self.l2_latent:
            sim = cosine_similarity(q_vec, item.get("vector", []))
            if sim > 0.4:
                item["last_used"] = time.time()
                item["decay_score"] = min(1.0, item.get("decay_score", 1.0) + 0.2)
                results.append((sim, item))
        results.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "concept": r[1]["concept"],
                "preview": r[1]["content_preview"],
                "similarity": r[0],
                "source": "L2",
            }
            for r in results[:top_k]
        ]
