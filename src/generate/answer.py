"""
P7 - LLM Generation with Citations
=====================================
Model: Groq LLaMA 3.3 70B
Temperature: 0.1 (deterministic legal answers)
Strategy:
  - Answer ONLY from retrieved context
  - Every claim must cite [doc_title, p.N]
  - Refuse if answer not in context
  - Never hallucinate

Why temperature=0.1:
  Legal answers must be deterministic
  Same query = same answer every time
  0.0 too rigid, 0.1 allows slight phrasing variation

Why cite-or-refuse:
  Legal system = every claim needs source
  Hallucinated citation = malpractice risk
  Better to say "not found" than guess
"""

import os
import re
import json
import time
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import groq_call_with_rotation, GROQ_KEYS, GROQ_MODEL_FAST
GROQ_MODEL = GROQ_MODEL_FAST  # llama-3.1-8b-instant — higher TPM limits

# --- PROMPTS -------------------------------------------------

SYSTEM_PROMPT = """You are a precise US tax law research assistant.

STRICT RULES:
1. Answer ONLY using the provided legal context below
2. After EVERY claim, add citation: [Document Title, p.PAGE_NUMBER]
3. If the answer is NOT in the context, respond with exactly:
   "INSUFFICIENT_CONTEXT: The provided documents do not contain enough information to answer this question."
4. Never use external knowledge
5. Never guess or infer beyond what is explicitly stated
6. Use exact legal terminology from the source text

CITATION FORMAT:
- Single source: [IRC Section 162, p.3]
- Multiple sources: [IRC Section 162, p.3] and [Welch v. Helvering, p.2]

ANSWER FORMAT:
- Start directly with the answer
- Keep answers concise but complete
- End with a "Sources:" section listing all cited documents"""


def build_context(retrieved_chunks: list) -> str:
    """
    Format retrieved chunks into context for LLM.
    Each chunk clearly labeled with source for citation.
    """
    context_parts = []

    for i, chunk in enumerate(retrieved_chunks, 1):
        source    = chunk.get('source', chunk)
        doc_title = source.get('doc_title', 'Unknown')
        page_num  = source.get('page_number', '?')
        doc_type  = source.get('doc_type', '')
        text      = source.get('text', '')
        section   = source.get('section_ref', '')

        header = f"[CONTEXT {i}] {doc_title} | Page {page_num}"
        if section:
            header += f" | {section}"

        context_parts.append(f"{header}\n{text}")

    return "\n\n" + "=" * 50 + "\n\n".join(context_parts)


def generate_answer(
    query: str,
    retrieved_chunks: list,
) -> dict:
    """
    Generate grounded answer with citations from retrieved chunks.

    Returns:
      answer: str (cited answer or INSUFFICIENT_CONTEXT)
      citations: list of {doc_title, page_number, doc_id}
      model: str
      tokens_used: int
    """
    context = build_context(retrieved_chunks)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": (
            f"LEGAL CONTEXT:\n{context}\n\n"
            f"QUESTION: {query}\n\n"
            "Provide a precise answer with citations from the context above."
        )}
    ]

    try:
        answer_text = groq_call_with_rotation(
            messages,
            model=GROQ_MODEL,
            max_tokens=800,
            temperature=0.1,
        ).strip()

        citations  = extract_citations(answer_text, retrieved_chunks)
        is_refused = answer_text.startswith("INSUFFICIENT_CONTEXT")

        return {
            "answer":      answer_text,
            "citations":   citations,
            "is_refused":  is_refused,
            "model":       GROQ_MODEL,
            "tokens_used": 0,   # not exposed by rotation helper
            "chunks_used": len(retrieved_chunks),
            "keys_available": len(GROQ_KEYS),
        }

    except Exception as e:
        return {
            "answer":      f"ERROR: {str(e)}",
            "citations":   [],
            "is_refused":  False,
            "model":       GROQ_MODEL,
            "tokens_used": 0,
            "chunks_used": len(retrieved_chunks),
            "keys_available": len(GROQ_KEYS),
        }


