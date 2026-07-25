"""
In-process hybrid store — Elasticsearch replacement
====================================================
Drop-in local search backend so the whole system runs in a single
container (HuggingFace Spaces / any host) with no external database.

Why this exists:
  The original pipeline used Elasticsearch for BM25 + kNN. ES is a
  separate stateful service and cannot run inside a one-container
  HuggingFace Space. At this corpus size (3,497 chunks) an in-process
  store is not just adequate — it is faster and far more portable.

Design:
  - BM25   -> rank_bm25.BM25Okapi over tokenized chunk texts (pure Python)
  - Vector -> brute-force cosine via a single NumPy matmul.
              3,497 x 768 float32 = ~11 MB. One (N,768)·(768,) matmul
              scores the whole corpus in <5 ms — no ANN index needed,
              no native wheel (FAISS) to build.
  - Embeddings are precomputed once by build_index.py and shipped as
    data/index/embeddings.npy so runtime never re-embeds the corpus.

The public methods return the SAME hit-dict shape the old ES functions
returned, so src/retrieve/hybrid.py needs only its search calls rewired
— RRF fusion, multi-query fusion, graph expansion and reranking are
untouched.
"""

import os
import json
import re
from pathlib import Path

import numpy as np

try:
    from rank_bm25 import BM25Okapi
except ImportError as exc:  # pragma: no cover - dependency guard
    raise ImportError(
        "rank-bm25 is required for the in-process store. "
        "Install it with: pip install rank-bm25"
    ) from exc


# ── Paths ────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_FILE   = os.getenv(
    "CHUNKS_FILE",
    str(_PROJECT_ROOT / "data" / "processed" / "okf_chunks.jsonl"),
)
INDEX_DIR     = Path(os.getenv("INDEX_DIR", str(_PROJECT_ROOT / "data" / "index")))
EMB_FILE      = INDEX_DIR / "embeddings.npy"
IDS_FILE      = INDEX_DIR / "chunk_ids.json"


# ── Tokenizer (approximates the ES legal_analyzer) ───────────────────────────
# ES used: standard tokenizer -> lowercase -> English stop -> snowball stem.
# We reproduce lowercase + stopword removal + light Porter/Snowball stemming.
# snowballstemmer is pure-Python (no native build); it is optional — if it is
# not installed we fall back to unstemmed tokens (slightly lower BM25 recall).

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in",
    "into", "is", "it", "no", "not", "of", "on", "or", "such", "that", "the",
    "their", "then", "there", "these", "they", "this", "to", "was", "will",
    "with",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

try:
    import snowballstemmer

    _STEMMER = snowballstemmer.stemmer("english")

    def _stem_many(tokens):
        return _STEMMER.stemWords(tokens)
except Exception:  # pragma: no cover - optional dependency
    _STEMMER = None

    def _stem_many(tokens):
        return tokens


def tokenize(text: str) -> list:
    """Lowercase -> alnum tokens -> drop stopwords -> stem."""
    raw = _TOKEN_RE.findall(text.lower())
    kept = [t for t in raw if t not in _STOPWORDS]
    return _stem_many(kept)


# ── Store singleton ──────────────────────────────────────────────────────────

_store = None


def get_store():
    global _store
    if _store is None:
        _store = HybridStore()
    return _store


