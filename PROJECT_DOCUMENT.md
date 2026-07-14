# Legal RAG System — Complete Project Document

---

## 1. Project Overview

**Legal RAG** is a Retrieval-Augmented Generation system for US tax law research. Given a natural-language question, it retrieves the most relevant passages from a corpus of 101 authoritative documents, reranks them, and generates a grounded answer where every claim is backed by a specific document and page number. The system refuses to answer questions it cannot support from the corpus.

**Problem it solves:** Tax law research requires citing primary sources. Generic LLMs hallucinate statutes and case holdings. This system forces the model to ground every sentence in a retrieved passage and to cite the source explicitly, or to refuse.

### Tech Stack

| Layer | Technology |
|---|---|
| Document parsing | PyMuPDF, pdfplumber, pytesseract |
| Chunking | Custom sliding-window (600 words, 100-word overlap) |
| Vector store + BM25 | Elasticsearch 8.13 (kNN + BM25 hybrid) |
| Embedding model | BAAI/bge-base-en-v1.5 (768-dim, CPU) |
| Reranker | BAAI/bge-reranker-base (cross-encoder, CPU) |
| LLM | LLaMA 3.3 70B Versatile via Groq API |
| Query rewriting | LLaMA 3.1 8B Instant via Groq API |
| Backend API | FastAPI + Uvicorn |
| Frontend | Next.js 16, React 19, Tailwind CSS 4 |
| Citation graph | NetworkX |
| Containerisation | Docker, Docker Compose |

**Architecture diagram:** `legal_rag_architecture.svg` in the repo root.

---

## 2. System Architecture

### Pipeline Phases (P1–P9)

| Phase | Name | What happens |
|---|---|---|
| P1 | Data collection | 101 legal documents downloaded (PDFs + TXT) |
| P2 | Parsing | PDFs parsed to text; page boundaries recorded |
| P3 | Chunking | Text split into 3,497 overlapping chunks with metadata |
| P4 | Indexing | Chunks embedded (BGE) and loaded into Elasticsearch |
| P5 | Citation graph | Cross-document citation relationships mapped with NetworkX |
| P6 | Retrieval | Hybrid BM25 + kNN search returns 50 candidates |
| P7 | Reranking | BGE cross-encoder reranks candidates; top-8 selected |
| P8 | Generation | LLaMA 3.3 70B generates grounded answer with inline citations |
| P9 | UI | Next.js interface with search, answer, and citation display |

### Data Flow

```
User query
  │
  ▼
Query rewriter (LLaMA 3.1 8B, Groq)
  │
  ▼
Hybrid search (Elasticsearch)
  ├── BM25 keyword search  ─┐
  └── kNN vector search    ─┴── RRF fusion (k=60) → 50 candidates
  │
  ▼
BGE cross-encoder reranker → top-8 chunks
  │
  ▼
LLM generation (LLaMA 3.3 70B, Groq)
  │  system prompt: cite every claim or refuse
  │
  ▼
Citation extraction + fuzzy doc_id matching
  │
  ▼
API response: {answer, citations, is_refused, chunks_used}
```

### Component Interaction

- `api/main.py` — FastAPI app; handles startup (model loading, auto-indexing), routes
- `src/retrieve/hybrid.py` — BM25 + kNN hybrid search, RRF fusion, query rewriting
- `src/retrieve/rerank.py` — BGE cross-encoder reranking
- `src/generate/answer.py` — prompt assembly, Groq API call, citation extraction
- `src/index/` — Elasticsearch setup and document indexing
- `src/ingest/parse.py` — PDF parsing and chunking pipeline
- `ui/` — Next.js frontend

---

## 3. Document Corpus

**Total:** 101 documents, 3,497 chunks

| Category | Count | Source |
|---|---|---|
| IRC Statutes (acts) | 25 | IRS.gov statutory text |
| Court Judgments | 15 | CourtListener / Legal Information Institute |
| POV / Commentary | 36 | CRS reports, GAO reports, Tax Foundation, JCT |
| IRS Publications | 10 | IRS.gov publications (Pub 17, 463, 526, etc.) |

**Chunking parameters:**
- Chunk size: 600 words
- Overlap: 100 words
- Metadata per chunk: `doc_id`, `doc_type`, `doc_title`, `page_number`, `section_ref`, `chunk_index`
- Stored in: `data/processed/okf_chunks.jsonl` and Elasticsearch index `legal_rag`

