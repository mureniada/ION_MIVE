# Architecture Decision Record

Short, dated decisions with rationale. Each has a status. Supersedes any conflicting earlier note. See `docs/14_ARCHITECTURE.md` for the full design.

Format: **ADR-NNN — Title** · Status · Date · Decision · Why · Consequences.

---

## ADR-001 — Monorepo with separated frontend/backend
- **Status:** Accepted · 2026-07-13
- **Decision:** One repository with `frontend/` and `backend/`; delivered via Docker Compose.
- **Why:** Operator wants a real front/back split; simplest to hand to Claude Code; clear boundaries.
- **Consequences:** Frontend is its own container and holds no ION logic; internal REST between them.

## ADR-002 — Single core + in-process modules (ports/adapters)
- **Status:** Accepted · 2026-07-13
- **Decision:** Backend has one core orchestrator; modules (retrieval, Gemini IVE, OpenAI IVE, MIVE, renderer, telemetry) implement interface contracts and run **in-process** in the backend container for v0.1.
- **Why:** Smallest testable/observable/replaceable design; avoids premature microservices and inter-module network failure; honors the pack invariants.
- **Consequences:** Modules are swappable and independently testable; any can be extracted to its own service later without changing the core. No module-to-module or module-to-frontend calls.

## ADR-003 — REST backbone + DEBUG-gated SSE
- **Status:** Accepted · 2026-07-13
- **Decision:** Frontend↔backend uses REST (HTTP/JSON). An SSE progress stream is exposed **only when `DEBUG=true`**; live mode returns a single final REST result. One code path gated by a flag.
- **Why:** REST is universal and simple; the pipeline is multi-second and staged, so developers benefit from progress events while users only need the final answer.
- **Consequences:** SSE route returns 404 when `DEBUG=false`; `DEBUG` never enabled in user-facing deployments. SSE stages: retrieval, Gemini, OpenAI, MIVE, answer-ready, stage-failure.

## ADR-004 — FastAPI as the service boundary
- **Status:** Accepted · 2026-07-13
- **Decision:** FastAPI (Uvicorn) exposes the core over REST + SSE.
- **Why:** Standard Python REST framework; native SSE since 0.135.0; first-class Pydantic; strong DI for wiring adapters.
- **Consequences:** API layer stays thin (transport + validation + error mapping); no reasoning in the API layer.

## ADR-005 — Qdrant as the only vector store
- **Status:** Accepted · 2026-07-13
- **Decision:** Use Qdrant for semantic retrieval; no second/parallel store for v0.1.
- **Why:** Operator decision; Docker-native, stable IDs, payload/metadata filtering, local→hosted path; sits behind a provider-independent retrieval interface.
- **Consequences:** Before implementation, report deployment mode, collection naming, embedding dimension, payload contract, rebuild procedure, persistence volume. Replaceable behind the interface if a concrete blocker appears.

## ADR-006 — Core-first delivery order
- **Status:** Accepted · 2026-07-13
- **Decision:** The MIVE core (`core.ask`) must be independently testable (mocked + synthetic) before full-stack Docker integration is declared complete.
- **Why:** Operator dependency-order requirement; keeps the intelligence core verifiable independent of transport/containers.
- **Consequences:** Docker/FastAPI/frontend integrate around an already-tested core; see `docs/PHASE_PLAN.md`.

## ADR-007 — Raw corpus is not committed to Git
- **Status:** Accepted · 2026-07-13
- **Decision:** `corpus/source/` raw files are git-ignored; the committed artifact is `docs/CORPUS_REGISTER.md` (checksums + metadata). The generated vector index and runtime cache are also ignored.
- **Why:** Files include copyrighted, private research material; must not be publicly exposed/redistributed. The register preserves traceability without shipping raw text.
- **Consequences:** A fresh clone has specs + register but no raw corpus/index; the operator supplies the corpus locally and the index is rebuilt. Evidence excerpts appear only inside the controlled application.

## ADR-008 — Model names and pricing are configuration
- **Status:** Accepted · 2026-07-13
- **Decision:** Model IDs live in `.env`; pricing lives in an isolated, dated table; both re-verified at build time.
- **Why:** Models/prices change; the pack must not rot; unknown pricing returns `null`, never fabricated.
- **Consequences:** Pairs proposed in `docs/MODEL_AND_PRICING_REGISTER.md`; economical pair is default and needs operator approval before first live call.

## ADR-009 — Frontend: React + Vite SPA
- **Status:** Accepted (revisable) · 2026-07-13
- **Decision:** Frontend is a React + Vite single-page app.
- **Why:** Internal, behind-login dashboard needs no SSR; simplest, fastest to build/host; consumes REST + SSE cleanly.
- **Consequences:** Any equivalent that keeps the frontend logic-free is acceptable; confirm at build.
