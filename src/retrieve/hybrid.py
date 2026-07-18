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
import sys
import json
import pickle
from pathlib import Path
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
load_dotenv()

# Allow running directly: python src/retrieve/hybrid.py
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from config import groq_call_with_rotation          # when src/ is in sys.path
except ImportError:
    from src.config import groq_call_with_rotation      # when project root is in sys.path

# Config
ES_URL     = os.getenv("ES_URL", "http://localhost:9200")
INDEX_NAME = "legal_rag"
EMB_MODEL  = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
GRAPH_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "processed", "citation_graph.pkl"
)

# Global model instance (load once)
_embedding_model = None
_citation_graph = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        print("Loading embedding model...")
        _embedding_model = SentenceTransformer(EMB_MODEL)
    return _embedding_model

def get_es():
    return Elasticsearch(ES_URL)

def get_citation_graph():
    """Lazy-load the citation graph; returns None if not available."""
    global _citation_graph
    if _citation_graph is None and os.path.exists(GRAPH_FILE):
        try:
            with open(GRAPH_FILE, "rb") as f:
                _citation_graph = pickle.load(f)
            print(f"Citation graph loaded: {_citation_graph.number_of_nodes()} nodes")
        except Exception as e:
            print(f"Citation graph load failed: {e}")
    return _citation_graph

# ─── STEP 1: QUERY REWRITER ──────────────────────────────