---

## 4. Retrieval Pipeline

### Step 1 — Query Rewriting
LLaMA 3.1 8B Instant rewrites the user query into a more precise legal search formulation before retrieval. Falls back to the original query on API failure.

### Step 2 — Hybrid Search
- **BM25:** Elasticsearch full-text search over the `text` field
- **kNN:** Approximate nearest-neighbour search over BGE-embedded vectors (768 dimensions)
- **Fusion:** Reciprocal Rank Fusion with k=60; both lists contribute 50 candidates each
- **Output:** Top-50 merged candidates

### Step 3 — Reranking
- BAAI/bge-reranker-base cross-encoder scores each (query, chunk) pair
- Top-8 chunks by rerank score are selected
- These 8 chunks (≤500 chars each in API response) are passed to the LLM

### Key parameters (configurable via `.env`)

| Variable | Default | Effect |
|---|---|---|
| `TOP_K_RETRIEVE` | 50 | Candidates from hybrid search |
| `TOP_K_RERANK` | 8 | Chunks passed to LLM |
| `CHUNK_SIZE` | 600 | Words per chunk |
| `CHUNK_OVERLAP` | 100 | Overlap between chunks |

---

## 5. Generation

### Model
LLaMA 3.3 70B Versatile via Groq API (fast inference, free tier available).

### Cite-or-Refuse System Prompt
The system prompt instructs the model that **every factual claim must be followed by an inline citation** in the format `[Document Title, Page N]`. If the retrieved passages do not support an answer, the model must refuse rather than speculate. This is enforced at the prompt level, not post-hoc.

### Citation Extraction
After generation, citations are extracted from the response text using regex and matched to chunk metadata via fuzzy `doc_id` matching (handles minor title variations).

### Rate Limit Management
Four Groq API keys rotate in round-robin. On a `429 RateLimitError`, the system waits 60 seconds and retries before surfacing an error to the user. Each free-tier key provides ~100k tokens/day; four keys give ~400k tokens/day total.

---

## 6. Evaluation Results

Evaluated on 25 of 100 golden-set queries (Groq free-tier rate limits constrained full evaluation).

### Overall

| Metric | Score |
|---|---|
| Reranked Recall@8 | 80.0% |
| Reranked MRR | 72.0% |
| Citation Accuracy | 52.0% |
| Faithfulness (DeBERTa NLI) | 19.5% |
| Refusal Rate | 4.0% |
| Queries Evaluated | 25 / 100 |

### By Document Type

| Doc Type | Recall@8 | Citation Acc | Faithfulness |
|---|---|---|---|
| act (IRC statutes) | 90.0% | 70.0% | 16.7% |
| judgment (case law) | 75.0% | 25.0% | 27.5% |
| pov (commentary) | 83.3% | 66.7% | 16.7% |
| tax (IRS publications) | 0.0% | 0.0% | 0.0% |

> IRS publications scored 0% because they were not present in the 25-query evaluation sample.

### By Query Difficulty

| Difficulty | Recall@8 | Citation Acc | Faithfulness |
|---|---|---|---|
| factual | 100.0% | 75.0% | 25.0% |
| interpretive | 72.7% | 63.6% | 9.4% |
| multi_hop | 80.0% | 0.0% | 36.7% |
| unanswerable | 0.0% | 0.0% | 0.0% |

> Unanswerable queries correctly receive refusals (expected behaviour), scoring 0% on citation/faithfulness metrics.

**Evaluation artefacts:** `reports/interim_evaluation_25.json`, `reports/interim_evaluation_25.xlsx`, `data/golden/golden_set.csv`

---

## 7. API Reference

Base URL: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

---

### POST /api/answer

Generate a grounded answer with citations.

**Request**
```json
{ "query": "What expenses are deductible under IRC Section 162?" }
```

**Response**
```json
{
  "query": "What expenses are deductible under IRC Section 162?",
  "rewritten_query": "IRC Section 162 ordinary and necessary business expense deduction requirements",
  "answer": "Under IRC § 162, a taxpayer may deduct all ordinary and necessary expenses paid during the taxable year in carrying on a trade or business [IRC Section 162, Page 1]. ...",
  "citations": ["IRC Section 162"],
  "is_refused": false,
  "tokens_used": 812,
  "chunks_used": 8,
  "top_chunks": [...],
  "response_time_ms": 3241
}
```

