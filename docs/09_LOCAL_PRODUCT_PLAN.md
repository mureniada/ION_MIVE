# Local Product Plan

## Phase 0 — Research

- complete `docs/17_RESEARCH_FIRST_MANDATE.md` before any implementation code;
- record findings and chosen versions in a research log.

## Phase 1 — Repository foundation

- clean monorepo: `backend/` and `frontend/`;
- clean Python backend project;
- backend **core** skeleton with empty **module** interfaces (ports/adapters), no provider calls yet;
- `.env.example` (including `DEBUG`);
- secret-safe `.gitignore`;
- reproducible backend environment;
- unit test command;
- Dockerfiles for backend and frontend + a `docker-compose.yml` skeleton;
- no inherited code.

## Phase 2 — Corpus

- place source material in `corpus/source/`;
- define ingestion;
- create versioned index;
- verify retrieval with representative questions;
- expose evidence metadata.

## Phase 3 — Backend core + modules

Implement the modules behind their interfaces and one core entry point:

```python
result = core.ask(question: str, top_k: int = 5)
```

Execution inside the core (calling modules in-process):

Question
→ retrieval module
→ build Context Pack
→ Gemini IVE module
→ OpenAI IVE module
→ validate
→ MIVE module compare
→ renderer module
→ telemetry module (metrics)

Each module is reached only through its interface contract (see `docs/14_ARCHITECTURE.md`).

## Phase 4 — REST API

- expose the core over an internal REST API (see `docs/15_API_CONTRACT.md`);
- `POST /ask` returns the single final result;
- when `DEBUG` is true, also expose the SSE progress stream; when false, no progress stream exists.

## Phase 5 — Local acceptance

The API path (and the underlying `core.ask`) must pass before frontend work begins.

## Phase 6 — Frontend

A containerized web app that calls the REST API only. Minimum UI:
- title;
- question input;
- run button;
- progress states (SSE-driven in `DEBUG`, spinner otherwise);
- final answer;
- MIVE assessment;
- uncertainty;
- evidence;
- cost and latency;
- technical details expander.

The frontend holds no ION logic and never calls providers or the vector store directly.

## Phase 7 — Docker Compose

- `docker compose up` brings up backend + frontend + vector store;
- one documented command starts the whole stack;
- backend and frontend are separate containers on an internal network.

## Phase 8 — Validation set

Run 10–20 representative questions and inspect:
- retrieval relevance;
- evidence traceability;
- model independence;
- comparison quality;
- readability;
- latency;
- cost;
- failure handling;
- secret safety.

## Phase 9 — Optional cloud

Only after local PASS:
- private repository;
- hosted frontend + backend containers (or equivalent);
- managed secrets;
- reachable vector store;
- controlled access;
- web smoke tests.

## CRUD

CRUD is deferred until the first product works.

When needed:
- create corpus document;
- read document and evidence;
- update metadata/content with re-indexing;
- delete document and vectors;
- audit changes.