class HybridStore:
    """Loads chunks + precomputed embeddings, builds BM25 in memory."""

    def __init__(self):
        self.chunks = self._load_chunks()                 # list[dict] (no embedding)
        self.chunk_ids = [c["chunk_id"] for c in self.chunks]
        self.id_to_pos = {cid: i for i, cid in enumerate(self.chunk_ids)}

        # BM25 (rebuilt at load — cheap for 3.5k docs, ~0.5s)
        print(f"[store] Building BM25 over {len(self.chunks)} chunks…")
        tokenized_corpus = [tokenize(c.get("text", "")) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

        # Embeddings (precomputed by build_index.py)
        self.embeddings = self._load_embeddings()
        print(f"[store] Ready — {len(self.chunks)} chunks, "
              f"embeddings shape={None if self.embeddings is None else self.embeddings.shape}")

    # ── loaders ──────────────────────────────────────────────────────────────

    def _load_chunks(self) -> list:
        if not os.path.exists(CHUNKS_FILE):
            raise FileNotFoundError(
                f"Chunk file not found: {CHUNKS_FILE}. "
                "Run the ingestion step (src/ingest/parse.py) first."
            )
        chunks = []
        with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    rec.pop("embedding", None)  # never keep vectors on the source dict
                    chunks.append(rec)
        return chunks

    def _load_embeddings(self):
        """Load the precomputed, L2-normalized embedding matrix aligned to chunk order."""
        if not EMB_FILE.exists() or not IDS_FILE.exists():
            print(f"[store] WARNING: embeddings not found at {EMB_FILE}. "
                  "Vector search disabled until build_index.py is run.")
            return None

        emb = np.load(EMB_FILE).astype(np.float32)

        # Re-align rows to the current chunk order using the saved id list.
        with open(IDS_FILE, "r", encoding="utf-8") as f:
            saved_ids = json.load(f)

        if saved_ids == self.chunk_ids:
            matrix = emb
        else:
            pos_by_id = {cid: i for i, cid in enumerate(saved_ids)}
            try:
                order = [pos_by_id[cid] for cid in self.chunk_ids]
            except KeyError as exc:
                raise ValueError(
                    "Embedding index is stale — a chunk_id has no embedding. "
                    "Rebuild with: python src/index/build_index.py"
                ) from exc
            matrix = emb[order]

        # Ensure unit norm so a plain dot product == cosine similarity.
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    # ── search ───────────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self.chunks)

    def doc_type_counts(self) -> dict:
        counts = {}
        for c in self.chunks:
            counts[c.get("doc_type", "unknown")] = counts.get(c.get("doc_type", "unknown"), 0) + 1
        return counts

    def bm25_search(self, query: str, top_k: int = 50) -> list:
        """BM25 keyword search. Returns ES-shaped hit dicts (rank_bm25, score_bm25, chunk_id, source)."""
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)

        # Top-k by score (descending); skip zero-score docs (no term overlap).
        top_idx = np.argsort(scores)[::-1][:top_k]
        hits = []
        rank = 0
        for i in top_idx:
            if scores[i] <= 0:
                break
            rank += 1
            hits.append({
                "rank_bm25":  rank,
                "score_bm25": float(scores[i]),
                "chunk_id":   self.chunk_ids[i],
                "source":     self.chunks[i],
            })
        return hits

    def vector_search(self, query_vector, top_k: int = 50) -> list:
        """
        Dense cosine search via brute-force matmul.
        query_vector: 1-D list/np.ndarray, ALREADY L2-normalized (BGE normalize_embeddings=True).
        Returns ES-shaped hit dicts (rank_vector, score_vector, chunk_id, source).
        """
        if self.embeddings is None:
            return []
        q = np.asarray(query_vector, dtype=np.float32)
        n = np.linalg.norm(q)
        if n > 0:
            q = q / n

        scores = self.embeddings @ q                      # (N,) cosine similarities

        k = min(top_k, scores.shape[0])
        # argpartition for the top-k, then sort just those k.
        part = np.argpartition(scores, -k)[-k:]
        top_idx = part[np.argsort(scores[part])[::-1]]

        hits = []
        for rank, i in enumerate(top_idx, 1):
            hits.append({
                "rank_vector":  rank,
                "score_vector": float(scores[i]),
                "chunk_id":     self.chunk_ids[int(i)],
                "source":       self.chunks[int(i)],
            })
        return hits

    def search_by_doc_ids(self, query: str, doc_ids: list, size: int = 20) -> list:
        """
        BM25 search restricted to a set of doc_ids — used by citation-graph
        expansion to fetch the best-matching chunk of each related document.
        Returns a list of source dicts (highest BM25 first).
        """
        if not doc_ids:
            return []
        doc_id_set = set(doc_ids)
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)

        candidates = [
            (scores[i], self.chunks[i])
            for i in range(len(self.chunks))
            if self.chunks[i].get("doc_id", "") in doc_id_set and scores[i] > 0
        ]
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [src for _, src in candidates[:size]]


if __name__ == "__main__":
    store = get_store()
    print(f"\nChunks: {store.count()}")
    print("Doc-type distribution:")
    for k, v in sorted(store.doc_type_counts().items()):
        print(f"  {k:12} {v}")

    print("\nBM25 test — 'gross income':")
    for h in store.bm25_search("gross income", top_k=3):
        s = h["source"]
        print(f"  [{s['doc_type']:6}] {s['doc_title'][:50]:50} p.{s['page_number']} "
              f"(bm25 {h['score_bm25']:.2f})")
