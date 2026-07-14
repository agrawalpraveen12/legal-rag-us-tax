from sentence_transformers import SentenceTransformer, CrossEncoder
from transformers import AutoTokenizer, AutoModelForSequenceClassification

print("Downloading embedding model...")
SentenceTransformer("BAAI/bge-base-en-v1.5")

print("Downloading reranker model...")
CrossEncoder("BAAI/bge-reranker-base")

print("Downloading NLI model...")
AutoTokenizer.from_pretrained("cross-encoder/nli-deberta-v3-base")
AutoModelForSequenceClassification.from_pretrained("cross-encoder/nli-deberta-v3-base")

print("All models downloaded.")
