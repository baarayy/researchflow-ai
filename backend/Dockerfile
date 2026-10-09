FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install .

COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts

RUN useradd --create-home appuser && mkdir -p /data/uploads && chown appuser /data/uploads
USER appuser

EXPOSE 8000
# Apply DB migrations (app tables + LangGraph checkpoint tables), then serve.
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.setup_checkpointer && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
