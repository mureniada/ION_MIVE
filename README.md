# ION MIVE Clean-Room Pack v1.0

This pack defines a clean-room implementation mandate for a new local ION MIVE product.

It intentionally contains:
- project meaning;
- epistemic rules;
- functional contracts;
- acceptance criteria;
- implementation constraints.

It intentionally excludes:
- previous Codex implementation code;
- previous debugging history;
- inherited module structure;
- old shell, path, or runtime workarounds;
- assumptions about how the new implementation must be organized internally.

## Target

A local application must accept a user question, retrieve relevant evidence from a corpus, send the same Context Pack independently to Gemini and OpenAI, normalize both results into one IVE contract, compare them through MIVE, and return a human-readable answer with evidence, uncertainty, latency, token use, and estimated cost.

## Architecture at a glance

The application is a **monorepo** with a clear front/back split, delivered on **Docker**:

- **`frontend/`** — a containerized web app (the only thing the user sees). It holds no ION logic; it talks to the backend only over an internal **REST API**.
- **`backend/`** — a single container that hosts a **core** orchestrator and a set of **modules** (retrieval, Gemini IVE, OpenAI IVE, MIVE, telemetry, renderer). Modules connect to the core through strict in-process interface contracts, not network calls.
- **REST** is the backbone protocol between frontend and backend. A **Server-Sent Events (SSE)** progress stream is exposed **only when `DEBUG` is enabled**; in normal/live mode the backend returns a single final REST result.
- **Docker Compose** orchestrates the two containers (plus the vector store).

The full architecture, module contracts, API contract, target file tree, and the mandatory research-first rule are defined in `docs/14`–`docs/17`. Read them before building.

## Required development order

0. Research current best practices before writing any code (see `docs/17_RESEARCH_FIRST_MANDATE.md`).
1. Backend skeleton: core + module interfaces (ports/adapters), no provider calls yet.
2. Corpus ingestion and retrieval module.
3. Context Pack generation.
4. Gemini IVE module.
5. OpenAI IVE module.
6. MIVE comparison module.
7. One backend `ask(question)` core entry point.
8. REST API over the core (+ DEBUG-gated SSE progress stream).
9. Automated acceptance tests.
10. Containerized frontend calling the REST API.
11. Docker Compose bringing up frontend + backend + vector store.
12. Optional cloud deployment.
13. Optional corpus CRUD after the first working product.

## First release boundary

The first release is a controlled local research product. It is not a public platform, not a knowledge graph, not a billing system, and not a general autonomous agent.