def extract_citations(answer_text: str, chunks: list) -> list:
    """
    Extract which chunks were actually cited in the answer.
    Handles formats: [Title (Year), Page N], [Title, p.N], [Title | Page N], [Title, Page N]
    """
    # Patterns ordered most-specific first; all capture (title, page_number)
    patterns = [
        r'\[([^\]]+?)\s*\(\d{4}\),\s*[Pp]age\s*(\d+)\]',   # [Title (Year), Page N]
        r'\[([^\]]+?)\s*\(\d{4}\),\s*p\.?\s*(\d+)\]',        # [Title (Year), p.N]
        r'\[([^\]]+),\s*p\.?\s*(\d+)\]',                      # [Title, p.N]
        r'\[([^\]]+)\|\s*[Pp]age\s*(\d+)\]',                  # [Title | Page N]
        r'\[([^\]]+),\s*[Pp]age\s*(\d+)\]',                   # [Title, Page N]
    ]

    def _clean_title(t: str) -> str:
        t = re.sub(r'\s*\(\d{4}\)\s*$', '', t)   # strip trailing (Year)
        t = re.sub(r',\s*$', '', t)               # strip trailing comma
        return t.strip()

    def _sig_words(t: str) -> set:
        """Significant words: lowercase, split on non-alphanumeric incl. underscore, >2 chars."""
        t = re.sub(r'[\W_]+', ' ', t.lower())
        return {w for w in t.split() if len(w) > 2}

    # Collect unique (clean_title, page) pairs
    seen_keys: set = set()
    all_matches: list = []
    for pat in patterns:
        for raw_title, page_str in re.findall(pat, answer_text):
            clean = _clean_title(raw_title)
            key = (clean.lower(), page_str)
            if key not in seen_keys:
                seen_keys.add(key)
                all_matches.append((clean, page_str))

    citations = []
    for doc_title_partial, page_str in all_matches:
        title_words = _sig_words(doc_title_partial)
        best_chunk = None
        best_overlap = 0

        for chunk in chunks:
            source     = chunk.get('source', chunk)
            chunk_title = source.get('doc_title', '')
            chunk_page  = source.get('page_number', 0)

            # Page must match exactly
            try:
                if int(chunk_page) != int(page_str):
                    continue
            except (ValueError, TypeError):
                continue

            # Word-overlap fuzzy title match
            overlap = len(title_words & _sig_words(chunk_title))
            if overlap > best_overlap:
                best_overlap = overlap
                best_chunk = (source, chunk_title, chunk_page)

        if best_chunk and best_overlap >= 2:
            source, chunk_title, chunk_page = best_chunk
            citations.append({
                "doc_id":      source.get('doc_id', ''),
                "doc_title":   chunk_title,
                "cited_title": doc_title_partial,
                "page_number": int(chunk_page),
                "doc_type":    source.get('doc_type', ''),
                "section_ref": source.get('section_ref', ''),
            })
        else:
            # Keep the citation even without a chunk match so metrics can fuzzy-match
            try:
                page_int = int(page_str)
            except (ValueError, TypeError):
                page_int = 0
            citations.append({
                "doc_id":      '',
                "doc_title":   doc_title_partial,
                "cited_title": doc_title_partial,
                "page_number": page_int,
                "doc_type":    '',
                "section_ref": '',
            })

    # Deduplicate on (doc_id or title, page)
    seen: set = set()
    unique_citations = []
    for c in citations:
        key = f"{c['doc_id'] or c['doc_title'][:30]}_{c['page_number']}"
        if key not in seen:
            seen.add(key)
            unique_citations.append(c)

    return unique_citations


# --- FULL RAG PIPELINE ---------------------------------------

def rag_pipeline(query: str) -> dict:
    """
    Complete RAG pipeline:
    Query -> Hybrid Search -> Rerank -> Generate -> Cited Answer
    """
    from retrieve.hybrid import hybrid_search
    from retrieve.rerank import retrieve_and_rerank

    # Step 1: Hybrid search
    hybrid_results = hybrid_search(query, rewrite=True)

    # Step 2: Rerank
    reranked = retrieve_and_rerank(query, hybrid_results)

    # Step 3: Generate
    result = generate_answer(query, reranked)

    return {
        "query":           query,
        "rewritten_query": hybrid_results.get("rewritten_query", query),
        "answer":          result["answer"],
        "citations":       result["citations"],
        "is_refused":      result["is_refused"],
        "tokens_used":     result["tokens_used"],
        "chunks_used":     result["chunks_used"],
        "top_chunks":      reranked[:3]
    }


if __name__ == "__main__":
    test_queries = [
        # Factual
        "What items are included in gross income under IRC Section 61?",
        # Interpretive
        "How did the Supreme Court define ordinary and necessary in Welch v Helvering?",
        # Multi-hop
        "Which IRC section does Bob Jones University case interpret and what are its requirements?",
        # Unanswerable
        "What is the corporate tax rate in the United Kingdom?",
    ]

    print("=" * 60)
    print("P7 - LLM Generation Test")
    print("=" * 60)

    for query in test_queries:
        print(f"\n{'-'*60}")
        print(f"QUERY: {query}")
        print(f"{'-'*60}")

        result = rag_pipeline(query)

        print(f"Rewritten: {result['rewritten_query']}")
        print(f"\nANSWER:")
        print(result['answer'])

        if result['citations']:
            print(f"\nCITATIONS ({len(result['citations'])}):")
            for c in result['citations']:
                print(f"  [{c['doc_type']}] {c['doc_title']} p.{c['page_number']}")

        print(f"\nRefused:  {result['is_refused']}")
        print(f"Tokens:   {result['tokens_used']}")

        time.sleep(3)

    print("\n" + "=" * 60)
    print("P7 COMPLETE")
    print("Next: P8 - Evaluation against Golden Set")
