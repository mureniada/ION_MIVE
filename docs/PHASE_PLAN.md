# Phase Plan (Milestone Sequence)

Dependency-ordered milestones. Core is proven before containers. No live API call before operator approval of the economical pair + keys. Each milestone lists its gate (what must be true to move on).

## M0 — Preparation *(this pass — awaiting operator approval to proceed)*
- Research current SDKs, models, pricing; corpus audit; registers + docs; Git baseline.
- **Gate:** operator approves readiness report and authorizes implementation.

## M1 — Backend skeleton (no providers, no network)
- Monorepo layout; backend Python env; core orchestrator + empty module interfaces (ports/adapters); config incl. `DEBUG`; import-safe (no secrets/clients at import).
- Dockerfiles + `docker-compose.yml` skeleton (not yet the gate).
- **Gate:** `core.ask` importable; unit tests for interfaces/DI pass; no secret required to import.

## M2 — Retrieval + corpus (Qdrant)
- Ingestion of the 9 approved files; chunking; embeddings; Qdrant collection with stable IDs + payload contract; retrieval behind its interface; evidence metadata (source_id, title, page/chunk, checksum).
- **Gate:** representative questions return relevant, traceable evidence; retrieval config validated before external calls; rebuild procedure documented.

## M3 — Context Pack
- Canonical, provider-independent Context Pack; measurable size; explicit truncation if any; validates against `schemas/context_pack.schema.json`.
- **Gate:** both providers would receive an identical pack; document IDs stable.

## M4 — Provider IVE modules (mocked first)
- Gemini adapter (`google-genai`) and OpenAI adapter (Responses API) → canonical IVE schema; Pydantic validation; usage/latency capture; precise provider-stage errors.
- Build and test against **recorded/mocked** responses first.
- **Gate:** normalization tests pass on mocks; no live call yet; independence preserved (neither sees the other's output).

## M5 — MIVE (synthetic)
- Comparison logic: agreements, partial, conflicts, unique findings, evidence overlap, unsupported claims, shared uncertainty, overall status.
- **Gate:** synthetic IVE reports drive full MIVE tests with **no API access**; one-provider failure = incomplete state, not success.

## M6 — Core `ask()` + renderer (mocked end-to-end)
- Wire the pipeline in the core; deterministic human-readable renderer (`docs/07`); telemetry (`docs/08`).
- **Gate:** mocked integration test of `core.ask` passes end-to-end; this is the "core independently testable" milestone (ADR-006).

## M7 — First controlled LIVE test *(requires operator approval + keys)*
- Confirm both keys configured; run one minimal auth check per provider; then **Question 1 only** on the economical pair.
- Report: models used, provider calls (2), actual tokens/latency/cost vs the ~$0.02 estimate.
- **Gate:** one real end-to-end MIVE result produced; cost within expectation; operator approves any further live use.

## M8 — REST API + DEBUG SSE
- Expose `core.ask` via FastAPI: `POST /ask` (final result), `GET /health`; `GET /ask/stream` SSE **only when `DEBUG`** (else 404). Stage events + client-disconnect handling.
- **Gate:** API acceptance tests pass; error stages precise; no secret in any payload/log.

## M9 — Frontend (separated container)
- React + Vite SPA consuming REST (+ SSE in DEBUG); renders `docs/07` sections; no ION logic.
- **Gate:** a real question through the UI yields a complete result; readable stage-specific errors.

## M10 — Docker Compose full stack
- `docker compose up` brings up backend + frontend + Qdrant on one network with one documented command.
- **Gate:** full-stack acceptance passes; **only now** is Docker integration "complete" (ADR-006).

## M11 — Validation set (batched, approval-gated)
- With approval, run questions 2–20 (report #calls + est. max cost first); compute avg/median/P95 cost + latency, failure rate, per-100-question and monthly estimates (`docs/08`).
- **Gate:** metrics recorded; `STATUS: LOCAL WORKING PRODUCT v0.1` if all acceptance criteria (`docs/10`) pass.

## M12 — Optional cloud
- Only after local PASS: private repo, hosted containers, managed secrets, reachable vector store, controlled access, web smoke tests.

## Budget guardrails across phases
- M0–M6 and M8–M10 use mocks/synthetic — **$0 live**.
- M7 first live ≈ **$0.02** (Pair A).
- M11 full set Pair A ≈ **$0.36–0.50** (within $1, still report before running); Pair B ≈ **$2.5** (exceeds $1 → explicit approval).
- Hard stops: USD 1 live without approval, USD 10 total.
