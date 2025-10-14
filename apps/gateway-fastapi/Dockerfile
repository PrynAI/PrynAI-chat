# apps/gateway-fastapi/Dockerfile

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy project metadata and source
COPY pyproject.toml ./
COPY src ./src

# Install build tool and build wheel
RUN pip install --no-cache-dir hatchling \
    && pip wheel -w /tmp/wheels . \
    && pip install --no-cache-dir /tmp/wheels/*.whl

# --- System dependencies for OCR ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies for OCR and PDF/image handling ---
RUN pip install --no-cache-dir \
    pillow \
    pytesseract \
    pymupdf

# Expose FastAPI port
EXPOSE 8080

# Run the FastAPI app with uvicorn
CMD ["uvicorn", "src.main:app", "--host=0.0.0.0", "--port=8080"]