# System Scope

## Version 1 scope

The clean-room implementation must include:

1. A monorepo with a `backend/` and a `frontend/`, delivered via Docker / Docker Compose.
2. A backend **core** orchestrator with **modules** connected through in-process interface contracts.
3. Corpus ingestion.
4. Vector or equivalent semantic retrieval.
5. Evidence metadata.
6. Canonical Context Pack.
7. Gemini IVE adapter (module).
8. OpenAI IVE adapter (module).
9. Canonical IVE report validation.
10. MIVE comparison (module).
11. Human-readable result renderer.
12. Per-request usage, latency, and cost telemetry.
13. Backend core entry point (`ask`) exposed over an internal **REST API**.
14. A **`DEBUG`-gated SSE progress stream** (debug only; live mode returns a single final result).
15. A containerized **frontend web app** that consumes the REST API and holds no ION logic.
16. Automated tests (backend and frontend).

## Explicitly deferred

- Claude as a runtime reasoning provider;
- automatic knowledge graph publication;
- complex operator workflow;
- user authentication;
- billing;
- multi-tenant infrastructure;
- advanced corpus CRUD;
- background ingestion pipelines;
- public cloud production deployment;
- automated Big Bang knowledge capsule generation;
- large-scale orchestration frameworks.

## Completion sequence

Backend core + modules first (behind the REST API).
Frontend second (thin client over the API).
Docker Compose bring-up of the full stack.
Cloud next.
CRUD only when a real operator requirement is demonstrated.
