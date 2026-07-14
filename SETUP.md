# Quick-Start Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| Docker | any | For Elasticsearch |
| Groq API keys | — | Free at [console.groq.com](https://console.groq.com) |

---

## 1. Start Elasticsearch

```bash
docker-compose up -d
```

Verify it's up (takes ~15 seconds):

```bash
curl http://localhost:9200
```

---

## 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your Groq API keys. The system uses 4-key round-robin rotation to maximise the free-tier rate limit (100k tokens/day per key → 400k total).

---

## 4. Ingest and index documents

> **Skip this step** if you already have a populated Elasticsearch index.

```bash
# Parse PDFs → chunked JSON (outputs to data/processed/)
python src/ingest/parse.py

# Create Elasticsearch index schema
python src/index/es_setup.py

# Bulk-index all chunks
python src/index/index_docs.py

# Build citation graph (optional — needed for /api/graph)
python src/index/graph.py
```

---

## 5. Start the backend API

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

Swagger UI: <http://localhost:8000/docs>

Models are loaded once at startup (embedding + reranker take ~5 seconds).

---

## 6. Start the frontend

```bash
cd ui
npm install
npm run dev
```

Open <http://localhost:3000> in your browser.

---

## Verify everything works

```bash
# Health check
curl http://localhost:8000/api/health

# Test a query
curl -X POST http://localhost:8000/api/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "What is gross income under IRC Section 61?"}'
```

---

## Run the evaluation harness

```bash
# Full 100-query run (checkpoints every 5 queries; auto-resumes on restart)
python src/eval/evaluate.py

# Quick smoke-test (first 2 queries)
python src/eval/evaluate.py --dry-run

# Force fresh run ignoring checkpoint
python src/eval/evaluate.py --no-cache
```

Results are written to `reports/evaluation_report.xlsx`.
