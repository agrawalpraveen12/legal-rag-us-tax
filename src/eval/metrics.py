"""
P8 - Evaluation Metrics for Legal RAG
=====================================
Contains calculations for:
1. Recall@k (pre-rerank & post-rerank)
2. Mean Reciprocal Rank (MRR)
3. Citation Accuracy (Answerable and Refusal)
4. Faithfulness (DeBERTa-v3 NLI Sentence Entailment)
5. Cohen's h (proportional effect size)
"""

import re
import numpy as np
from typing import List, Dict, Union, Tuple

# Global variables to cache the DeBERTa model
_nli_tokenizer = None
_nli_model = None
_device = None

def get_nli_model():
    """
    Lazy load and cache the DeBERTa NLI model and tokenizer.
    Ensures model is only loaded when needed.
    """
    global _nli_tokenizer, _nli_model, _device
    if _nli_model is None:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        
        model_name = "cross-encoder/nli-deberta-v3-base"
        print(f"Loading NLI model: {model_name}...")
        _nli_tokenizer = AutoTokenizer.from_pretrained(model_name)
        _nli_model = AutoModelForSequenceClassification.from_pretrained(model_name)
        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _nli_model.to(_device)
        _nli_model.eval()
        print(f"NLI model loaded on {_device}")
    return _nli_model, _nli_tokenizer, _device


def calculate_recall_at_k(
    retrieved_chunks: List[Dict],
    expected_doc_id: str,
    expected_page_no: int,
    k: int
) -> float:
    """
    Calculate Recall@k for a single query.
    Recall@k = 1.0 if the expected doc_id and page_no are in the top-k retrieved chunks, else 0.0.
    """
    expected_doc_id = expected_doc_id.strip().lower()
    expected_page_no = int(expected_page_no)
    
    # Check top k chunks
    for chunk in retrieved_chunks[:k]:
        source = chunk.get("source", chunk)
        chunk_doc_id = str(source.get("doc_id", "")).strip().lower()
        chunk_page = source.get("page_number")
        
        if chunk_page is not None:
            try:
                chunk_page = int(chunk_page)
            except (ValueError, TypeError):
                continue
            
            if chunk_doc_id == expected_doc_id and chunk_page == expected_page_no:
                return 1.0
                
    return 0.0


def calculate_mrr(
    retrieved_chunks: List[Dict],
    expected_doc_id: str,
    expected_page_no: int
) -> float:
    """
    Calculate Reciprocal Rank (RR) for a single query.
    RR = 1 / rank (1-indexed) of the first matching chunk, else 0.0.
    """
    expected_doc_id = expected_doc_id.strip().lower()
    expected_page_no = int(expected_page_no)
    
    for idx, chunk in enumerate(retrieved_chunks):
        source = chunk.get("source", chunk)
        chunk_doc_id = str(source.get("doc_id", "")).strip().lower()
        chunk_page = source.get("page_number")
        
        if chunk_page is not None:
            try:
                chunk_page = int(chunk_page)
            except (ValueError, TypeError):
                continue
                
            if chunk_doc_id == expected_doc_id and chunk_page == expected_page_no:
                return 1.0 / (idx + 1)
                
    return 0.0


def _sig_words(t: str) -> set:
    """Significant words: lowercase, split on non-alphanumeric incl. underscore, >2 chars."""
    t = re.sub(r'[\W_]+', ' ', t.lower())
    return {w for w in t.split() if len(w) > 2}


def _fuzzy_doc_match(cite_doc_id: str, cite_title: str, expected_doc_id: str) -> bool:
    """
    True if either:
      - cite_doc_id exactly equals expected_doc_id, OR
      - the extracted citation title shares >= 2 significant words with the expected_doc_id string.
    """
    if cite_doc_id and cite_doc_id == expected_doc_id:
        return True
    overlap = len(_sig_words(cite_title) & _sig_words(expected_doc_id))
    return overlap >= 2


def calculate_citation_accuracy(
    generated_citations: List[Dict],
    expected_doc_id: str,
    expected_page_no: int,
    is_answerable: bool,
    is_refused: bool
) -> float:
    """
    Calculate Citation Accuracy for a single query.
    - If the query is unanswerable:
        Returns 1.0 if the LLM correctly refused (is_refused = True) and no citations are generated, else 0.0.
    - If the query is answerable:
        Returns 1.0 if the expected citation (doc_id and page_no) is present in the generated citations, else 0.0.
    Uses fuzzy doc matching: exact doc_id OR title-word overlap >= 2 against expected_doc_id.
    """
    expected_doc_id = expected_doc_id.strip().lower()
    expected_page_no = int(expected_page_no)

    if not is_answerable:
        # Expected behavior: refusal
        if is_refused and not generated_citations:
            return 1.0
        return 0.0
    else:
        # Expected behavior: correct citation in output
        if is_refused:
            return 0.0

        for citation in generated_citations:
            cite_doc_id   = str(citation.get("doc_id", "")).strip().lower()
            cite_title    = str(citation.get("cited_title") or citation.get("doc_title", "")).strip()
            cite_page     = citation.get("page_number")

            if cite_page is not None:
                try:
                    cite_page = int(cite_page)
                except (ValueError, TypeError):
                    continue

                if _fuzzy_doc_match(cite_doc_id, cite_title, expected_doc_id) and cite_page == expected_page_no:
                    return 1.0
        return 0.0


