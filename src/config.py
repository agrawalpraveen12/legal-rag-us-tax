import os
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ES_URL = os.getenv("ES_URL", "http://localhost:9200")
DATA_RAW_DIR = "data/raw"
DATA_PROCESSED_DIR = "data/processed"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
RERANKER_MODEL = "BAAI/bge-reranker-base"
GROQ_MODEL = "llama-3.3-70b-versatile"
TOP_K_RETRIEVE = 50
TOP_K_RERANK = 8
