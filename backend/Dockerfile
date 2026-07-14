# Backend image: intelligence core + modules + FastAPI transport (M8).
# Build context is the REPO ROOT so schemas/ can be copied in.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for layer caching.
# Single explicit dependency contract: API server + the approved local embedding
# runtime (sentence-transformers). No ad hoc installs inside running containers.
COPY backend/pyproject.toml ./pyproject.toml
RUN pip install --no-cache-dir ".[api,local-embed]"

# App code + canonical schemas (source of truth for validation).
COPY backend/ ./
COPY schemas/ /schemas/
# docker-compose.yml is copied in so the compose-contract tests can read it
# inside the container (M8.1). It is config only, not application code.
COPY docker-compose.yml ./docker-compose.yml
ENV ION_SCHEMAS_DIR=/schemas
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Default: serve the transport layer. `docker compose run` overrides this command
# (e.g. `python run_tests.py`, `python -m app.cli "..."`, `python -m app.ingest_cli`).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
