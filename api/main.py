import os
import sys
import time
from contextlib import asynccontextmanager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
load_dotenv()


# ── Startup: load all heavy models once ──────────────────────────────────────

def _load_models_sync():
    from src.retrieve.hybrid import get_embedding_model
    from src.retrieve.rerank import get_reranker
    print("[startup] Loading embedding model …")
    get_embedding_model()
    print("[startup] Loading reranker …")
    get_reranker()
    print("[startup] All models ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _load_models_sync)
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Legal RAG API",
    description="US Tax Law Research Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 8
    doc_type_filter: Optional[str] = None
    rewrite: bool = True


class AnswerRequest(BaseModel):
    query: str


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "message": "Legal RAG API — US Tax Law",
        "docs": "/docs",
        "endpoints": [
            "POST /api/answer",
            "POST /api/search",
            "GET  /api/health",
            "GET  /api/graph",
        ],
    }


@app.get("/api/health")
async def health():
    from elasticsearch import Elasticsearch
    es = Elasticsearch(os.getenv("ES_URL", "http://localhost:9200"))
    try:
        info  = es.info()
        count = es.count(index="legal_rag")
        es_status  = "ok"
        es_docs    = count["count"]
        es_version = info["version"]["number"]
    except Exception as exc:
        es_status  = f"error: {exc}"
        es_docs    = 0
        es_version = "unknown"

    return {
        "status": "ok",
        "elasticsearch": {
            "status":      es_status,
            "doc_count":   es_docs,
            "version":     es_version,
        },
        "embedding_model": "BAAI/bge-base-en-v1.5",
        "reranker_model":  "BAAI/bge-reranker-base",
        "llm_model":       "llama-3.3-70b-versatile",
    }


@app.post("/api/search")
async def search(request: SearchRequest):
    start = time.time()
    try:
        from src.retrieve.hybrid import hybrid_search
        from src.retrieve.rerank import retrieve_and_rerank

        hybrid_results = hybrid_search(
            query=request.query,
            top_k=50,
            rewrite=request.rewrite,
            doc_type_filter=request.doc_type_filter,
        )
        reranked = retrieve_and_rerank(request.query, hybrid_results)

        chunks = []
        for r in reranked[: request.top_k]:
            source = r.get("source", r)
            chunks.append({
                "chunk_id":     source.get("chunk_id", ""),
                "doc_id":       source.get("doc_id", ""),
                "doc_type":     source.get("doc_type", ""),
                "doc_title":    source.get("doc_title", ""),
                "page_number":  source.get("page_number", 0),
                "section_ref":  source.get("section_ref", ""),
                "text":         source.get("text", "")[:500],
                "rrf_score":    round(r.get("rrf_score", 0), 6),
                "rerank_score": round(r.get("rerank_score", 0), 4),
                "final_rank":   r.get("final_rank", 0),
            })

        return {
            "query":            request.query,
            "rewritten_query":  hybrid_results.get("rewritten_query", request.query),
            "total_chunks":     len(chunks),
            "chunks":           chunks,
            "response_time_ms": int((time.time() - start) * 1000),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/answer")
async def answer(request: AnswerRequest):
    import concurrent.futures
    start = time.time()
    try:
        from src.generate.answer import rag_pipeline

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(rag_pipeline, request.query)
            try:
                result = future.result(timeout=45)
            except concurrent.futures.TimeoutError:
                raise HTTPException(
                    status_code=503,
                    detail="Generation timed out. Groq API may be rate-limited — try again in 60 s.",
                )

        return {
            "query":            request.query,
            "rewritten_query":  result.get("rewritten_query", request.query),
            "answer":           result["answer"],
            "citations":        result["citations"],
            "is_refused":       result["is_refused"],
            "tokens_used":      result.get("tokens_used", 0),
            "chunks_used":      result["chunks_used"],
            "top_chunks": [
                {
                    "doc_title":    c.get("source", c).get("doc_title", ""),
                    "page_number":  c.get("source", c).get("page_number", 0),
                    "doc_type":     c.get("source", c).get("doc_type", ""),
                    "text":         c.get("source", c).get("text", "")[:300],
                    "rerank_score": round(c.get("rerank_score", 0), 4),
                }
                for c in result.get("top_chunks", [])
            ],
            "response_time_ms": int((time.time() - start) * 1000),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/graph")
async def graph_stats():
    import pickle
    try:
        with open("data/processed/citation_graph.pkl", "rb") as f:
            G = pickle.load(f)

        edges = [
            {"source": u, "target": v, "relationship": data.get("relationship", "unknown")}
            for u, v, data in G.edges(data=True)
        ]
        return {
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "edges":      edges[:500],   # cap for JSON size
        }
    except FileNotFoundError:
        return {"node_count": 0, "edge_count": 0, "edges": []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
