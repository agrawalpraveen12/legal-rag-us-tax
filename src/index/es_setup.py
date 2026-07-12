"""
P3 - Elasticsearch Index Setup
================================
Index name: legal_rag
Mappings:
  - text field: BM25 (default analyzer)
  - embedding field: dense_vector 768 dims (BGE-base)
  - metadata fields: doc_type, page_number, section_ref etc.

Why single index:
  RRF combines BM25 + kNN in one query - needs same index
  Separate index = 2 queries + manual fusion = complex
"""

from elasticsearch import Elasticsearch
import os
from dotenv import load_dotenv
load_dotenv()

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
INDEX_NAME = "legal_rag"

def get_es_client():
    return Elasticsearch(ES_URL)

def create_index(es, force_recreate=False):
    """
    Create legal_rag index with hybrid search mappings.

    Why 768 dims: BGE-base-en-v1.5 output dimension
    Why cosine similarity: standard for semantic search
    Why m=16, ef_construction=100:
      HNSW params - balance of speed vs accuracy
      m=16: connections per node (higher = more accurate, more RAM)
      ef_construction=100: build time accuracy
    """

    if es.indices.exists(index=INDEX_NAME):
        if force_recreate:
            es.indices.delete(index=INDEX_NAME)
            print(f"Deleted existing index: {INDEX_NAME}")
        else:
            print(f"Index {INDEX_NAME} already exists. Use force_recreate=True to recreate.")
            return False

    mappings = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "legal_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "stop",
                            "snowball"
                        ]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                # Primary search field - BM25
                "text": {
                    "type": "text",
                    "analyzer": "legal_analyzer",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256
                        }
                    }
                },

                # Vector field - semantic search
                # Why 768: BGE-base output dimensions
                # Why cosine: standard for normalized embeddings
                "embedding": {
                    "type": "dense_vector",
                    "dims": 768,
                    "index": True,
                    "similarity": "cosine",
                    "index_options": {
                        "type": "hnsw",
                        "m": 16,
                        "ef_construction": 100
                    }
                },

                # Metadata fields for filtering
                "chunk_id":    {"type": "keyword"},
                "doc_id":      {"type": "keyword"},
                "doc_type":    {"type": "keyword"},
                "doc_title":   {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "page_number": {"type": "integer"},
                "chunk_index": {"type": "integer"},
                "word_count":  {"type": "integer"},
                "section_ref": {"type": "keyword"},
                "source_url":  {"type": "keyword"},
                "jurisdiction":{"type": "keyword"},
                "date":        {"type": "keyword"},
                "local_path":  {"type": "keyword"},
            }
        }
    }

    es.indices.create(index=INDEX_NAME, body=mappings)
    print(f"[OK] Created index: {INDEX_NAME}")
    print(f"  - BM25 field: text (legal_analyzer)")
    print(f"  - Vector field: embedding (768 dims, cosine, HNSW)")
    print(f"  - Metadata: doc_type, page_number, section_ref etc.")
    return True

if __name__ == "__main__":
    es = get_es_client()

    # Test connection
    info = es.info()
    print(f"ES Version: {info['version']['number']}")
    print(f"Cluster: {info['cluster_name']}")

    # Create index
    create_index(es, force_recreate=True)

    # Verify
    mapping = es.indices.get_mapping(index=INDEX_NAME)
    print(f"\n[OK] Index verified: {INDEX_NAME}")
