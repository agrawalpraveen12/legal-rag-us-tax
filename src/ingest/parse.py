"""
P2 - Document Parsing Pipeline
================================
Parser: PyMuPDF (fitz) - fastest PDF parser, exact page numbers
Chunk size: 600 words - legal concept boundary
Overlap: 100 words - sentence context preservation
Split: sentence boundary - never mid-sentence
TXT pages: 3000 chars = 1 virtual page
"""

import os
import json
import re
from pathlib import Path
from tqdm import tqdm
import fitz  # PyMuPDF

# ─── CONFIG ───────────────────────────────────────────────
CHUNK_SIZE    = 600   # words - legal concept fits here
CHUNK_OVERLAP = 100   # words - context preservation
TXT_PAGE_SIZE = 3000  # chars per virtual page for .txt files
MIN_CHUNK_WORDS = 20  # skip tiny fragments
OUTPUT_FILE   = "data/processed/okf_chunks.jsonl"
MANIFEST_FILE = "data/processed/manifest.csv"

# ─── TITLE MAPPINGS ───────────────────────────────────────
ACT_TITLES = {
    "act_sec61":   "IRC Section 61 - Gross Income Defined",
    "act_sec62":   "IRC Section 62 - Adjusted Gross Income Defined",
    "act_sec63":   "IRC Section 63 - Taxable Income Defined",
    "act_sec67":   "IRC Section 67 - Miscellaneous Itemized Deductions",
    "act_sec68":   "IRC Section 68 - Overall Limitation on Itemized Deductions",
    "act_sec101":  "IRC Section 101 - Life Insurance Exclusions",
    "act_sec102":  "IRC Section 102 - Gifts and Inheritances Exclusion",
    "act_sec121":  "IRC Section 121 - Home Sale Exclusion",
    "act_sec132":  "IRC Section 132 - Fringe Benefits",
    "act_sec151":  "IRC Section 151 - Personal Exemptions",
    "act_sec162":  "IRC Section 162 - Trade or Business Expenses",
    "act_sec163":  "IRC Section 163 - Interest Deduction",
    "act_sec165":  "IRC Section 165 - Losses",
    "act_sec167":  "IRC Section 167 - Depreciation",
    "act_sec170":  "IRC Section 170 - Charitable Contributions",
    "act_sec183":  "IRC Section 183 - Hobby Loss Rules",
    "act_sec199A": "IRC Section 199A - Qualified Business Income Deduction",
    "act_sec212":  "IRC Section 212 - Expenses for Income Production",
    "act_sec263":  "IRC Section 263 - Capital Expenditures",
    "act_sec265":  "IRC Section 265 - Expenses for Tax-Exempt Income",
    "act_sec351":  "IRC Section 351 - Transfer to Controlled Corporation",
    "act_sec368":  "IRC Section 368 - Corporate Reorganizations",
    "act_sec401":  "IRC Section 401 - Qualified Pension Plans",
    "act_sec408":  "IRC Section 408 - Individual Retirement Accounts",
    "act_sec501":  "IRC Section 501 - Tax-Exempt Organizations",
    "act_sec1001": "IRC Section 1001 - Gain or Loss on Disposition",
    "act_sec1031": "IRC Section 1031 - Like-Kind Exchanges",
    "act_sec1221": "IRC Section 1221 - Capital Asset Defined",
    "act_sec6662": "IRC Section 6662 - Accuracy-Related Penalty",
    "act_sec7201": "IRC Section 7201 - Tax Evasion",
}

