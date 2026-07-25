# Deploying to HuggingFace Spaces (single container, free tier)

This project has been refactored to run **backend + frontend in one container**
with **no Elasticsearch** — so it fits a free HuggingFace Docker Space.

## What changed (Option A refactor)

| Before | After |
|---|---|
| Elasticsearch 8.13 service (BM25 + kNN) | In-process store: `rank-bm25` + NumPy cosine (`src/index/store.py`) |
| 3 containers (ES + backend + frontend) | 1 container, FastAPI serves API **and** the static UI |
| Next.js dev server on its own port | Next.js **static export** (`output: 'export'`) served by FastAPI |
| `NEXT_PUBLIC_API_URL=http://localhost:8000` | UI calls **relative** `/api/answer` (same origin) |
| ES index built at runtime | Embeddings precomputed into `data/index/embeddings.npy` at image build |

The LLM still runs remotely on **Groq** (free tier) — only the search database was replaced.

## Architecture on HF

```
Browser ──▶ HuggingFace Space (one container, port 7860)
                │
                ├── /                → static Next.js UI (ui/out)
                └── /api/answer …    → FastAPI RAG pipeline
                                         ├─ rank-bm25 (keyword)     ┐ in-process
                                         ├─ NumPy cosine (vector)   ┘ store.py
                                         ├─ BGE reranker (local)
                                         └─ Groq LLaMA 70B (remote API)
```

## One-time local check (recommended before pushing)

```bash
# 1. Build the embedding index (writes data/index/embeddings.npy)
python src/index/build_index.py

# 2. Build the static UI
cd ui && npm install && npm run build && cd ..

# 3. Run the whole thing locally on one port
uvicorn api.main:app --host 0.0.0.0 --port 7860
# open http://localhost:7860
```

## Deploy steps

1. **Create a Space**
   - huggingface.co → *New Space* → **SDK: Docker** → *Blank*.
   - The `README.md` front-matter already sets `sdk: docker` and `app_port: 7860`.

2. **Add your Groq keys as Space Secrets** (Settings → *Variables and secrets*):
   - `GROQ_API_KEY_PRIMARY`
   - `GROQ_API_KEY_FALLBACK`
   - `GROQ_API_KEY_3`
   - `GROQ_API_KEY_4`
   - (Only `GROQ_API_KEY_PRIMARY` is strictly required; the rest add throughput.)
   - **Do not** commit `.env` — it stays local / gitignored.

3. **Commit the corpus + prebuilt index** (HF builds from the git repo, so these
   must be committed — they are no longer gitignored). The two ~10 MB files are
   best tracked with Git LFS:
   ```bash
   git lfs install
   git lfs track "data/processed/okf_chunks.jsonl" "data/index/embeddings.npy"
   git add .gitattributes \
           data/processed/okf_chunks.jsonl data/processed/citation_graph.pkl \
           data/index/embeddings.npy data/index/chunk_ids.json
   git add .   # the refactor's code changes
   git commit -m "Elasticsearch-free single-container build for HF Spaces"
   ```
   (If you skip committing `data/index/`, the Docker build will re-embed the
   corpus itself — correct, but adds ~10–30 min to the build.)

4. **Push the repo to the Space**
   ```bash
   git remote add space https://huggingface.co/spaces/<user>/<space-name>
   git push space main
   ```
   HF builds the `Dockerfile` (installs deps, bakes the BGE models, precomputes
   the embedding index, builds the UI) and starts it on port 7860.

5. **First build takes ~5–10 min** (torch + model download + UI build; the index
   is reused if committed). After that the Space is live at
   `https://<user>-<space-name>.hf.space`.

## Notes / caveats

- **Free tier** (16 GB RAM / 2 vCPU): the Space **sleeps** when idle and cold-starts
  slowly (loads BGE embedder + reranker). Fine for a demo, not for heavy traffic.
- **Index ships in the image** — no persistent storage needed. To change the corpus,
  re-run `src/ingest/parse.py` then `src/index/build_index.py`, commit, and push.
- **Groq rate limits** still apply; the 4-key rotation in `src/config.py` is unchanged.
- The old Elasticsearch path (`docker-compose.yml`, `src/index/es_setup.py`,
  `src/index/index_docs.py`) is kept for reference / AWS deployments but is **not**
  used by the HF container.

## Deploying elsewhere (AWS, etc.)

The same single-container `Dockerfile` runs anywhere:
```bash
docker build -t legal-rag .
docker run -p 7860:7860 --env-file .env legal-rag
```
For an always-on host (EC2, Fly.io, Render, etc.) that one command is the whole deploy.
