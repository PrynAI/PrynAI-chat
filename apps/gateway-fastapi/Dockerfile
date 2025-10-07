FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir hatchling && pip wheel -w /tmp/wheels . && pip install --no-cache-dir /tmp/wheels/*.whl
EXPOSE 8080
CMD ["uvicorn", "src.main:app", "--host=0.0.0.0", "--port=8080"]