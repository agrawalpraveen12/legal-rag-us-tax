"""
P4 - Hybrid Search Pipeline
=============================
Components:
1. Query Rewriter: Groq llama-3.1-8b (fast, cheap)
2. BM25 Search: ES text match (exact legal terms)
3. Vector Search: ES kNN (semantic understanding)
4. RRF Fusion: Reciprocal Rank Fusion (self-tuning)

Why RRF over weighted sum:
  Weighted sum needs manual tuning (alpha=0.7 BM25 + 0.3 vector)
  RRF is self-tuning: score = 1/(60+rank)
  k=60: empirically best constant (Elasticsearch default)

Why query rewrite:
  "can church lose tax exemption"
  -> "IRC 501c3 tax exempt organization revocation"
  BM25 needs keywords, users ask in natural language
"""

import os
import json
from groq import Groq
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
load_dotenv()

# Config
ES_URL            = os.getenv("ES_URL", "http://localhost:9200")
INDEX_NAME        = "legal_rag"
GROQ_KEY          = os.getenv("GROQ_API_KEY_PRIMARY")
GROQ_KEY_FALLBACK = os.getenv("GROQ_API_KEY_FALLBACK")
EMB_MODEL         = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")

# Global model instance (load once)
_embedding_model = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        print("Loading embedding model...")
        _embedding_model = SentenceTransformer(EMB_MODEL)
    return _embedding_model

def get_es():
    return Elasticsearch(ES_URL)

def get_groq(use_fallback=False):
    key = GROQ_KEY_FALLBACK if use_fallback else GROQ_KEY
    return Groq(api_key=key)

# ─── STEP 1: QUERY REWRITER ──────────────────────────────

def rewrite_query(query: str, use_fallback: bool = False) -> str:
    """
    Rewrite natural language query to legal search terms.

    Why Groq 8B (not 70B):
      Query rewrite is simple task - 8B sufficient
      Saves 70B tokens for generation (limited daily quota)
      Speed: 8B = ~500 tok/sec vs 70B = ~100 tok/sec

    Why temperature=0.1:
      Deterministic output needed
      Same query should always rewrite same way
    """
    system_prompt = """You are a legal search query optimizer for US tax law.
Rewrite the user's question into 5-8 precise legal search terms.
Focus on: IRC section numbers, legal terms, case names, IRS codes.
Return ONLY the search terms, no explanation, no punctuation.
Examples:
Input: "can a company deduct business meals"
Output: IRC 162 business meal expense deduction ordinary necessary

Input: "what happens if you don't pay taxes"
Output: IRC 7201 tax evasion willful failure pay criminal penalty"""

    try:
        client = get_groq(use_fallback)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            max_tokens=50,
            temperature=0.1
        )
        rewritten = response.choices[0].message.content.strip()
        return rewritten
    except Exception as e:
        if not use_fallback and GROQ_KEY_FALLBACK:
            print(f"Primary key failed, using fallback: {e}")
            return rewrite_query(query, use_fallback=True)
        print(f"Query rewrite failed: {e}, using original")
        return query

# ─── STEP 2: BM25 SEARCH ─────────────────────────────────

def bm25_search(query: str, top_k: int = 50) -> list:
    """
    BM25 keyword search using Elasticsearch.

    Why multi_match over match:
      Searches both text and doc_title fields
      Legal queries often match document titles exactly

    Why top_k=50:
      RRF needs enough candidates to work well
      Final reranker picks top-8 from 50
    """
    es = get_es()

    result = es.search(
        index=INDEX_NAME,
        body={
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["text", "doc_title^2", "section_ref^3"],
                    "type": "best_fields"
                }
            },
            "size": top_k,
            "_source": True
        }
    )

    hits = []
    for rank, hit in enumerate(result['hits']['hits']):
        hits.append({
            "rank_bm25":  rank + 1,
            "score_bm25": hit['_score'],
            "chunk_id":   hit['_source']['chunk_id'],
            "source":     hit['_source']
        })

    return hits

# ─── STEP 3: VECTOR SEARCH ───────────────────────────────

