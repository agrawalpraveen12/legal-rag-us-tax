# ─────────────────────────────────────────────────────────────────────────────
# Single-container image for HuggingFace Spaces (and any Docker host).
# Elasticsearch-free: FastAPI serves the REST API AND the static Next.js UI
# on ONE port (7860), backed by the in-process NumPy/BM25 store.
#
# Build UI  →  install Python  →  bake models + embedding index  →  serve.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build the Next.js static export (ui/out) ────────────────────────
FROM node:20-slim AS ui-build
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build          # next.config.ts has output:'export' → emits /ui/out


# ── Stage 2: Python backend serving API + static UI ──────────────────────────
FROM python:3.10-slim
WORKDIR /app

# Cache models INSIDE the image at a fixed, world-readable path so the runtime
# user (HF Spaces runs as uid 1000) finds them without re-downloading.
ENV HF_HOME=/app/hf_cache \
    SENTENCE_TRANSFORMERS_HOME=/app/hf_cache \
    TRANSFORMERS_CACHE=/app/hf_cache \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# System libs needed by PyMuPDF / torch
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# CPU-only torch first — avoids pulling the ~500 MB CUDA wheel
RUN pip install --no-cache-dir --timeout 600 \
    torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --timeout 300 -r requirements.txt

# Pre-download embedding + reranker into the baked cache (no runtime internet)
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-base-en-v1.5'); \
CrossEncoder('BAAI/bge-reranker-base')"

# App source + pre-parsed chunks + static asset
COPY src/ ./src/
COPY api/ ./api/
COPY data/ ./data/
COPY legal_rag_architecture.svg .

# Use the committed embedding index if present (fast, deterministic build);
# otherwise build it here. Precomputing locally + committing data/index/
# avoids a ~30-min CPU embed on every image build.
RUN test -f data/index/embeddings.npy \
    && echo "[docker] Using committed embedding index." \
    || python src/index/build_index.py

# Static UI from stage 1
COPY --from=ui-build /ui/out ./ui/out

# Make caches writable in case ST needs lock files at runtime (uid 1000)
RUN chmod -R 777 /app/hf_cache

EXPOSE 7860
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
