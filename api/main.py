import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(
    title="Legal RAG API",
    description="US Tax Law Research Assistant",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    query: str
    top_k: int = 8
    doc_type_filter: Optional[str] = None
    rewrite: bool = True

class AnswerRequest(BaseModel):
    query: str

_models_loaded = False

def ensure_models():
    global _models_loaded
    if not _models_loaded:
        from src.retrieve.hybrid import get_embedding_model
        from src.retrieve.rerank import get_reranker
        get_embedding_model()
        get_reranker()
        _models_loaded = True

@app.get("/")
async def root():
    return {
        "message": "Legal RAG API - US Tax Law",
        "docs": "/docs",
        "endpoints": [
            "POST /api/search",
            "POST /api/answer",
            "GET  /api/health",
            "GET  /api/graph"
        ]
    }

@app.get("/api/health")
async def health():
    from elasticsearch import Elasticsearch
    es = Elasticsearch(os.getenv("ES_URL", "http://localhost:9200"))
    try:
        info = es.info()
        count = es.count(index="legal_rag")
        es_status = "ok"
        es_docs = count['count']
        es_version = info['version']['number']
    except Exception as e:
        es_status = f"error: {str(e)}"
        es_docs = 0
        es_version = "unknown"

    return {
        "status": "ok",
        "elasticsearch": {
            "status": es_status,
            "docs_indexed": es_docs,
            "version": es_version
        },
        "models": {
            "embedding": "BAAI/bge-base-en-v1.5",
            "reranker":  "BAAI/bge-reranker-base",
            "llm":       "llama-3.1-8b-instant"
        },
        "total_chunks": 3497
    }

@app.post("/api/search")
async def search(request: SearchRequest):
    start = time.time()
    try:
        ensure_models()
        from src.retrieve.hybrid import hybrid_search
        from src.retrieve.rerank import retrieve_and_rerank

        hybrid_results = hybrid_search(
            query=request.query,
            top_k=50,
            rewrite=request.rewrite,
            doc_type_filter=request.doc_type_filter
        )
        reranked = retrieve_and_rerank(request.query, hybrid_results)

        chunks = []
        for r in reranked[:request.top_k]:
            source = r.get('source', r)
            chunks.append({
                "chunk_id":    source.get('chunk_id',''),
                "doc_id":      source.get('doc_id',''),
                "doc_type":    source.get('doc_type',''),
                "doc_title":   source.get('doc_title',''),
                "page_number": source.get('page_number',0),
                "section_ref": source.get('section_ref',''),
                "text":        source.get('text','')[:500],
                "rrf_score":   round(r.get('rrf_score',0),6),
                "rerank_score":round(r.get('rerank_score',0),4),
                "final_rank":  r.get('final_rank',0)
            })

        return {
            "query": request.query,
            "rewritten_query": hybrid_results.get('rewritten_query', request.query),
            "total_chunks": len(chunks),
            "chunks": chunks,
            "response_time_ms": int((time.time()-start)*1000)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/answer")
async def answer(request: AnswerRequest):
    start = time.time()
    try:
        ensure_models()
        from src.generate.answer import rag_pipeline
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(rag_pipeline, request.query)
            try:
                result = future.result(timeout=45)
            except concurrent.futures.TimeoutError:
                raise HTTPException(
                    status_code=503,
                    detail="Generation timed out - Groq API rate limited. Try again in 60 seconds."
                )

        return {
            "query":           request.query,
            "rewritten_query": result.get('rewritten_query', request.query),
            "answer":          result['answer'],
            "citations":       result['citations'],
            "is_refused":      result['is_refused'],
            "tokens_used":     result['tokens_used'],
            "chunks_used":     result['chunks_used'],
            "top_chunks": [
                {
                    "doc_title":   c.get('source',c).get('doc_title',''),
                    "page_number": c.get('source',c).get('page_number',0),
                    "doc_type":    c.get('source',c).get('doc_type',''),
                    "text":        c.get('source',c).get('text','')[:300],
                    "rerank_score":round(c.get('rerank_score',0),4)
                }
                for c in result.get('top_chunks',[])
            ],
            "response_time_ms": int((time.time()-start)*1000)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/graph")
async def graph_stats():
    import pickle
    try:
        with open("data/processed/citation_graph.pkl","rb") as f:
            G = pickle.load(f)
        edge_types = {}
        for u,v,data in G.edges(data=True):
            rel = data.get('relationship','unknown')
            edge_types[rel] = edge_types.get(rel,0)+1
        type_counts = {}
        for node,data in G.nodes(data=True):
            t = data.get('doc_type','unknown')
            type_counts[t] = type_counts.get(t,0)+1
        return {
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "nodes_by_type": type_counts,
            "edges_by_type": edge_types
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))