```bash
curl -X POST http://localhost:8000/api/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "What expenses are deductible under IRC Section 162?"}'
```

---

### POST /api/search

Retrieve and rerank chunks without generating an answer.

**Request**
```json
{ "query": "like-kind exchange requirements", "top_k": 8 }
```

**Response**
```json
{
  "query": "like-kind exchange requirements",
  "rewritten_query": "IRC Section 1031 like-kind exchange property requirements",
  "total_chunks": 8,
  "chunks": [
    {
      "chunk_id": "act_sec1031_0",
      "doc_id": "act_sec1031",
      "doc_type": "act",
      "doc_title": "IRC Section 1031",
      "page_number": 1,
      "section_ref": "",
      "text": "No gain or loss shall be recognized on the exchange...",
      "rrf_score": 0.032787,
      "rerank_score": 0.9821,
      "final_rank": 1
    }
  ],
  "response_time_ms": 412
}
```

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "like-kind exchange requirements", "top_k": 8}'
```

---

### GET /api/health

Check system status and Elasticsearch document count.

**Response**
```json
{
  "status": "ok",
  "elasticsearch": {
    "status": "ok",
    "doc_count": 3497,
    "version": "8.13.0"
  },
  "embedding_model": "BAAI/bge-base-en-v1.5",
  "reranker_model": "BAAI/bge-reranker-base",
  "llm_model": "llama-3.3-70b-versatile"
}
```

```bash
curl http://localhost:8000/api/health
```

---

### GET /api/graph

Retrieve the citation graph (node and edge counts, up to 500 edges).

**Response**
```json
{
  "node_count": 101,
  "edge_count": 247,
  "edges": [
    { "source": "act_sec162", "target": "act_sec263", "relationship": "cross-reference" }
  ]
}
```

```bash
curl http://localhost:8000/api/graph
```

---

## 8. Setup — Method A: Local Development

**Prerequisites:** Python 3.10+, Node.js 20+, Docker Desktop

```bash
# 1. Clone repo
git clone https://github.com/YOUR_USERNAME/legal-rag.git
cd legal-rag

# 2. Start Elasticsearch
docker compose up -d elasticsearch

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set GROQ_API_KEY_PRIMARY and change ES_URL to http://localhost:9200

# 5. Index documents (first time only — takes ~5 minutes)
python src/ingest/parse.py
python src/index/es_setup.py
python src/index/index_docs.py

# 6. Start backend
uvicorn api.main:app --reload --port 8000

# 7. Start frontend (new terminal)
cd ui && npm install && npm run dev

# 8. Open http://localhost:3001
```

---

## 9. Setup — Method B: Docker Compose

**Prerequisites:** Docker Desktop, Groq API key

```bash
# 1. Clone repo
git clone https://github.com/YOUR_USERNAME/legal-rag.git
cd legal-rag

# 2. Configure environment
cp .env.example .env
# Edit .env — add your Groq API key

# 3. Start everything
docker compose up

# 4. Wait 3–5 minutes (first run downloads models + indexes 3,497 chunks)

# 5. Open http://localhost:3001
```

The backend auto-detects an empty Elasticsearch index on startup and runs `es_setup.py` + `index_docs.py` automatically. Subsequent starts skip indexing.

---

## 10. Setup — Method C: Docker Hub (Easiest)

**Prerequisites:** Docker Desktop, Groq API key

```bash
# 1. Create .env file
cp .env.example .env
# Edit .env — add your Groq API key

# 2. Pull images and start
docker pull YOUR_DOCKERHUB/legal-rag-backend:latest
docker pull YOUR_DOCKERHUB/legal-rag-frontend:latest
docker compose -f docker-compose.prod.yml up