def vector_search(query: str, top_k: int = 50) -> list:
    """
    Dense vector search using BGE embeddings + ES kNN.

    Why BGE prefix "Represent this sentence for searching relevant passages:":
      BGE model recommended query prefix for asymmetric search
      Document chunks don't need prefix (already indexed without)
      Improves recall by ~3-5%

    Why num_candidates=100:
      HNSW approximate search candidate pool
      More candidates = more accurate but slower
      100 is ES recommended default
    """
    model = get_embedding_model()

    # BGE recommended query prefix for retrieval tasks
    prefixed_query = f"Represent this sentence for searching relevant passages: {query}"

    query_embedding = model.encode(
        prefixed_query,
        normalize_embeddings=True
    ).tolist()

    es = get_es()

    result = es.search(
        index=INDEX_NAME,
        body={
            "knn": {
                "field": "embedding",
                "query_vector": query_embedding,
                "k": top_k,
                "num_candidates": 100
            },
            "size": top_k,
            "_source": True
        }
    )

    hits = []
    for rank, hit in enumerate(result['hits']['hits']):
        hits.append({
            "rank_vector":  rank + 1,
            "score_vector": hit['_score'],
            "chunk_id":     hit['_source']['chunk_id'],
            "source":       hit['_source']
        })

    return hits

# ─── STEP 4: RRF FUSION ──────────────────────────────────

def rrf_fusion(bm25_hits: list, vector_hits: list, k: int = 60) -> list:
    """
    Reciprocal Rank Fusion combines BM25 + Vector results.

    Formula: RRF_score = 1/(k + rank_bm25) + 1/(k + rank_vector)

    Why k=60:
      - Elasticsearch default, empirically best
      - Reduces impact of top ranks
      - Makes fusion more stable

    Why RRF over weighted sum:
      - No manual alpha tuning needed
      - Self-normalizing across different score scales
      - BM25 scores (0-10) vs Vector scores (0-1) can't be directly added
      - RRF uses ranks (1,2,3...) not raw scores = scale invariant
    """
    scores  = {}
    sources = {}

    # BM25 contribution
    for hit in bm25_hits:
        cid = hit['chunk_id']
        scores[cid]  = scores.get(cid, 0) + 1.0 / (k + hit['rank_bm25'])
        sources[cid] = hit['source']

    # Vector contribution
    for hit in vector_hits:
        cid = hit['chunk_id']
        scores[cid]  = scores.get(cid, 0) + 1.0 / (k + hit['rank_vector'])
        if cid not in sources:
            sources[cid] = hit['source']

    # Sort by RRF score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for rank, (chunk_id, rrf_score) in enumerate(ranked[:50]):
        results.append({
            "rank":      rank + 1,
            "rrf_score": round(rrf_score, 6),
            "chunk_id":  chunk_id,
            "source":    sources[chunk_id]
        })

    return results

# ─── MAIN HYBRID SEARCH ──────────────────────────────────

def hybrid_search(
    query: str,
    top_k: int = 50,
    rewrite: bool = True,
    doc_type_filter: str = None
) -> dict:
    """
    Complete hybrid search pipeline.

    Returns:
      original_query, rewritten_query,
      top-50 RRF results with metadata
    """

    # Step 1: Rewrite query
    rewritten = rewrite_query(query) if rewrite else query

    print(f"Original:  {query}")
    print(f"Rewritten: {rewritten}")

    # Step 2: BM25
    bm25_results = bm25_search(rewritten, top_k)
    print(f"BM25 hits: {len(bm25_results)}")

    # Step 3: Vector
    vector_results = vector_search(rewritten, top_k)
    print(f"Vector hits: {len(vector_results)}")

    # Step 4: RRF
    fused = rrf_fusion(bm25_results, vector_results)
    print(f"After RRF: {len(fused)} unique chunks")

    # Optional filter by doc_type
    if doc_type_filter:
        fused = [r for r in fused if r['source']['doc_type'] == doc_type_filter]

    return {
        "original_query":  query,
        "rewritten_query": rewritten,
        "results":         fused,
        "bm25_count":      len(bm25_results),
        "vector_count":    len(vector_results),
        "total_unique":    len(fused)
    }


if __name__ == "__main__":
    test_queries = [
        "What is gross income under IRC section 61?",
        "Can a church lose its tax exempt status?",
        "What are ordinary and necessary business expenses?",
        "Like kind exchange rules section 1031",
    ]

    print("=" * 60)
    print("P4 - Hybrid Search Test")
    print("=" * 60)

    for query in test_queries:
        print(f"\n{'-'*60}")
        result = hybrid_search(query)
        print(f"\nTop 5 Results:")
        for r in result['results'][:5]:
            s = r['source']
            print(f"  #{r['rank']} [{s['doc_type']:8}] "
                  f"{s['doc_title'][:45]:45} "
                  f"p.{s['page_number']:3} "
                  f"(RRF: {r['rrf_score']:.4f})")