JUDGMENT_TITLES = {
    "judgment_01_commissioner_v_glenshaw_glass":           "Commissioner v. Glenshaw Glass Co. (1955)",
    "judgment_02_old_colony_trust_co_v_commissioner":      "Old Colony Trust Co. v. Commissioner (1929)",
    "judgment_03_cesarini_v_united_states":                "Cesarini v. United States (1969)",
    "judgment_04_welch_v_helvering":                       "Welch v. Helvering (1933)",
    "judgment_05_commissioner_v_tellier":                  "Commissioner v. Tellier (1966)",
    "judgment_06_indopco_v_commissioner":                  "INDOPCO Inc. v. Commissioner (1992)",
    "judgment_07_bob_jones_university_v_united_states":    "Bob Jones University v. United States (1983)",
    "judgment_08_gregory_v_helvering":                     "Gregory v. Helvering (1935)",
    "judgment_09_cottage_savings_association_v_commissioner": "Cottage Savings Association v. Commissioner (1991)",
    "judgment_10_starker_v_united_states":                 "Starker v. United States (1979)",
    "judgment_11_cheek_v_united_states":                   "Cheek v. United States (1991)",
    "judgment_12_united_states_v_kirby_lumber":            "United States v. Kirby Lumber Co. (1931)",
    "judgment_13_faridessultaneh_v_commissioner":          "Farid-Es-Sultaneh v. Commissioner (1947)",
    "judgment_14_commissioner_v_duberstein":               "Commissioner v. Duberstein (1960)",
    "judgment_15_crane_v_commissioner":                    "Crane v. Commissioner (1947)",
    "judgment_16_commissioner_v_tufts":                    "Commissioner v. Tufts (1983)",
    "judgment_17_arrowsmith_v_commissioner":               "Arrowsmith v. Commissioner (1952)",
    "judgment_18_corn_products_refining_v_commissioner":   "Corn Products Refining Co. v. Commissioner (1955)",
    "judgment_19_arkansas_best_corporation_v_commissioner":"Arkansas Best Corp. v. Commissioner (1988)",
    "judgment_20_grodt_mckay_realty_v_commissioner":       "Grodt & McKay Realty v. Commissioner (1981)",
    "judgment_21_estate_of_franklin_v_commissioner":       "Estate of Franklin v. Commissioner (1976)",
    "judgment_22_united_states_v_gilmore":                 "United States v. Gilmore (1963)",
    "judgment_23_commissioner_v_flowers":                  "Commissioner v. Flowers (1946)",
    "judgment_24_hernandez_v_commissioner":                "Hernandez v. Commissioner (1989)",
    "judgment_25_benaglia_v_commissioner":                 "Benaglia v. Commissioner (1937)",
    "judgment_26_moller_v_united_states":                  "Moller v. United States (1983)",
    "judgment_27_textron_inc_v_united_states":             "Textron Inc. v. United States (2009)",
    "judgment_28_helvering_v_bruun":                       "Helvering v. Bruun (1940)",
    "judgment_29_davis_v_united_states":                   "Davis v. United States (1990)",
    "judgment_30_commissioner_v_idaho_power":              "Commissioner v. Idaho Power Co. (1974)",
}

TAX_TITLES = {
    "tax_pub17":   "IRS Publication 17 - Your Federal Income Tax",
    "tax_pub334":  "IRS Publication 334 - Tax Guide for Small Business",
    "tax_pub463":  "IRS Publication 463 - Travel Gift and Car Expenses",
    "tax_pub526":  "IRS Publication 526 - Charitable Contributions",
    "tax_pub535":  "IRS Publication 535 - Business Expenses",
    "tax_pub544":  "IRS Publication 544 - Sales of Business Property",
    "tax_pub550":  "IRS Publication 550 - Investment Income and Expenses",
    "tax_pub590a": "IRS Publication 590A - IRA Contributions",
    "tax_pub946":  "IRS Publication 946 - How to Depreciate Property",
    "tax_pub15b":  "IRS Publication 15B - Employers Tax Guide to Fringe Benefits",
}

# ─── SECTION REF MAPPING ──────────────────────────────────
SECTION_REFS = {
    "act": lambda doc_id: "IRC §" + doc_id.replace("act_sec",""),
    "judgment": lambda doc_id: "",
    "pov": lambda doc_id: "",
    "tax": lambda doc_id: "",
}

# ─── HELPER FUNCTIONS ─────────────────────────────────────

def get_doc_type(folder_name):
    return {
        "acts": "act",
        "judgments": "judgment",
        "pov": "pov",
        "tax_docs": "tax"
    }.get(folder_name, "unknown")

