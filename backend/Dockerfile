# Backend image: core + modules behind the (later) FastAPI service.
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
ENV ION_SCHEMAS_DIR=/schemas
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# NOTE: the REST/SSE server (uvicorn app.main:app) is wired at milestone M8.
# Until then the image ships the tested core + CLI.
CMD ["python", "-m", "app.cli", "--help"]
