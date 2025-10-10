FROM python:3.11-slim

# Set working directory to where server.py lives
WORKDIR /app/apps/chainlit-ui/src

# Copy the entire chainlit-ui folder so all future subfolders are preserved
COPY apps/chainlit-ui /app/apps/chainlit-ui

# Install dependencies from pyproject.toml
WORKDIR /app
RUN pip install --no-cache-dir hatchling && \
    pip wheel -w /tmp/wheels ./apps/chainlit-ui && \
    pip install --no-cache-dir /tmp/wheels/*.whl

EXPOSE 8000

# Run uvicorn from inside src/, so "server:app" works
WORKDIR /app/apps/chainlit-ui/src
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]