def calculate_faithfulness(
    answer_text: str,
    retrieved_chunks: List[Dict]
) -> float:
    """
    Calculate Faithfulness using DeBERTa NLI sentence entailment.

    Each answer sentence is checked against EACH retrieved chunk individually.
    A sentence is considered entailed if ANY chunk entails it above the threshold.

    Previous approach concatenated all chunks into one premise (~6400 tokens), then
    truncated to 512 — meaning only ~8% of context was seen by the NLI model.
    Per-chunk checking fits each (chunk ~600 words, sentence) pair within 512 tokens,
    utilizing ~57% of each chunk and all 8 chunks.

    - Correct refusals: automatically 1.0 (no claims to verify).
    - Returns: (entailed sentences) / (total sentences).
    """
    if answer_text.strip().startswith("INSUFFICIENT_CONTEXT"):
        return 1.0

    # Collect chunk texts
    chunk_texts = []
    for chunk in retrieved_chunks:
        source = chunk.get("source", chunk)
        text = source.get("text", "")
        if text and text.strip():
            chunk_texts.append(text.strip())

    if not chunk_texts:
        return 0.0

    # Remove the "Sources:" section (everything from "Sources:" to end).
    # These lines are citation headers/list items, not factual claims — they
    # would score near-zero entailment and artificially deflate faithfulness.
    answer_body = re.split(r'\n\s*Sources\s*:', answer_text, maxsplit=1, flags=re.IGNORECASE)[0]

    # Strip bracketed citations before sentence splitting
    cleaned_answer = re.sub(r'\[[^\]]+\]', '', answer_body)
    cleaned_answer = re.sub(r'\s+', ' ', cleaned_answer)

    # Split into sentences (handle common legal abbreviations to avoid false splits)
    abbreviations = {
        'etc', 'eg', 'ie', 'v', 'vs', 'inc', 'co', 'corp', 'l', 'p',
        'sec', 'pub', 'art', 'al', 'dr', 'mr', 'mrs', 'ms', 'u.s', 'u.s.a'
    }
    raw_sentences = re.split(r'(?<=\.|\?)\s+(?=[A-Z])', cleaned_answer)

    sentences = []
    temp_sentence = ""
    for s in raw_sentences:
        s = s.strip()
        if not s:
            continue
        temp_sentence = (temp_sentence + " " + s).strip() if temp_sentence else s
        words = temp_sentence.split()
        if words:
            last_word = words[-1].lower().rstrip('.?,;')
            if last_word in abbreviations or (len(last_word) == 1 and last_word.isalpha()):
                continue
        sentences.append(temp_sentence)
        temp_sentence = ""
    if temp_sentence:
        sentences.append(temp_sentence)

    # Clean up sentences
    cleaned_sentences = []
    for s in sentences:
        s = re.sub(r'\s+', ' ', s)
        s = re.sub(r'\s+([.,?])', r'\1', s)
        s = s.strip(" .,;and")
        if len(s) > 5:
            cleaned_sentences.append(s)

    if not cleaned_sentences:
        return 1.0

    # Load NLI model
    model, tokenizer, device = get_nli_model()
    import torch

    id2label = model.config.id2label
    entail_idx = None
    for k, v in id2label.items():
        if "entail" in v.lower():
            entail_idx = int(k)
            break
    if entail_idx is None:
        entail_idx = 2  # standard: [contradiction=0, neutral=1, entailment=2]

    entailed_count = 0

    # For each sentence, check against every chunk and take the max entailment score.
    # Truncate only the premise (chunk) so the full hypothesis (sentence) is always seen.
    for sentence in cleaned_sentences:
        max_entail_prob = 0.0
        try:
            pairs = [[ct, sentence] for ct in chunk_texts]
            inputs = tokenizer(
                pairs,
                padding=True,
                truncation="only_first",   # truncate premise (chunk), keep full sentence
                max_length=512,
                return_tensors="pt",
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = model(**inputs)
                probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()
            max_entail_prob = float(max(p[entail_idx] for p in probs))
        except Exception as e:
            print(f"NLI error on sentence: {e}")
            continue

        if max_entail_prob > 0.15:
            entailed_count += 1

    return float(entailed_count) / len(cleaned_sentences)


def calculate_faithfulness_llm(
    answer_text: str,
    retrieved_chunks: List[Dict],
) -> float:
    """
    LLM-as-judge faithfulness: one Groq API call per query.

    Batches all answer sentences against the top-4 retrieved chunks in a single prompt.
    More accurate than DeBERTa NLI for legal text — handles paraphrase and legal synonyms
    that NLI scores as neutral even when genuinely supported by the source.

    Returns (supported sentences) / (total sentences).
    Uses llama-3.1-8b-instant (8B, cheap) — YES/NO classification doesn't need 70B.
    """
    if answer_text.strip().startswith("INSUFFICIENT_CONTEXT"):
        return 1.0

    # Top-4 chunks keep the prompt within 8B context limits
    chunk_texts = []
    for chunk in retrieved_chunks[:4]:
        source = chunk.get("source", chunk)
        text = source.get("text", "")
        if text and text.strip():
            chunk_texts.append(text.strip()[:800])

    if not chunk_texts:
        return 0.0

    # Strip Sources section and bracketed citations
    answer_body = re.split(r'\n\s*Sources\s*:', answer_text, maxsplit=1, flags=re.IGNORECASE)[0]
    cleaned_answer = re.sub(r'\[[^\]]+\]', '', answer_body)
    cleaned_answer = re.sub(r'\s+', ' ', cleaned_answer).strip()

    # Sentence splitting (same logic as calculate_faithfulness)
    abbreviations = {
        'etc', 'eg', 'ie', 'v', 'vs', 'inc', 'co', 'corp', 'l', 'p',
        'sec', 'pub', 'art', 'al', 'dr', 'mr', 'mrs', 'ms', 'u.s', 'u.s.a'
    }
    raw_sentences = re.split(r'(?<=\.|\?)\s+(?=[A-Z])', cleaned_answer)
    sentences = []
    temp = ""
    for s in raw_sentences:
        s = s.strip()
        if not s:
            continue
        temp = (temp + " " + s).strip() if temp else s
        words = temp.split()
        if words:
            last = words[-1].lower().rstrip('.?,;')
            if last in abbreviations or (len(last) == 1 and last.isalpha()):
                continue
        sentences.append(temp)
        temp = ""
    if temp:
        sentences.append(temp)

    sentences = [re.sub(r'\s+', ' ', s).strip(" .,;and") for s in sentences]
    sentences = [s for s in sentences if len(s) > 5]

    if not sentences:
        return 1.0

    # Single LLM call: all sentences evaluated against all top-4 chunks at once
    context_block = "\n\n".join(
        f"[Chunk {i+1}]\n{ct}" for i, ct in enumerate(chunk_texts)
    )
    claims_block = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sentences))

    system_prompt = (
        "You are a faithfulness evaluator for a legal RAG system. "
        "Given source context chunks and a list of claims, determine which claims "
        "are directly supported by the context (stated or logically implied by any chunk). "
        f"Return exactly {len(sentences)} lines in format '1: YES' or '1: NO'."
    )
    user_msg = (
        f"SOURCE CONTEXT:\n{context_block}\n\n"
        f"CLAIMS:\n{claims_block}\n\n"
        "Evaluate each claim (YES/NO, one per line):"
    )

    try:
        try:
            from config import groq_call_with_rotation
        except ImportError:
            from src.config import groq_call_with_rotation

        response = groq_call_with_rotation(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            model="llama-3.1-8b-instant",
            max_tokens=len(sentences) * 15 + 50,
            temperature=0.0,
        )
        lines = [l.strip() for l in response.strip().split('\n') if l.strip()]
        supported_indices = set()
        for line in lines:
            m = re.match(r'^(\d+)[:\.\)]\s*(YES|NO)', line, re.IGNORECASE)
            if m and m.group(2).upper() == "YES":
                idx = int(m.group(1))
                if 1 <= idx <= len(sentences):
                    supported_indices.add(idx)
        return float(len(supported_indices)) / len(sentences)
    except Exception as e:
        print(f"LLM faithfulness error: {e}, falling back to 0.0")
        return 0.0


def calculate_cohens_h(p1: float, p2: float) -> float:
    """
    Calculate Cohen's h to compare two proportions:
    h = 2 * arcsin(sqrt(p1)) - 2 * arcsin(sqrt(p2))
    
    Clips proportions to [0.0, 1.0] to avoid mathematical domain errors.
    """
    p1 = max(0.0, min(1.0, float(p1)))
    p2 = max(0.0, min(1.0, float(p2)))
    
    h = 2 * np.arcsin(np.sqrt(p1)) - 2 * np.arcsin(np.sqrt(p2))
    return float(h)
