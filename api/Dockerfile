FROM python:3.10-slim

WORKDIR /app

# Install system deps needed by PyMuPDF and torch
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install torch CPU-only first — avoids the 526 MB CUDA wheel
RUN pip install --no-cache-dir --timeout 600 \
    torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies (torch already satisfied, skipped)
RUN pip install --no-cache-dir --timeout 300 -r requirements.txt

# Pre-download HuggingFace models into the image so runtime needs no internet
COPY api/download_models.py ./download_models.py
RUN python download_models.py && rm download_models.py

# App source
COPY src/ ./src/
COPY api/ ./api/

# Pre-parsed chunk data — used by index_docs.py on first run
COPY data/processed/ ./data/processed/

# Static assets served by the root endpoint
COPY legal_rag_architecture.svg .

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
