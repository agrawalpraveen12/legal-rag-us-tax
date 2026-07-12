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
            cite_doc_id = str(citation.get("doc_id", "")).strip().lower()
            cite_page = citation.get("page_number")
            
            if cite_page is not None:
                try:
                    cite_page = int(cite_page)
                except (ValueError, TypeError):
                    continue
                    
                if cite_doc_id == expected_doc_id and cite_page == expected_page_no:
                    return 1.0
        return 0.0


def calculate_faithfulness(
    answer_text: str,
    retrieved_chunks: List[Dict]
) -> float:
    """
    Calculate Faithfulness using DeBERTa NLI sentence entailment.
    Each sentence of the answer must be entailed by the retrieved context.
    - Correct refusals are automatically marked 1.0 (no claims made, so 100% faithful).
    - Otherwise, computes: (number of entailed sentences) / (total sentences).
    """
    if answer_text.strip().startswith("INSUFFICIENT_CONTEXT"):
        return 1.0
        
    # Concatenate the text of the retrieved chunks to build the premise (context)
    premise_parts = []
    for chunk in retrieved_chunks:
        source = chunk.get("source", chunk)
        text = source.get("text", "")
        if text:
            premise_parts.append(text)
            
    premise = "\n".join(premise_parts).strip()
    if not premise:
        return 0.0
        
    # Preprocess text to strip bracketed citations to clean the claims
    cleaned_answer = re.sub(r'\[[^\]]+\]', '', answer_text)
    cleaned_answer = re.sub(r'\s+', ' ', cleaned_answer)
    
    # Split the answer into sentences (ignoring common abbreviations like sec., p., v., Inc.)
    abbreviations = ['etc', 'eg', 'ie', 'v', 'vs', 'inc', 'co', 'corp', 'l', 'p', 'sec', 'pub', 'art', 'al', 'dr', 'mr', 'mrs', 'ms', 'u.s', 'u.s.a']
    raw_sentences = re.split(r'(?<=\.|\?)\s+(?=[A-Z])', cleaned_answer)
    
    sentences = []
    temp_sentence = ""
    for s in raw_sentences:
        s = s.strip()
        if not s:
            continue
        if temp_sentence:
            temp_sentence += " " + s
        else:
            temp_sentence = s
            
        words = temp_sentence.split()
        if words:
            last_word = words[-1].lower().rstrip('.?,;')
            if last_word in abbreviations or (len(last_word) == 1 and last_word.isalpha()):
                continue
        sentences.append(temp_sentence)
        temp_sentence = ""
        
    if temp_sentence:
        sentences.append(temp_sentence)
        
    # Clean sentences: remove trailing/leading spaces, punctuation left by removing citations, etc.
    cleaned_sentences = []
    for s in sentences:
        s = re.sub(r'\s+', ' ', s)
        s = re.sub(r'\s+([.,?])', r'\1', s)
        s = s.strip(" .,;and")
        if len(s) > 5:
            cleaned_sentences.append(s)
            
    if not cleaned_sentences:
        return 1.0
        
    # Load model and determine labels dynamically
    model, tokenizer, device = get_nli_model()
    import torch
    
    id2label = model.config.id2label
    entail_idx = None
    for k, v in id2label.items():
        if "entail" in v.lower():
            entail_idx = int(k)
            break
            
    if entail_idx is None:
        entail_idx = 1  # Standard fallback
        
    # Run predictions in a batch
    pairs = [[premise, s] for s in cleaned_sentences]
    
    try:
        inputs = tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()
            
        entailed_count = 0
        for prob in probs:
            if prob[entail_idx] > 0.4:
                entailed_count += 1
                
        return float(entailed_count) / len(cleaned_sentences)
    except Exception as e:
        print(f"Error during NLI faithfulness check: {e}")
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
