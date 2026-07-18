# Prompt Catalog

All prompts used in the Legal RAG system, with design rationale.

---

## 1. LLM Generation — Cite-or-Refuse System Prompt

**File:** `src/generate/answer.py`  
**Model:** `llama-3.1-8b-instant` via Groq  
**Temperature:** `0.1`

### System prompt

```
You are a precise US tax law research assistant.

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
- End with a "Sources:" section listing all cited documents
```

### User message template

```
LEGAL CONTEXT:
{formatted_chunks}

QUESTION: {query}

Provide a precise answer with citations from the context above.
```

Each chunk in the context is formatted as:

```
[CONTEXT N] {doc_title} | Page {page_number} | {section_ref}
{text}
```

### Design rationale

**Cite-or-refuse instead of best-effort answers.** Legal advice with a wrong citation is worse than no answer — it looks authoritative but may be wrong. The `INSUFFICIENT_CONTEXT` sentinel makes refusals machine-detectable so the evaluation harness can score them separately from wrong answers.

**Temperature 0.1, not 0.0.** The model must reproduce exact legal terminology (`ordinary and necessary`, `realization event`) verbatim from the source text. Full temperature-0 can occasionally loop on repeated phrasing; 0.1 adds just enough variation to avoid that while keeping the output deterministic for the same context.

**Citation format in the system prompt, not left to the model.** BM25 and vector retrieval return exact page numbers. By mandating `[Title, p.N]` in the system prompt, the citation parser in `extract_citations()` has a stable regex target to match against.

**Context injected in the user turn, not the system turn.** Groq's instruction-following is stronger when the task (system) is separated from the data (user). Mixing retrieved passages into the system prompt also inflates caching costs on repeated queries with the same chunks.

---

## 2. Query Rewriting Prompt

**File:** `src/retrieve/hybrid.py` → `rewrite_query()`  
**Model:** `llama-3.1-8b-instant` via Groq  
**Temperature:** `0.1`  
**Max tokens:** `50`

### System prompt

```
You are a legal search query optimizer for US tax law.
Rewrite the user's question into 5-8 precise legal search terms.
Focus on: IRC section numbers, legal terms, case names, IRS codes.
Return ONLY the search terms, no explanation, no punctuation.
Examples:
Input: "can a company deduct business meals"
Output: IRC 162 business meal expense deduction ordinary necessary

Input: "what happens if you don't pay taxes"
Output: IRC 7201 tax evasion willful failure pay criminal penalty
```

### User message

```
{original_query}
```

### Design rationale

**8B model for rewriting, 70B for generation.** Query rewriting is a mechanical keyword-extraction task; 8B is sufficient and runs at ~500 tok/sec vs ~100 for 70B. Saving 70B capacity for the generation step matters on the free Groq tier.

**Few-shot examples inline.** BM25 benefits from exact statutory terms (`IRC 162`) not natural language (`business meal deductions`). The two examples anchor the output format without requiring a schema — and because `max_tokens=50`, there is no room for the model to add explanations even if it wants to.

**Returns raw terms, not a question.** The rewritten output feeds directly into `multi_match` against `text`, `doc_title^2`, and `section_ref^3` fields in Elasticsearch. A full sentence would be tokenised and scored correctly by BM25 anyway, but raw terms are more predictable across both the BM25 and vector search paths.

---

## 3. Golden Dataset Generation Prompts

**File:** `src/eval/golden_gen.py` → `generate_qa_pair()`  
**Model:** `llama-3.3-70b-versatile` via Groq  
**Temperature:** `0.3`  
**Response format:** `json_object`

### System prompt

```
You are a US tax law expert creating evaluation questions.
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
}
```

### User message template

```
Document: {doc_title}
Type: {doc_type}
Page: {page_number}
Section: {section_ref}

Legal Text:
{chunk_text[:1500]}

Task: {difficulty_prompt}

Generate a {DIFFICULTY} question for this text.
```

### Difficulty sub-prompts (injected as `{difficulty_prompt}`)

**factual**
```
Generate a FACTUAL question with a direct, specific answer.
Example: "What items does IRC section 61 include in gross income?"
The answer should be findable in 1-2 sentences from the text.
```

**interpretive**
```
Generate an INTERPRETIVE question requiring legal analysis.
Example: "How did the court define 'ordinary' in the context of business expenses?"
The answer requires understanding the legal reasoning, not just facts.
```