def get_title(doc_id, doc_type, filename):
    stem = Path(filename).stem
    if doc_type == "act":
        return ACT_TITLES.get(stem, stem)
    elif doc_type == "judgment":
        return JUDGMENT_TITLES.get(stem, stem.replace("_"," ").title())
    elif doc_type == "tax":
        return TAX_TITLES.get(stem, stem)
    elif doc_type == "pov":
        # Clean up filename for POV
        name = stem.replace("pov_crs_","CRS Report: ")\
                   .replace("pov_gao_","GAO Report: ")\
                   .replace("pov_jct_","JCT Report: ")\
                   .replace("pov_tf_","Tax Foundation: ")\
                   .replace("pov_irs_","IRS Analysis: ")\
                   .replace("pov_ssrn_","SSRN Paper: ")\
                   .replace("_"," ")
        return name.title()
    return stem

def extract_pdf_pages(filepath):
    """
    Extract text per page using PyMuPDF.
    Reason: PyMuPDF preserves exact page numbers critical for legal citations.
    Fallback: if page has < 50 chars, flag for OCR.
    """
    pages = []
    ocr_needed = []

    try:
        doc = fitz.open(filepath)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            cleaned = text.strip()

            if len(cleaned) < 50:
                ocr_needed.append(page_num + 1)
                continue

            if cleaned:
                pages.append({
                    "page_number": page_num + 1,
                    "text": cleaned
                })
        doc.close()

        if ocr_needed:
            print(f"    [OCR] Pages needing OCR: {ocr_needed} in {Path(filepath).name}")

    except Exception as e:
        print(f"    [ERR] PDF error {filepath}: {e}")

    return pages

