import json
import math
import os
import re
import sqlite3
import time
import zlib
from datetime import datetime
from typing import Any, Dict, List, Optional


def _tokenize_terms(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r"[a-z0-9äöüß_]{2,}", text.lower())


def _hash_embed_384(text: str) -> List[float]:
    vec = [0.0] * 384
    if not text:
        return vec
    low = text.lower()[:6000]
    for w in _tokenize_terms(low):
        h = zlib.crc32(w.encode("utf-8"))
        idx = h % 384
        sign = 1.0 if ((h >> 16) & 1) == 0 else -1.0
        vec[idx] += sign * 2.0
        if len(w) >= 4:
            for i in range(len(w) - 3):
                ng = w[i : i + 4]
                h2 = zlib.crc32(ng.encode("utf-8"))
                idx2 = h2 % 384
                sign2 = 1.0 if ((h2 >> 16) & 1) == 0 else -1.0
                vec[idx2] += sign2 * 0.5
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-9:
        inv = 1.0 / norm
        vec = [v * inv for v in vec]
    return vec


def _cosine_sim(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class _SQLiteCollection:
    def __init__(self, store: "VectorMemory", name: str):
        self._store = store
        self.name = name

    def count(self) -> int:
        try:
            with self._store._connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM vector_docs WHERE collection = ?",
                    (self.name,),
                ).fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    def upsert(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ):
        if not documents:
            return
        now = datetime.now().isoformat()
        if ids is None:
            ids = [f"{self.name}_{int(time.time() * 1000)}_{i}" for i in range(len(documents))]
        if metadatas is None:
            metadatas = [{} for _ in documents]

        rows = []
        for doc_id, doc, meta in zip(ids, documents, metadatas):
            rows.append((self.name, str(doc_id), str(doc or ""), json.dumps(meta or {}, ensure_ascii=False), now))

        with self._store._connect() as conn:
            for col, did, doc_str, meta_json, ts in rows:
                old = conn.execute(
                    "SELECT rowid FROM vector_docs WHERE collection = ? AND doc_id = ?",
                    (col, did),
                ).fetchone()
                if old:
                    rowid = old[0]
                    conn.execute(
                        "UPDATE vector_docs SET document = ?, metadata_json = ?, updated_at = ? WHERE rowid = ?",
                        (doc_str, meta_json, ts, rowid),
                    )
                    if self._store._has_fts:
                        conn.execute("DELETE FROM vector_docs_fts WHERE rowid = ?", (rowid,))
                        conn.execute(
                            "INSERT INTO vector_docs_fts(rowid, collection, document) VALUES (?, ?, ?)",
                            (rowid, col, doc_str),
                        )
                else:
                    cur = conn.execute(
                        "INSERT INTO vector_docs(collection, doc_id, document, metadata_json, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (col, did, doc_str, meta_json, ts),
                    )
                    if self._store._has_fts:
                        conn.execute(
                            "INSERT INTO vector_docs_fts(rowid, collection, document) VALUES (?, ?, ?)",
                            (cur.lastrowid, col, doc_str),
                        )
            conn.commit()

    def add(self, documents: List[str], metadatas: Optional[List[Dict[str, Any]]] = None, ids: Optional[List[str]] = None):
        self.upsert(documents=documents, metadatas=metadatas, ids=ids)

    def query(self, query_texts: List[str], n_results: int = 3) -> Dict[str, List[List[Any]]]:
        all_ids, all_docs, all_metas, all_dists = [], [], [], []
        n_req = max(1, int(n_results or 3))

        with self._store._connect() as conn:
            for qtext in (query_texts or [""]):
                candidates = []
                seen_rowids = set()
                terms = _tokenize_terms(qtext)[:12]
                if self._store._has_fts and terms:
                    fts_expr = " OR ".join(f'"{t}"' for t in terms)
                    try:
                        fts_rows = conn.execute(
                            """
                            SELECT d.rowid, d.doc_id, d.document, d.metadata_json
                            FROM vector_docs_fts f
                            JOIN vector_docs d ON d.rowid = f.rowid
                            WHERE f.vector_docs_fts MATCH ? AND d.collection = ?
                            ORDER BY bm25(vector_docs_fts)
                            LIMIT ?
                            """,
                            (fts_expr, self.name, max(64, n_req * 16)),
                        ).fetchall()
                        for r in fts_rows:
                            seen_rowids.add(r[0])
                            candidates.append(r)
                    except Exception:
                        pass

                if len(candidates) < max(32, n_req * 8):
                    recent_rows = conn.execute(
                        """
                        SELECT rowid, doc_id, document, metadata_json
                        FROM vector_docs
                        WHERE collection = ?
                        ORDER BY rowid DESC
                        LIMIT ?
                        """,
                        (self.name, max(80, n_req * 16)),
                    ).fetchall()
                    for r in recent_rows:
                        if r[0] not in seen_rowids:
                            seen_rowids.add(r[0])
                            candidates.append(r)

                q_vec = _hash_embed_384(qtext)
                scored = []
                for idx, (_, did, doc, mjson) in enumerate(candidates):
                    sim = _cosine_sim(q_vec, _hash_embed_384(doc))
                    fts_bonus = 0.12 / (1.0 + idx * 0.15) if idx < 32 and terms else 0.0
                    scored.append((sim + fts_bonus, did, doc, mjson))

                scored.sort(key=lambda x: x[0], reverse=True)
                q_ids, q_docs, q_metas, q_dists = [], [], [], []
                for score, did, doc, mjson in scored[:n_req]:
                    q_ids.append(did)
                    q_docs.append(doc)
                    try:
                        q_metas.append(json.loads(mjson) if mjson else {})
                    except Exception:
                        q_metas.append({})
                    q_dists.append(round(max(0.0, 1.0 - score), 4))

                all_ids.append(q_ids)
                all_docs.append(q_docs)
                all_metas.append(q_metas)
                all_dists.append(q_dists)

        return {"ids": all_ids, "documents": all_docs, "metadatas": all_metas, "distances": all_dists}


class VectorMemory:
    """Multi-process SQLite WAL & FTS5 local vector memory."""

    def __init__(self, workspace: Optional[str] = None):
        if not workspace:
            workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.workspace = workspace
        self.sqlite_path = os.path.join(workspace, "memory", "fenrir_vector_store.sqlite3")
        os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)
        self._has_fts = True
        self._init_schema()
        self.collection = _SQLiteCollection(self, "evolution_skills")
        self.dream_collection = _SQLiteCollection(self, "fenrir_dreams")
        self.knowledge_collection = _SQLiteCollection(self, "fenrir_knowledge")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path, timeout=20.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vector_docs (
                    collection TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    document TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    UNIQUE(collection, doc_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vector_docs_col ON vector_docs(collection)")
            try:
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS vector_docs_fts USING fts5(collection, document)")
            except Exception:
                self._has_fts = False
            conn.commit()

    def store_skill(self, cycle: int, skill_code: str, summary: str):
        try:
            self.collection.upsert(
                documents=[summary],
                metadatas=[{"cycle": cycle, "code": skill_code, "timestamp": datetime.now().isoformat()}],
                ids=[f"cycle_{cycle}"],
            )
        except Exception:
            pass

    def find_similar_skills(self, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        try:
            cnt = self.collection.count()
            if cnt == 0:
                return []
            res = self.collection.query(query_texts=[query_text], n_results=min(n_results, cnt))
            return [
                {"summary": res["documents"][0][i], "metadata": res["metadatas"][0][i]}
                for i in range(len(res["documents"][0]))
            ]
        except Exception:
            return []