**multi_hop**
```
Generate a MULTI-HOP question that requires connecting
two concepts in the text.
Example: "What standard does section 162 set, and how does this relate to capital expenditures?"
The answer should reference multiple parts of the legal text.
```

**unanswerable**
```
Generate a question that CANNOT be answered from this text.
The question should seem related but the answer is not in the provided passage.
Example: "What is the tax rate in California for this type of income?"
Return answer as: "This information is not available in the provided legal text."
Set confidence to: "unanswerable"
```

### Difficulty distribution

| Difficulty    | Share | Rationale |
|---------------|-------|-----------|
| factual       | 40 %  | Baseline recall — can the system find explicit facts? |
| interpretive  | 30 %  | Tests whether legal reasoning is preserved across chunking |
| multi_hop     | 20 %  | Tests whether RRF fusion surfaces multiple relevant chunks |
| unanswerable  | 10 %  | Verifies the cite-or-refuse refusal behaviour |

### Design rationale

**70B for golden generation, 8B for query rewriting.** The golden set is used only once; its quality directly determines whether evaluation scores are meaningful. Spending 70B tokens here is worth it.

**Temperature 0.3, not 0.1.** Unlike generation (which must be deterministic), question formulation benefits from some lexical variety — the same chunk should produce different-sounding questions across difficulty levels. 0.3 achieves variety while keeping answers faithful to the source text.

**JSON response format enforced at the API level.** `response_format={"type": "json_object"}` guarantees parseable output without regex. The schema (`question`, `answer`, `key_terms`, `confidence`) is embedded in the system prompt so the model's JSON keys are predictable.

**Difficulty injected per-call, not as a separate prompt.** Each call produces exactly one Q&A pair at one difficulty level. This keeps the context short and avoids the model hedging between difficulty types in a single response.

**Stratified sampling before generation.** The 30/30/30/10 doc-type split is enforced by sampling, not by prompting the model — asking an LLM to "generate 30% act questions" reliably fails. The model only sees one chunk at a time.

---

## 4. Citation Graph Extraction

**File:** `src/index/graph.py`

> **No LLM prompt is used here.** Citation relationships are extracted by two mechanisms:

### 4a. Hardcoded relationship tables

Curated manually from legal knowledge before the system ran. Three tables define the graph skeleton:

- `JUDGMENT_TO_ACT` — 30 landmark cases mapped to the IRC section each primarily interprets (e.g. *Welch v. Helvering* → `act_sec162`)
- `POV_TO_ACT` / `POV_TO_JUDGMENT` — CRS/IRS policy documents mapped to the acts and cases they analyse
- `TAX_TO_ACT` — IRS Publications mapped to the IRC sections they implement

Edge types and weights:

| Relationship   | Source              | Weight |
|----------------|---------------------|--------|
| `CITES`        | judgment → act      | 1.0    |
| `ANALYZES`     | pov → act           | 0.8    |
| `REFERENCES`   | pov → judgment      | 0.7    |
| `IMPLEMENTS`   | tax pub → act       | 0.6    |
| `CITES_AUTO`   | regex IRC detection | 0.5    |
| `CITES_CASE`   | regex case detection| 0.4    |

### 4b. Regex extraction from judgment text

Two functions scan the first 5,000 characters of each judgment file:

**`extract_irc_refs(text)`** — five patterns covering common citation styles:

```python
r'§\s*(\d+[A-Z]?)'
r'[Ss]ection\s+(\d+[A-Z]?)'
r'IRC\s+(?:§\s*)?(\d+[A-Z]?)'
r'26\s+U\.?S\.?C\.?\s+(?:§\s*)?(\d+[A-Z]?)'
r'I\.R\.C\.\s+§\s*(\d+[A-Z]?)'
```

Each match maps to `act_sec{N}` and is added as a `CITES_AUTO` edge if that node exists in the graph.

**`extract_case_refs(text)`** — case-name patterns for the nine most frequently cited landmark cases (Glenshaw Glass, Welch, Bob Jones, Cheek, Starker, INDOPCO, Gregory, Crane, Arkansas Best). Adds `CITES_CASE` edges.

### Why no LLM for graph extraction

The corpus is 101 documents with stable, well-known citation relationships. An LLM call per document would introduce hallucinated edges and require verification. Regex on the first 5,000 characters of judgment text catches the majority of explicit statutory citations reliably, while the curated tables handle the semantically important relationships (which case interprets which doctrine) that regex cannot infer from text alone.
