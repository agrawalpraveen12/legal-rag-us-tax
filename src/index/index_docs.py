"""
P3 - Document Indexing Pipeline
================================
Step 1: Load BGE-base-en-v1.5 model (local, free)
Step 2: Generate 768-dim embeddings for each chunk
Step 3: Bulk index into Elasticsearch

Why BGE-base-en-v1.5:
  - MTEB legal benchmark top performer
  - 768 dims: quality vs speed balance
  - Free, local, no API cost
  - Legal text trained

Why batch_size=32:
  - Memory efficient for CPU
  - BGE model fits in RAM with batch 32
  - Larger batch = OOM risk on 8GB RAM

Why normalize_embeddings=True:
  - Cosine similarity needs normalized vectors
  - BGE recommended setting
"""

import json
import os
import time
from pathlib import Path
from tqdm import tqdm
from elasticsearch import Elasticsearch, helpers
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
load_dotenv()

# Config
ES_URL       = os.getenv("ES_URL", "http://localhost:9200")
INDEX_NAME   = "legal_rag"
JSONL_FILE   = "data/processed/okf_chunks.jsonl"
MODEL_NAME   = "BAAI/bge-base-en-v1.5"
BATCH_SIZE   = 32   # chunks per embedding batch
ES_BATCH     = 100  # chunks per ES bulk request

def load_chunks(filepath):
    """Load all chunks from JSONL file"""
    chunks = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    print(f"[OK] Loaded {len(chunks)} chunks from {filepath}")
    return chunks

def load_embedding_model():
    """
    Load BGE-base model locally.
    First run downloads ~400MB to ~/.cache/huggingface/
    Subsequent runs use cache.
    """
    print(f"Loading embedding model: {MODEL_NAME}")
    print("  (First run downloads ~400MB - please wait)")
    model = SentenceTransformer(MODEL_NAME)
    print(f"[OK] Model loaded: {MODEL_NAME}")
    print(f"  Embedding dims: {model.get_sentence_embedding_dimension()}")
    return model

def generate_embeddings(model, chunks, batch_size=BATCH_SIZE):
    """
    Generate embeddings in batches.

    Why normalize=True: cosine similarity needs unit vectors
    Why batch_size=32: CPU memory efficient
    Why BGE prefix: BGE model recommends query prefix for queries
    """
    texts = [chunk["text"] for chunk in chunks]

    print(f"\nGenerating embeddings for {len(texts)} chunks...")
    print(f"Batch size: {batch_size}")
    print(f"Estimated time: {len(texts)//batch_size * 2} seconds on CPU")

    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,  # required for cosine similarity
        show_progress_bar=True,
    )

    print(f"[OK] Generated {len(embeddings)} embeddings")
    print(f"  Shape: {embeddings.shape}")
    return embeddings

def index_to_elasticsearch(es, chunks, embeddings):
    """
    Bulk index chunks + embeddings to Elasticsearch.

    Why bulk:
      Single insert = 3497 requests = slow
      Bulk 100 = 35 requests = 10x faster
    """

    def generate_actions():
        for chunk, embedding in zip(chunks, embeddings):
            doc = {**chunk}  # copy all fields
            doc["embedding"] = embedding.tolist()  # add vector

            yield {
                "_index": INDEX_NAME,
                "_id": chunk["chunk_id"],
                "_source": doc
            }

    print(f"\nIndexing {len(chunks)} chunks to Elasticsearch...")
    print(f"Bulk batch size: {ES_BATCH}")

    success = 0
    failed = 0

    # Use helpers.bulk for efficient indexing
    for ok, result in helpers.streaming_bulk(
        es,
        generate_actions(),
        chunk_size=ES_BATCH,
        raise_on_error=False
    ):
        if ok:
            success += 1
        else:
            failed += 1
            print(f"  Failed: {result}")

    print(f"[OK] Indexed: {success} chunks")
    if failed:
        print(f"[ERR] Failed: {failed} chunks")

    return success, failed

def verify_index(es):
    """Quick verification - search for a test query"""

    # Count documents
    count = es.count(index=INDEX_NAME)
    print(f"\n[OK] Total docs in index: {count['count']}")

    # Test BM25 search
    result = es.search(
        index=INDEX_NAME,
        body={
            "query": {
                "match": {
                    "text": "gross income"
                }
            },
            "size": 3,
            "_source": ["chunk_id", "doc_title", "page_number", "doc_type"]
        }
    )

    print("\nTest BM25 Search: 'gross income'")
    print(f"Hits: {result['hits']['total']['value']}")
    for hit in result['hits']['hits']:
        src = hit['_source']
        print(f"  [{src['doc_type']}] {src['doc_title']} p.{src['page_number']} (score: {hit['_score']:.2f})")

    # Doc type distribution via aggregation
    result2 = es.search(
        index=INDEX_NAME,
        body={
            "query": {"match_all": {}},
            "size": 0,
            "aggs": {
                "by_type": {
                    "terms": {"field": "doc_type", "size": 10}
                }
            }
        }
    )

    print("\nDoc type distribution in index:")
    for bucket in result2['aggregations']['by_type']['buckets']:
        print(f"  {bucket['key']:12} : {bucket['doc_count']} chunks")

def main():
    print("=" * 60)
    print("P3 - Elasticsearch Indexing Pipeline")
    print("=" * 60)

    # Step 1: Connect to ES
    es = Elasticsearch(ES_URL)
    info = es.info()
    print(f"[OK] Connected to ES {info['version']['number']}")

    # Step 2: Load chunks
    chunks = load_chunks(JSONL_FILE)

    # Step 3: Load embedding model
    model = load_embedding_model()

    # Step 4: Generate embeddings
    start = time.time()
    embeddings = generate_embeddings(model, chunks)
    elapsed = time.time() - start
    print(f"  Time taken: {elapsed:.1f} seconds")

    # Step 5: Index to ES
    success, failed = index_to_elasticsearch(es, chunks, embeddings)

    # Step 6: Verify
    verify_index(es)

    print("\n" + "=" * 60)
    print("P3 COMPLETE")
    print("=" * 60)
    print(f"Chunks indexed: {success}/3497")
    print(f"Index name: {INDEX_NAME}")
    print(f"ES URL: {ES_URL}")
    print(f"Kibana: http://localhost:5601")
    print("\nNext: P4 - Hybrid Search (BM25 + Vector + RRF)")

if __name__ == "__main__":
    main()
