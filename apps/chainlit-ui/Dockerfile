FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY apps/chainlit-ui ./apps/chainlit-ui
COPY chainlit.toml ./chainlit.toml
RUN pip install --no-cache-dir hatchling && pip wheel -w /tmp/wheels . && pip install --no-cache-dir /tmp/wheels/*.whl
EXPOSE 8000
CMD ["uvicorn", "apps/chainlit-ui/src/server.py:app", "--host", "0.0.0.0", "--port", "8000"]