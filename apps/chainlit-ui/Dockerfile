FROM python:3.11-slim
WORKDIR /app
COPY apps/chainlit-ui/pyproject.toml ./pyproject.toml
COPY apps/chainlit-ui/chainlit.toml ./chainlit.toml
COPY apps/chainlit-ui/src ./apps/chainlit-ui/src
COPY apps/chainlit-ui/auth ./apps/chainlit-ui/auth
RUN pip install --no-cache-dir hatchling && pip wheel -w /tmp/wheels . && pip install --no-cache-dir /tmp/wheels/*.whl
EXPOSE 8000
CMD ["uvicorn", "apps/chainlit-ui/src/server.py:app", "--host", "0.0.0.0", "--port", "8000"]