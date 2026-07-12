"""
P4 - BGE Reranker
==================
Takes top-50 RRF results -> returns top-8

Why cross-encoder reranker:
  Bi-encoder (BGE base): encodes query and doc SEPARATELY
  Cross-encoder (reranker): encodes query+doc TOGETHER
  Cross-encoder sees interaction between query and doc
  Much more accurate but slower (only run on top-50, not all)

Why bge-reranker-base:
  Free, local, no API cost
  Legal domain well-trained
  CPU inference: ~200ms for 50 pairs

Why top-8 final:
  LLM context window: 8 chunks x 600 words = 4800 words
  Fits in Groq LLaMA 70B 8K context with room for answer
  More than 8 = context too long, less relevant chunks included
"""

import os
import sys
from pathlib import Path
from sentence_transformers import CrossEncoder
from dotenv import load_dotenv
load_dotenv()

# Allow running directly: python src/retrieve/rerank.py
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")
TOP_K_FINAL    = int(os.getenv("TOP_K_RERANK", 8))

_reranker = None

def get_reranker():
    global _reranker
    if _reranker is None:
        print(f"Loading reranker: {RERANKER_MODEL}")
        _reranker = CrossEncoder(RERANKER_MODEL)
        print("Reranker loaded")
    return _reranker

def rerank(query: str, candidates: list, top_k: int = TOP_K_FINAL) -> list:
    """
    Rerank top-50 RRF candidates using BGE cross-encoder.

    Why CrossEncoder vs BiEncoder for reranking:
      BiEncoder: embed(query) · embed(doc) = dot product
      CrossEncoder: embed(query + [SEP] + doc) = joint attention
      CrossEncoder sees BOTH at once = much better relevance judgment
      Trade-off: slower, but only on 50 candidates (not full corpus)

    Input: list of RRF results (each has 'source' with 'text')
    Output: top_k reranked results with rerank_score
    """
    reranker = get_reranker()

    if not candidates:
        return []

    # Prepare [query, passage] pairs for cross-encoder
    pairs = [
        [query, candidate['source']['text']]
        for candidate in candidates
    ]

    # Score all pairs in one batch (faster than one-by-one)
    scores = reranker.predict(pairs, show_progress_bar=False)

    # Attach scores to candidates
    for candidate, score in zip(candidates, scores):
        candidate['rerank_score'] = float(score)

    # Sort by rerank score descending (higher = more relevant)
    reranked = sorted(
        candidates,
        key=lambda x: x['rerank_score'],
        reverse=True
    )

    # Return top-k with updated final ranks
    top_results = []
    for new_rank, result in enumerate(reranked[:top_k]):
        result['final_rank']       = new_rank + 1
        result['original_rrf_rank'] = result['rank']
        top_results.append(result)

    return top_results

def retrieve_and_rerank(query: str, hybrid_results: dict) -> list:
    """
    Full pipeline: hybrid results -> reranked top-8
    """
    candidates = hybrid_results.get('results', [])

    if not candidates:
        return []

    print(f"Reranking {len(candidates)} candidates -> top-{TOP_K_FINAL}")
    reranked = rerank(query, candidates)

    print(f"\nTop {TOP_K_FINAL} after reranking:")
    for r in reranked:
        s = r['source']
        print(f"  #{r['final_rank']} "
              f"[{s['doc_type']:8}] "
              f"{s['doc_title'][:40]:40} "
              f"p.{s['page_number']:3} "
              f"(rerank: {r['rerank_score']:+.3f}, "
              f"was RRF #{r['original_rrf_rank']})")

    return reranked


if __name__ == "__main__":
    from src.retrieve.hybrid import hybrid_search

    print("=" * 60)
    print("P4 - Reranker Test")
    print("=" * 60)

    query = "What are ordinary and necessary business expenses under IRC 162?"

    print(f"\nQuery: {query}")
    print("\nStep 1: Hybrid Search...")
    hybrid_results = hybrid_search(query)

    print("\nStep 2: Reranking...")
    final_results = retrieve_and_rerank(query, hybrid_results)

    print(f"\n{'='*60}")
    print("FINAL TOP-8 RESULTS:")
    print(f"{'='*60}")
    for r in final_results:
        s = r['source']
        print(f"\n#{r['final_rank']} {s['doc_title']}")
        print(f"   Type:    {s['doc_type']} | Page: {s['page_number']}")
        print(f"   Section: {s.get('section_ref','N/A')}")
        print(f"   Score:   {r['rerank_score']:+.3f}")
        print(f"   Preview: {s['text'][:150]}...")
