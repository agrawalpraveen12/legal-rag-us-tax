"""
P6 - Golden Dataset Generator
================================
Strategy:
1. Sample chunks from corpus (stratified by doc_type)
2. For each chunk, ask Groq 70B to generate Q&A pair
3. Auto-fill metadata (source_doc, page_no, section_ref)
4. Save as Excel with all required columns

Why Groq 70B (not 8B):
  Golden set quality = evaluation quality
  70B generates more accurate, nuanced legal Q&A
  Worth spending tokens on this one-time generation

Why stratified sampling:
  30/30/30/10 split must be maintained
  Random sampling would give too many tax chunks (1571 > others)
"""

import os
import json
import time
import random
import pandas as pd
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

# Config
GROQ_KEY_PRIMARY  = os.getenv("GROQ_API_KEY_PRIMARY")
GROQ_KEY_FALLBACK = os.getenv("GROQ_API_KEY_FALLBACK")
JSONL_FILE   = "data/processed/okf_chunks.jsonl"
OUTPUT_EXCEL = "data/golden/golden_set.xlsx"
CHECKPOINT   = "data/golden/checkpoint.json"
os.makedirs("data/golden", exist_ok=True)

# Distribution: 30/30/30/10
TARGET_COUNTS = {
    "act":      30,
    "judgment": 30,
    "pov":      30,
    "tax":      10
}

# Difficulty distribution per type
DIFFICULTY_DIST = {
    "factual":       40,
    "interpretive":  30,
    "multi_hop":     20,
    "unanswerable":  10
}

def get_groq_client(use_fallback=False):
    key = GROQ_KEY_FALLBACK if use_fallback else GROQ_KEY_PRIMARY
    return Groq(api_key=key)

