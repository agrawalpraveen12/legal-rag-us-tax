# Legal RAG System — US Tax Law
AI-powered legal research tool for US Tax Law with hybrid search and exact citations.

## Dataset: 100 Documents
- 30 IRC Statutes (Acts)
- 30 Court Judgments
- 30 POV/Commentary
- 10 IRS Publications

## Tech Stack
- Elasticsearch 8.x (BM25 + Vector + RRF)
- BAAI/bge embeddings
- Groq API (LLaMA 3.3 70B)
- FastAPI + Next.js

## Phases
- P1: Data Collection ✅
- P2: Parse + Chunk
- P3: Index (ES)
- P4: Hybrid Search
- P5: Citation Graph
- P6: Golden Dataset
- P7: Generation
- P8: Evaluation
- P9: UI + API
- P10: Deploy