# 3. Open http://localhost:3001
```

---

## 11. Project Structure

```
legal-rag/
│
├── api/
│   ├── Dockerfile          # Backend Docker image (Python 3.10-slim + CPU torch)
│   ├── main.py             # FastAPI app: routes, startup hooks, CORS
│   └── __init__.py
│
├── src/
│   ├── config.py           # Centralised env-var loading
│   ├── ingest/
│   │   └── parse.py        # PDF → text → chunks (600w/100w overlap)
│   ├── index/
│   │   ├── es_setup.py     # Create Elasticsearch index with kNN mapping
│   │   ├── index_docs.py   # Embed chunks and bulk-load into ES
│   │   └── graph.py        # Build citation graph with NetworkX
│   ├── retrieve/
│   │   ├── hybrid.py       # BM25 + kNN hybrid search, RRF fusion, query rewrite
│   │   └── rerank.py       # BGE cross-encoder reranking
│   ├── generate/
│   │   └── answer.py       # Groq API call, cite-or-refuse prompt, citation extraction
│   └── eval/
│       ├── evaluate.py     # Full evaluation runner
│       ├── metrics.py      # Recall@k, MRR, citation accuracy, faithfulness (NLI)
│       └── golden_gen.py   # Golden set generation
│
├── ui/                     # Next.js 16 frontend
│   ├── Dockerfile          # Frontend Docker image (Node 20-alpine)
│   ├── app/
│   │   ├── page.tsx        # Main search + answer UI
│   │   ├── layout.tsx      # Root layout
│   │   └── globals.css     # Tailwind CSS 4 global styles
│   ├── package.json
│   └── next.config.ts
│
├── data/
│   ├── raw/                # Downloaded PDFs and TXT files (not in Docker image)
│   │   ├── acts/           # IRC statute PDFs
│   │   ├── judgments/      # Court judgment TXT files
│   │   ├── pov/            # Commentary PDFs (CRS, GAO, Tax Foundation, JCT)
│   │   └── tax_docs/       # IRS publication PDFs
│   ├── processed/
│   │   ├── okf_chunks.jsonl    # All 3,497 parsed chunks
│   │   ├── manifest.csv        # Document-level metadata
│   │   └── citation_graph.pkl  # NetworkX graph (pickled)
│   └── golden/
│       ├── golden_set.csv          # 100 evaluation queries with expected doc_ids
│       └── golden_set_reviewed.xlsx
│
├── reports/
│   ├── interim_evaluation_25.json  # 25-query evaluation results (JSON)
│   └── interim_evaluation_25.xlsx  # 25-query evaluation results (Excel)
│
├── scripts/                # One-off download scripts (not needed after initial setup)
│   ├── download_acts.py
│   ├── download_judgments.py
│   ├── download_pov_fixed.py
│   └── download_tax_docs.py
│
├── docker-compose.yml      # Elasticsearch + backend + frontend services
├── .env.example            # All environment variables with documentation
├── requirements.txt        # Python dependencies
├── legal_rag_architecture.svg  # System architecture diagram
├── README.md               # Quick-start guide
├── SETUP.md                # Extended setup guide
└── PROJECT_DOCUMENT.md     # This document
```

---

## 12. Known Limitations

| Limitation | Detail |
|---|---|
| Groq free tier rate limits | 4 keys × ~100k tokens/day = ~400k TPD. On exhaustion the system waits 60s and retries automatically. |
| Elasticsearch RAM | Requires minimum 2 GB RAM allocated to Docker. Increase Docker Desktop memory limit if ES fails to start. |
| First-run indexing | ~5 minutes to embed 3,497 chunks and load into ES. Subsequent starts skip this step. |
| CPU-only inference | Embedding and reranking run on CPU (no GPU required, but slower on very large batches). |
| Faithfulness metric | DeBERTa NLI faithfulness scored 19.5% overall; this metric is strict — partial entailment scores low. |
| IRS publications | Not represented in the 25-query evaluation sample; recall/faithfulness scores for `tax` type are not meaningful. |
| Multi-hop citation | Multi-hop queries (80% Recall@8) had 0% citation accuracy — the model retrieves correctly but fails to cite cross-document chains inline. |

---

## 13. For Evaluators / Interviewers

**Quickest path to a running system:**

1. Get a free Groq API key at [console.groq.com](https://console.groq.com)
2. Clone the repo and run:
   ```bash
   cp .env.example .env
   # Add your key as GROQ_API_KEY_PRIMARY in .env
   docker compose up
   ```
3. Wait ~5 minutes for first-run indexing
4. Open [http://localhost:3001](http://localhost:3001)

**Sample queries to try:**
- "What ordinary business expenses are deductible under Section 162?"
- "What was the holding in Commissioner v. Glenshaw Glass?"
- "How does the like-kind exchange deferral work under Section 1031?"
- "Can charitable deductions be taken for payments to religious organisations that provide personal benefits?"

**API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

**Evaluation data:** `reports/interim_evaluation_25.xlsx` — full per-query breakdown with retrieved chunks, generated answers, and metric scores.
