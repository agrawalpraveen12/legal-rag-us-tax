"""
Smoke test: prove retrieval works with NO Elasticsearch.
Runs BM25 + vector + RRF + rerank on a few queries using the in-process store.
rewrite=False so it needs no Groq API key.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.index.store import get_store
from src.retrieve.hybrid import hybrid_search
from src.retrieve.rerank import retrieve_and_rerank

store = get_store()
print(f"\n[store] {store.count()} chunks, vector={'yes' if store.embeddings is not None else 'NO'}")
print("[store] doc types:", store.doc_type_counts())

QUERIES = [
    "What is included in gross income under IRC section 61?",
    "ordinary and necessary business expenses",
    "like kind exchange section 1031",
]

for q in QUERIES:
    print("\n" + "=" * 70)
    print("QUERY:", q)
    res = hybrid_search(q, rewrite=False)            # rewrite=False → no Groq call
    reranked = retrieve_and_rerank(q, res)
    print(f"candidates={res['total_unique']}  reranked_top={len(reranked)}")
    for r in reranked[:5]:
        s = r["source"]
        print(f"  #{r['final_rank']} [{s['doc_type']:5}] {s['doc_title'][:48]:48} "
              f"p.{s['page_number']}  rerank={r['rerank_score']:+.3f}")

print("\nOK — retrieval pipeline ran end-to-end with no Elasticsearch.")
