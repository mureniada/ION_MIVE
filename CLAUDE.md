# CLAUDE.md — Clean-Room Engineering Mandate

## Role

You are the primary software architect and implementer for a new clean-room ION MIVE application.

## Core instruction

Build from the specifications in this repository. Do not reconstruct or imitate any previous implementation. Do not request previous Codex code or debugging history unless the operator explicitly changes this rule.

## Product objective

Create a minimal, reliable local product that performs:

Question
→ Retrieval
→ Context Pack
→ Gemini IVE + OpenAI IVE
→ MIVE comparison
→ Human-readable answer
→ Evidence + uncertainty + usage/cost metrics

## Non-negotiable invariants

1. Intelligence is not truth.
2. Retrieval is not reasoning.
3. Gemini and OpenAI must reason independently.
4. Neither model may see the other model's report before MIVE.
5. Both models receive the same canonical Context Pack.
6. Evidence is stronger than confidence.
7. MIVE compares reports; it does not silently replace them with a third answer.
8. A one-model fallback is not a successful MIVE result.
9. Secrets must never be committed or printed.
10. The frontend must remain a thin client over a tested backend, reachable only through the REST API. It contains no ION reasoning, retrieval, or comparison logic.
11. No scope expansion before the local acceptance criteria pass.
12. Prefer the smallest implementation that is testable, observable, and replaceable.

## Architecture invariants

These are mandatory and constrain the freedom below.

A1. The system is a monorepo with a `frontend/` and a `backend/`, run via Docker / Docker Compose.
A2. The backend has one **core** orchestrator. All modules connect to the core through explicit interface contracts (ports/adapters); modules never call each other directly and never reach the frontend.
A3. For v0.1 the core and its modules run **in-process inside one backend container**. A module may be extracted into its own service later without changing the core's public contracts — design for that, do not build it now.
A4. Frontend↔backend communication uses **REST** (HTTP/JSON) as the backbone.
A5. A **Server-Sent Events (SSE)** progress stream is exposed **only when `DEBUG` is true**. When `DEBUG` is false, the backend returns a single final REST result and exposes no progress stream. This is one code path gated by a config flag, not two parallel implementations.
A6. Public contracts (REST payloads, IVE/MIVE/Context Pack schemas) are provider- and transport-independent. Provider- and framework-specific detail stays inside module adapters.

## Required engineering behavior

- **Research before coding.** Follow `docs/17_RESEARCH_FIRST_MANDATE.md`: confirm current SDKs, model names, pricing, FastAPI/SSE, vector store, and frontend/Docker practices from live sources before writing implementation code. Do not rely on memory for anything version-sensitive.
- Read all files in `docs/` and `schemas/` before writing code.
- Present a short implementation plan before editing.
- Produce and maintain the target monorepo tree (`docs/16_TARGET_FILE_TREE.md`); refine it if research shows a better structure, and record why.
- Use one reproducible Python environment for the backend.
- Add tests with every module.
- Keep provider-specific normalization inside provider adapters.
- Keep public contracts provider- and transport-independent.
- Record token use, latency, and estimated cost per provider.
- Stop and report exact evidence when blocked.
- Do not claim PASS without executing the acceptance tests.

## Freedom of implementation

You may choose libraries, exact internal module names, packaging details, and test framework.

The following are **mandated** and not open to change: the frontend/backend split, the single core with modules behind interface contracts, in-process modules for v0.1, REST as the frontend↔backend protocol, the `DEBUG`-gated SSE progress stream, Docker/Docker Compose delivery, and every epistemic invariant in this pack. See `docs/14_ARCHITECTURE.md`.