def load_chunks():
    """Load and group chunks by doc_type"""
    chunks_by_type = {
        "act": [], "judgment": [], "pov": [], "tax": []
    }

    with open(JSONL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunk = json.loads(line)
                doc_type = chunk.get("doc_type")
                if doc_type in chunks_by_type:
                    chunks_by_type[doc_type].append(chunk)

    for t, chunks in chunks_by_type.items():
        print(f"  {t:10}: {len(chunks)} chunks available")

    return chunks_by_type

def sample_chunks(chunks_by_type):
    """
    Stratified sampling - one chunk per unique document.
    Ensures coverage across all 101 documents.
    """
    sampled = []

    for doc_type, target in TARGET_COUNTS.items():
        chunks = chunks_by_type[doc_type]

        # Group by doc_id
        by_doc = {}
        for chunk in chunks:
            doc_id = chunk["doc_id"]
            if doc_id not in by_doc:
                by_doc[doc_id] = []
            by_doc[doc_id].append(chunk)

        # Sample one chunk per doc, then fill target
        selected = []
        doc_ids = list(by_doc.keys())
        random.shuffle(doc_ids)

        for doc_id in doc_ids:
            if len(selected) >= target:
                break
            # Pick chunk from middle of doc (more content than first page)
            doc_chunks = by_doc[doc_id]
            mid = len(doc_chunks) // 2
            selected.append(doc_chunks[mid])

        sampled.extend(selected[:target])
        print(f"  Sampled {len(selected[:target])} {doc_type} chunks")

    return sampled

def generate_qa_pair(chunk, difficulty, use_fallback=False):
    """
    Generate Q&A pair from chunk using Groq 70B.

    Why temperature=0.3 for generation (not 0.1):
      Need some creativity in question formulation
      But answers must stay faithful to text
      0.3 = good balance
    """

    system_prompt = """You are a US tax law expert creating evaluation questions.
Generate a question and answer based ONLY on the provided legal text.

Rules:
1. Question must be answerable from the text provided
2. Answer must be grounded in the text - no external knowledge
3. Include the exact page number and document title in your response
4. Be precise with legal terminology

Respond in this exact JSON format:
{
  "question": "...",
  "answer": "...",
  "key_terms": ["term1", "term2"],
  "confidence": "high/medium/low"
}"""

    difficulty_prompts = {
        "factual": """Generate a FACTUAL question with a direct, specific answer.
Example: "What items does IRC section 61 include in gross income?"
The answer should be findable in 1-2 sentences from the text.""",

        "interpretive": """Generate an INTERPRETIVE question requiring legal analysis.
Example: "How did the court define 'ordinary' in the context of business expenses?"
The answer requires understanding the legal reasoning, not just facts.""",

        "multi_hop": """Generate a MULTI-HOP question that requires connecting
two concepts in the text.
Example: "What standard does section 162 set, and how does this relate to capital expenditures?"
The answer should reference multiple parts of the legal text.""",

        "unanswerable": """Generate a question that CANNOT be answered from this text.
The question should seem related but the answer is not in the provided passage.
Example: "What is the tax rate in California for this type of income?"
Return answer as: "This information is not available in the provided legal text."
Set confidence to: "unanswerable" """
    }

    user_prompt = f"""Document: {chunk['doc_title']}
Type: {chunk['doc_type']}
Page: {chunk['page_number']}
Section: {chunk.get('section_ref', 'N/A')}

Legal Text:
{chunk['text'][:1500]}

Task: {difficulty_prompts[difficulty]}

Generate a {difficulty.upper()} question for this text."""

    for attempt in range(3):
        try:
            client = get_groq_client(use_fallback)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            error_str = str(e)
            if "rate_limit" in error_str.lower() or "429" in error_str:
                if not use_fallback and GROQ_KEY_FALLBACK:
                    print(f"    Rate limit hit, switching to fallback key...")
                    return generate_qa_pair(chunk, difficulty, use_fallback=True)
                else:
                    wait_time = 60 * (attempt + 1)
                    print(f"    Both keys rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)
            else:
                print(f"    Groq error (attempt {attempt+1}): {e}")
                time.sleep(5)

    return None

def assign_difficulties(n_rows):
    """
    Assign difficulties maintaining target distribution.
    40% factual, 30% interpretive, 20% multi_hop, 10% unanswerable
    """
    difficulties = []
    difficulties.extend(["factual"]       * int(n_rows * 0.40))
    difficulties.extend(["interpretive"]  * int(n_rows * 0.30))
    difficulties.extend(["multi_hop"]     * int(n_rows * 0.20))
    difficulties.extend(["unanswerable"]  * int(n_rows * 0.10))

    # Fill remaining
    while len(difficulties) < n_rows:
        difficulties.append("factual")

    random.shuffle(difficulties)
    return difficulties[:n_rows]

def save_checkpoint(rows, last_idx):
    with open(CHECKPOINT, "w") as f:
        json.dump({"rows": rows, "last_idx": last_idx}, f)

def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            data = json.load(f)
        print(f"Resuming from checkpoint: {data['last_idx']} rows done")
        return data["rows"], data["last_idx"]
    return [], 0

def generate_golden_set():
    print("=" * 60)
    print("P6 - Golden Dataset Generator")
    print("=" * 60)
    print("Target: 100 rows (30 act / 30 judgment / 30 pov / 10 tax)")
    print("Difficulty: 40% factual / 30% interpretive / 20% multi_hop / 10% unanswerable")

    # Load chunks
    print("\nLoading chunks...")
    chunks_by_type = load_chunks()

    # Sample chunks
    print("\nSampling chunks...")
    sampled_chunks = sample_chunks(chunks_by_type)
    random.shuffle(sampled_chunks)

    # Assign difficulties
    difficulties = assign_difficulties(len(sampled_chunks))

    # Load checkpoint
    rows, start_idx = load_checkpoint()

    print(f"\nGenerating {len(sampled_chunks)} Q&A pairs...")
    print(f"Starting from index: {start_idx}")
    print("-" * 60)

    for i, (chunk, difficulty) in enumerate(
        zip(sampled_chunks[start_idx:], difficulties[start_idx:]),
        start=start_idx
    ):
        query_id = f"Q{str(i+1).zfill(3)}"

        print(f"\n[{i+1}/100] {query_id} | {chunk['doc_type']:8} | {difficulty:13} | {chunk['doc_title'][:40]}")

        # Generate Q&A
        qa = generate_qa_pair(chunk, difficulty)

        if qa:
            # Determine is_answerable
            is_answerable = "no" if difficulty == "unanswerable" else "yes"
            if qa.get("confidence") == "unanswerable":
                is_answerable = "no"

            row = {
                "query_id":            query_id,
                "query":               qa.get("question", ""),
                "doc_type":            chunk["doc_type"],
                "difficulty":          difficulty,
                "ground_truth_answer": qa.get("answer", ""),
                "source_doc":          chunk["doc_id"],
                "page_no":             chunk["page_number"],
                "section_ref":         chunk.get("section_ref", ""),
                "expected_citations":  f"{chunk['doc_id']}, p.{chunk['page_number']}",
                "is_answerable":       is_answerable,
                "doc_title":           chunk["doc_title"],
                "key_terms":           ", ".join(qa.get("key_terms", [])),
                "confidence":          qa.get("confidence", ""),
                "chunk_id":            chunk["chunk_id"],
                "text_used":           chunk["text"][:300] + "..."
            }

            rows.append(row)
            print(f"  Q: {row['query'][:80]}...")
            print(f"  A: {row['ground_truth_answer'][:80]}...")
        else:
            print(f"  [FAIL] Failed to generate Q&A for {query_id}")

        # Save checkpoint every 10 rows
        if (i + 1) % 10 == 0:
            save_checkpoint(rows, i + 1)
            print(f"\n  [CHECKPOINT] {i+1} rows saved")

        # Rate limit protection
        time.sleep(3)

    # Save final Excel
    print(f"\n{'='*60}")
    print("Saving Excel file...")

    df = pd.DataFrame(rows)

    # Reorder columns
    columns = [
        "query_id", "query", "doc_type", "difficulty",
        "ground_truth_answer", "source_doc", "page_no",
        "section_ref", "expected_citations", "is_answerable",
        "doc_title", "key_terms", "confidence",
        "chunk_id", "text_used"
    ]
    df = df[columns]

    # Save Excel with formatting
    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Golden Set")

        # Auto-adjust column widths
        worksheet = writer.sheets["Golden Set"]
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    # Also save as CSV backup
    csv_file = OUTPUT_EXCEL.replace(".xlsx", ".csv")
    df.to_csv(csv_file, index=False)

    print(f"[OK] Saved: {OUTPUT_EXCEL}")
    print(f"[OK] Backup: {csv_file}")

    # Summary
    print(f"\n{'='*60}")
    print("P6 COMPLETE - Golden Set Summary")
    print(f"{'='*60}")
    print(f"Total rows: {len(rows)}")

    print("\nBy doc_type:")
    for t in ["act", "judgment", "pov", "tax"]:
        count = len([r for r in rows if r["doc_type"] == t])
        print(f"  {t:10}: {count}")

    print("\nBy difficulty:")
    for d in ["factual", "interpretive", "multi_hop", "unanswerable"]:
        count = len([r for r in rows if r["difficulty"] == d])
        print(f"  {d:13}: {count}")

    answerable   = len([r for r in rows if r["is_answerable"] == "yes"])
    unanswerable = len(rows) - answerable
    print(f"\nAnswerable:   {answerable}")
    print(f"Unanswerable: {unanswerable}")

    return df


if __name__ == "__main__":
    random.seed(42)  # Reproducibility
    df = generate_golden_set()
    print("\n[OK] Ready for manual review!")
    print(f"Open: data/golden/golden_set.xlsx")
    print("Next: P7 - LLM Generation + Citations")