def rewrite_query(query: str) -> str:
    """
    Rewrite natural language query to legal search terms.
    Uses the full 4-key round-robin rotation (previously only 2 keys were used).

    Why Groq 8B (not 70B):
      Query rewrite is simple — 8B is sufficient and much faster.
      Saves 70B quota for answer generation.
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
        rewritten = groq_call_with_rotation(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            model="llama-3.1-8b-instant",
            max_tokens=50,
            temperature=0.1,
        ).strip()
        return rewritten
    except Exception as e:
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

def generate_query_variants(original_query: str, rewritten: str, n: int = 2) -> list:
    """
    Generate n alternative query phrasings to improve recall on conceptual questions.
    BM25 and vector search run against all variants; multi_query_rrf_fusion merges results.
    Uses 8B (cheap/fast) — query rewriting doesn't need 70B.
    """
    system_prompt = (
        "You are a US tax law search expert. "
        "Given an original question and one rewritten search query, produce {n} "
        "alternative search queries that emphasize DIFFERENT legal concepts or terminology. "
        "Return exactly {n} lines, one query per line, no numbers, bullets, or explanation."
    ).format(n=n)

    try:
        response = groq_call_with_rotation(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    f"Original question: {original_query}\n"
                    f"Existing search query: {rewritten}\n"
                    f"Generate {n} alternative queries:"
                )},
            ],
            model="llama-3.1-8b-instant",
            max_tokens=100,
            temperature=0.3,
        ).strip()
        variants = [line.strip() for line in response.split('\n') if line.strip()][:n]
        return variants
    except Exception as e:
        print(f"Query variant generation failed: {e}")
        return []


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


def multi_query_rrf_fusion(query_result_pairs: list, k: int = 60) -> list:
    """
    RRF fusion across multiple (bm25_hits, vector_hits) pairs — one pair per query variant.
    Chunks retrieved by more variants accumulate higher scores, surfacing results
    that are relevant from multiple angles (keyword match AND semantic match).
    """
    scores = {}
    sources = {}

    for bm25_hits, vector_hits in query_result_pairs:
        for hit in bm25_hits:
            cid = hit['chunk_id']
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + hit['rank_bm25'])
            sources[cid] = hit['source']
        for hit in vector_hits:
            cid = hit['chunk_id']
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + hit['rank_vector'])
            if cid not in sources:
                sources[cid] = hit['source']

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


# ─── STEP 5: GRAPH EXPANSION ─────────────────────────────

def graph_expand(query: str, rrf_results: list, top_initial: int = 10) -> list:
    """
    Expand RRF candidates with 1-hop citation-graph neighbours.

    After RRF fusion gives top-50 candidates, the graph finds documents that
    CITE or ARE CITED BY the top-10 results and fetches their highest-BM25
    chunks. These are appended to the candidate pool at a slightly lower score
    so the reranker can still surface them for multi-hop queries.

    Example: query about IRC§162 retrieves Welch v. Helvering. Graph knows
    Welch CITES act_sec162 → act_sec162 chunks are added even if they ranked
    below 50 in the initial hybrid search.
    """
    G = get_citation_graph()
    if G is None:
        return rrf_results

    # Collect doc_ids from the first top_initial results
    top_doc_ids = []
    for r in rrf_results[:top_initial]:
        doc_id = r["source"].get("doc_id", "")
        if doc_id and doc_id not in top_doc_ids:
            top_doc_ids.append(doc_id)

    if not top_doc_ids:
        return rrf_results

    # 1-hop neighbours (predecessors + successors)
    related_ids = set()
    for doc_id in top_doc_ids:
        if doc_id in G:
            related_ids.update(G.predecessors(doc_id))
            related_ids.update(G.successors(doc_id))
    related_ids -= set(top_doc_ids)

    # Remove docs already represented in the candidate pool
    already_in_pool = {r["source"].get("doc_id", "") for r in rrf_results}
    new_doc_ids = [d for d in related_ids if d not in already_in_pool]

    if not new_doc_ids:
        return rrf_results

    # Fetch the best BM25-matching chunk per related doc
    try:
        es = get_es()
        es_result = es.search(
            index=INDEX_NAME,
            body={
                "query": {
                    "bool": {
                        "must":   {"multi_match": {"query": query, "fields": ["text", "doc_title^2"]}},
                        "filter": [{"terms": {"doc_id": new_doc_ids}}],
                    }
                },
                "size": min(len(new_doc_ids) * 2, 20),
                "_source": True,
            },
        )
    except Exception as e:
        print(f"Graph expansion ES query failed: {e}")
        return rrf_results

    # Append expanded chunks with a score slightly below the current minimum
    min_score = min((r["rrf_score"] for r in rrf_results), default=0.001) * 0.7
    seen_chunks = {r["chunk_id"] for r in rrf_results}
    for hit in es_result["hits"]["hits"]:
        cid = hit["_source"]["chunk_id"]
        if cid in seen_chunks:
            continue
        seen_chunks.add(cid)
        rrf_results.append({
            "rank":         len(rrf_results) + 1,
            "rrf_score":    min_score,
            "chunk_id":     cid,
            "source":       hit["_source"],
            "graph_expanded": True,
        })

    print(f"Graph expansion added {len(es_result['hits']['hits'])} candidates from {len(new_doc_ids)} related docs")
    return rrf_results


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

    # Step 2: Generate query variants for multi-query retrieval
    variants = generate_query_variants(query, rewritten, n=2) if rewrite else []
    all_queries = [rewritten] + variants
    if variants:
        print(f"Variants:  {variants}")

    # Step 3: BM25 + Vector for each query variant
    all_bm25 = []
    all_vector = []
    for q in all_queries:
        all_bm25.append(bm25_search(q, top_k))
        all_vector.append(vector_search(q, top_k))
    print(f"BM25 hits: {len(all_bm25[0])} (primary) + {sum(len(h) for h in all_bm25[1:])} (variants)")
    print(f"Vector hits: {len(all_vector[0])} (primary) + {sum(len(h) for h in all_vector[1:])} (variants)")

    # Step 4: Multi-query RRF fusion — chunks consistent across variants rank higher
    fused = multi_query_rrf_fusion(list(zip(all_bm25, all_vector)))
    print(f"After multi-query RRF: {len(fused)} unique chunks")

    # Step 5: Citation graph expansion
    fused = graph_expand(rewritten, fused)
    print(f"After graph expansion: {len(fused)} candidates")

    # Optional filter by doc_type
    if doc_type_filter:
        fused = [r for r in fused if r['source']['doc_type'] == doc_type_filter]

    return {
        "original_query":  query,
        "rewritten_query": rewritten,
        "results":         fused,
        "bm25_count":      len(all_bm25[0]),
        "vector_count":    len(all_vector[0]),
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
