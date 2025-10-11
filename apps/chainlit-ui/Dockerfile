FROM python:3.11-slim

WORKDIR /app

# Copy the entire chainlit-ui folder so all future subfolders are preserved
COPY apps/chainlit-ui /app/apps/chainlit-ui

# Install dependencies from pyproject.toml
RUN pip install --no-cache-dir hatchling && \
    pip wheel -w /tmp/wheels ./apps/chainlit-ui && \
    pip install --no-cache-dir /tmp/wheels/*.whl

EXPOSE 8000

# Switch into src so uvicorn can import server.py cleanly
WORKDIR /app/apps/chainlit-ui/src
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]