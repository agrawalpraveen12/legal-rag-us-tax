"""
Central config + 4-key round-robin Groq rotation.
Import groq_call_with_rotation() anywhere instead of
instantiating Groq clients directly.
"""

import os
import time
from dotenv import load_dotenv
load_dotenv()

# --- 4-key pool --------------------------------------------------

GROQ_KEYS = [
    os.getenv("GROQ_API_KEY_PRIMARY"),
    os.getenv("GROQ_API_KEY_FALLBACK"),
    os.getenv("GROQ_API_KEY_3"),
    os.getenv("GROQ_API_KEY_4"),
]
GROQ_KEYS = [k for k in GROQ_KEYS if k]   # drop unset

_key_index = 0


def get_next_groq_key() -> str:
    global _key_index
    key = GROQ_KEYS[_key_index % len(GROQ_KEYS)]
    _key_index += 1
    return key


def groq_call_with_rotation(
    messages: list,
    model: str = None,
    max_tokens: int = 1000,
    temperature: float = 0.1,
    response_format: dict = None,
) -> str:
    """
    Call Groq, rotating through all keys on rate-limit / quota errors.
    Returns the raw content string.

    Why round-robin, not fallback-only:
      Each free key has 100k TPD (tokens/day) on 70B.
      4 keys = 400k TPD total.
      Rotating spreads load evenly so no single key exhausts first.
    """
    from groq import Groq

    if model is None:
        model = os.getenv("GROQ_MODEL_PRIMARY", "llama-3.3-70b-versatile")

    kwargs = dict(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if response_format is not None:
        kwargs["response_format"] = response_format

    for attempt in range(len(GROQ_KEYS)):
        key = get_next_groq_key()
        try:
            client = Groq(api_key=key)
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            error = str(e).lower()
            if "rate_limit" in error or "429" in error or "quota" in error:
                print(f"  Key {attempt+1}/{len(GROQ_KEYS)} rate limited, trying next...")
                continue
            else:
                raise

    # All keys exhausted
    print(f"  All {len(GROQ_KEYS)} keys exhausted. Waiting 60s...")
    time.sleep(60)
    return groq_call_with_rotation(messages, model, max_tokens, temperature, response_format)


# --- Other config ------------------------------------------------

ES_URL              = os.getenv("ES_URL",              "http://localhost:9200")
ES_USERNAME         = os.getenv("ES_USERNAME",         "elastic")
ES_PASSWORD         = os.getenv("ES_PASSWORD",         "legal_rag_2024")
DATA_RAW_DIR        = os.getenv("DATA_RAW_DIR",        "data/raw")
DATA_PROCESSED_DIR  = os.getenv("DATA_PROCESSED_DIR",  "data/processed")
EMBEDDING_MODEL     = os.getenv("EMBEDDING_MODEL",     "BAAI/bge-base-en-v1.5")
RERANKER_MODEL      = os.getenv("RERANKER_MODEL",      "BAAI/bge-reranker-base")
GROQ_MODEL_PRIMARY  = os.getenv("GROQ_MODEL_PRIMARY",  "llama-3.3-70b-versatile")
GROQ_MODEL_FAST     = os.getenv("GROQ_MODEL_FAST",     "llama-3.1-8b-instant")
TOP_K_RETRIEVE      = int(os.getenv("TOP_K_RETRIEVE",  50))
TOP_K_RERANK        = int(os.getenv("TOP_K_RERANK",    8))
CHUNK_SIZE          = int(os.getenv("CHUNK_SIZE",      600))
CHUNK_OVERLAP       = int(os.getenv("CHUNK_OVERLAP",   100))
