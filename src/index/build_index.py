"""
Build the local vector index (Elasticsearch-free)
==================================================
Precomputes BGE embeddings for every chunk and saves them as a NumPy
matrix so the in-process store (src/index/store.py) can do brute-force
cosine search with zero external services.

Outputs (committed / shipped with the image):
  data/index/embeddings.npy   float32 (N, 768), L2-normalized
  data/index/chunk_ids.json   list[str] row order for the matrix

Run once locally (or in the Docker build):
  python src/index/build_index.py

Replaces the old ES pipeline:
  src/index/es_setup.py + src/index/index_docs.py  (no longer needed)
"""

import os
import sys
import json
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

CHUNKS_FILE = os.getenv("CHUNKS_FILE", str(_PROJECT_ROOT / "data" / "processed" / "okf_chunks.jsonl"))
INDEX_DIR   = Path(os.getenv("INDEX_DIR", str(_PROJECT_ROOT / "data" / "index")))
EMB_FILE    = INDEX_DIR / "embeddings.npy"
IDS_FILE    = INDEX_DIR / "chunk_ids.json"
MODEL_NAME  = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
BATCH_SIZE  = int(os.getenv("EMBED_BATCH_SIZE", 32))


def load_chunks(filepath: str) -> list:
    chunks = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    print(f"[build] Loaded {len(chunks)} chunks from {filepath}")
    return chunks


def main():
    print("=" * 60)
    print("Build local vector index (NumPy cosine store)")
    print("=" * 60)

    if not os.path.exists(CHUNKS_FILE):
        raise FileNotFoundError(
            f"Chunk file not found: {CHUNKS_FILE}. Run src/ingest/parse.py first."
        )

    chunks = load_chunks(CHUNKS_FILE)
    chunk_ids = [c["chunk_id"] for c in chunks]
    texts = [c.get("text", "") for c in chunks]

    print(f"[build] Loading embedding model: {MODEL_NAME} (first run downloads ~400 MB)…")
    model = SentenceTransformer(MODEL_NAME)

    print(f"[build] Embedding {len(texts)} chunks (batch={BATCH_SIZE})…")
    start = time.time()
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,   # unit vectors -> dot product == cosine
        show_progress_bar=True,
        convert_to_numpy=True,
    ).astype(np.float32)
    print(f"[build] Done in {time.time() - start:.1f}s — shape {embeddings.shape}")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMB_FILE, embeddings)
    with open(IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunk_ids, f)

    size_mb = EMB_FILE.stat().st_size / (1024 * 1024)
    print(f"[build] Saved {EMB_FILE} ({size_mb:.1f} MB)")
    print(f"[build] Saved {IDS_FILE} ({len(chunk_ids)} ids)")
    print("\n[build] COMPLETE — the store can now serve vector search with no Elasticsearch.")


if __name__ == "__main__":
    main()