def extract_txt_pages(filepath):
    """
    Read TXT and create virtual pages.
    Reason: TXT judgment files have no page markers.
    Virtual page = 3000 chars = ~1 printed page.
    This enables page-level citations for judgments.
    """
    pages = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Remove source line if present
        if content.startswith("Source:"):
            content = content.split("\n\n", 1)[-1]

        content = content.strip()

        for i in range(0, len(content), TXT_PAGE_SIZE):
            chunk = content[i:i + TXT_PAGE_SIZE].strip()
            if chunk:
                pages.append({
                    "page_number": (i // TXT_PAGE_SIZE) + 1,
                    "text": chunk
                })
    except Exception as e:
        print(f"    [ERR] TXT error {filepath}: {e}")

    return pages

def split_into_chunks(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """
    Split text into overlapping word-based chunks at sentence boundaries.

    Why 600 words: Legal concepts (IRC subsections, court holdings)
    typically span 400-800 words. Too small = missing context.
    Too large = noisy retrieval.

    Why 100 word overlap: Prevents context loss at chunk boundaries.
    Legal text often references prior sentences. 100 words ~= 2-3 sentences.

    Why sentence boundary: Never cut mid-sentence in legal text.
    "...shall not apply to subsection (b)" - cutting this loses meaning.
    """
    # Split into sentences first
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_words = []
    current_count = 0

    for sentence in sentences:
        sentence_words = sentence.split()
        sentence_len = len(sentence_words)

        # If adding this sentence exceeds chunk_size, save current chunk
        if current_count + sentence_len > chunk_size and current_words:
            chunk_text = " ".join(current_words)
            if len(current_words) >= MIN_CHUNK_WORDS:
                chunks.append(chunk_text)

            # Keep overlap words for next chunk
            overlap_words = current_words[-overlap:] if len(current_words) > overlap else current_words
            current_words = overlap_words + sentence_words
            current_count = len(current_words)
        else:
            current_words.extend(sentence_words)
            current_count += sentence_len

    # Add remaining words as last chunk
    if current_words and len(current_words) >= MIN_CHUNK_WORDS:
        chunks.append(" ".join(current_words))

    return chunks

# ─── MAIN PIPELINE ────────────────────────────────────────

def process_all_documents():
    os.makedirs("data/processed", exist_ok=True)

    all_chunks = []
    manifest_rows = []
    total_docs = 0
    failed_docs = []

    raw_dir = Path("data/raw")
    folders = ["acts", "judgments", "pov", "tax_docs"]

    print("=" * 60)
    print("P2 - Legal Document Parsing Pipeline")
    print("=" * 60)
    print(f"Chunk size:    {CHUNK_SIZE} words")
    print(f"Chunk overlap: {CHUNK_OVERLAP} words")
    print(f"Min chunk:     {MIN_CHUNK_WORDS} words")
    print(f"TXT page size: {TXT_PAGE_SIZE} chars")
    print("=" * 60)

    for folder in folders:
        folder_path = raw_dir / folder
        if not folder_path.exists():
            print(f"\n[WARN] Folder not found: {folder_path}")
            continue

        doc_type = get_doc_type(folder)
        files = sorted([
            f for f in folder_path.iterdir()
            if f.suffix in [".pdf", ".txt"] and not f.name.startswith(".")
        ])

        print(f"\n[DIR] Processing {folder}/ ({len(files)} files) -> type={doc_type}")

        folder_chunks = 0

        for filepath in tqdm(files, desc=f"  {folder}"):
            doc_id   = filepath.stem
            filename = filepath.name
            title    = get_title(doc_id, doc_type, filename)
            section_ref = SECTION_REFS[doc_type](doc_id)

            # Extract pages
            if filepath.suffix == ".pdf":
                pages = extract_pdf_pages(str(filepath))
            else:
                pages = extract_txt_pages(str(filepath))

            if not pages:
                print(f"\n    [SKIP] No text: {filename}")
                failed_docs.append(filename)
                continue

            # Chunk each page
            doc_chunk_idx = 0
            doc_total_words = 0

            for page in pages:
                page_text = page["text"]
                page_num  = page["page_number"]

                chunks = split_into_chunks(page_text)

                for chunk_text in chunks:
                    word_count = len(chunk_text.split())
                    doc_chunk_idx += 1
                    doc_total_words += word_count

                    chunk_id = f"{doc_id}_p{page_num}_c{doc_chunk_idx}"

                    record = {
                        "chunk_id":    chunk_id,
                        "doc_id":      doc_id,
                        "doc_type":    doc_type,
                        "doc_title":   title,
                        "page_number": page_num,
                        "chunk_index": doc_chunk_idx,
                        "text":        chunk_text,
                        "word_count":  word_count,
                        "section_ref": section_ref,
                        "source_url":  "",
                        "jurisdiction":"US-Federal",
                        "date":        "2024",
                        "local_path":  str(filepath)
                    }

                    all_chunks.append(record)
                    folder_chunks += 1

            # Manifest row
            manifest_rows.append({
                "doc_id":      doc_id,
                "doc_type":    doc_type,
                "title":       title,
                "filename":    filename,
                "pages":       len(pages),
                "chunks":      doc_chunk_idx,
                "total_words": doc_total_words,
                "section_ref": section_ref,
                "local_path":  str(filepath)
            })

            total_docs += 1

        print(f"  [OK] {folder}: {folder_chunks} chunks created")

    # ─── SAVE JSONL ───────────────────────────────────────
    print(f"\n[SAVE] Saving {len(all_chunks)} chunks to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    # ─── SAVE MANIFEST CSV ────────────────────────────────
    import csv
    with open(MANIFEST_FILE, "w", newline="", encoding="utf-8") as f:
        if manifest_rows:
            writer = csv.DictWriter(f, fieldnames=manifest_rows[0].keys())
            writer.writeheader()
            writer.writerows(manifest_rows)

    # ─── FINAL REPORT ─────────────────────────────────────
    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)

    print("\n" + "=" * 60)
    print("P2 COMPLETE")
    print("=" * 60)
    print(f"Documents processed : {total_docs}")
    print(f"Total chunks        : {len(all_chunks)}")
    print(f"Output file         : {OUTPUT_FILE}")
    print(f"File size           : {file_size_mb:.1f} MB")
    print(f"Manifest            : {MANIFEST_FILE}")

    if failed_docs:
        print(f"\n[WARN] Failed ({len(failed_docs)}): {failed_docs}")

    # Chunk distribution by type
    print("\nChunks by doc type:")
    from collections import Counter
    type_counts = Counter(c["doc_type"] for c in all_chunks)
    for dtype, count in sorted(type_counts.items()):
        print(f"  {dtype:10} : {count} chunks")

    # Sample chunk
    print("\nSample chunk (first):")
    print(json.dumps(all_chunks[0], indent=2, ensure_ascii=False))

    return all_chunks

if __name__ == "__main__":
    process_all_documents()
