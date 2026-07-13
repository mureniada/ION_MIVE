# Architecture

This document is mandatory. It fixes the shape of the system. Everything else in the pack (invariants, contracts, acceptance criteria) sits inside this shape.

## 1. One sentence

A **frontend** container talks over an internal **REST API** to a **backend** container, whose **core** orchestrates a set of **modules** (each behind a strict interface contract) to turn a question into a MIVE result.

## 2. Topology

```
┌──────────────────────────────────────────────────────────────┐
│ Docker Compose network                                        │
│                                                               │
│  ┌───────────────┐        REST (HTTP/JSON)      ┌───────────┐ │
│  │  frontend      │  ─────────────────────────▶ │  backend  │ │
│  │  (web app)     │  ◀───────────────────────── │  (API +   │ │
│  │  presentation  │   SSE progress (DEBUG only)  │   core)   │ │
│  └───────────────┘                              └─────┬─────┘ │
│                                                       │       │
│                                              in-process calls │
│                                                       │       │
│                                              ┌────────▼──────┐│
│                                              │     core       ││
│                                              │  orchestrator  ││
│                                              └───┬───┬───┬────┘│
│         ┌───────────┬───────────┬───────────┬───┘   │   └──── … │
│         ▼           ▼           ▼           ▼       ▼           │
│   retrieval    gemini_ive   openai_ive     mive   telemetry     │
│    module       module       module       module   module      │
│         │                                                       │
│         ▼                                                       │
│  ┌───────────────┐                                             │
│  │ vector store   │ (container or embedded)                    │
│  └───────────────┘                                             │
└──────────────────────────────────────────────────────────────┘
```

## 3. Layers and responsibilities

### Frontend (thin client)
- The only surface the user sees.
- Renders the User Output Contract (`docs/07`).
- Talks to the backend **only** through the REST API.
- Holds **no** ION logic: no retrieval, no provider calls, no MIVE, no prompt construction, no vector store access.
- Recommended stack (confirm in research phase): a React + Vite single-page app served as static assets. Any equivalent that respects these boundaries is acceptable.

### Backend
Two parts inside one container:

**API layer** — a thin REST (and DEBUG-only SSE) surface over the core. It translates HTTP to core calls and core results to HTTP. It contains no reasoning.

**Core (orchestrator)** — the single hub. It owns the pipeline order and nothing else:

```
question
  → retrieval module        (evidence)
  → build Context Pack       (canonical, shared)
  → gemini_ive module  ┐     (independent, parallel)
  → openai_ive module  ┘
  → validate IVE reports
  → mive module              (comparison)
  → renderer                 (human-readable result)
  → telemetry module         (usage, latency, cost)
```

The core calls modules **only through their interfaces**. It does not know which SDK, vector store, or model a module uses.

### Modules
Independent units behind interface contracts. For v0.1: `retrieval`, `gemini_ive`, `openai_ive`, `mive`, `renderer`, `telemetry` (exact names are the implementer's to choose). Rules:
- A module talks only to the core through its interface. Modules do **not** call each other and do **not** call the frontend.
- Provider-, framework-, and store-specific detail is sealed inside the module (adapter). It never leaks into the core or the API.
- Gemini and OpenAI modules must not share state or read each other's output (epistemic invariant, `docs/05`).

## 4. Ports and adapters (how "modules talk to the core")

Use ports/adapters (hexagonal) style:

- The core depends on **interfaces** (ports), e.g. `RetrievalPort`, `IVEPort`, `MIVEPort`, `TelemetryPort`.
- Each module provides an **adapter** implementing its port (e.g. a Gemini adapter and an OpenAI adapter both implement `IVEPort`).
- Adapters are wired into the core at startup via dependency injection. The core never imports a concrete SDK.

Benefit: modules are swappable and independently testable (synthetic IVE reports test MIVE with no API access, per `docs/06`), and any module can later be extracted into its own service without touching the core.

## 5. In-process now, service-ready later

For v0.1 all modules run **in-process inside the backend container**. This is deliberate:
- fewer moving parts, no inter-module network failures, easiest to test;
- honors the pack's "smallest implementation that is testable, observable, and replaceable" invariant.

Design the interfaces so a module *could* be moved behind its own REST/gRPC service later. Do not build that now. Microservices-per-module is explicitly out of scope for v0.1.

## 6. Protocols

| Boundary | Protocol | Notes |
|---|---|---|
| Frontend ↔ Backend | **REST** (HTTP/JSON) | Backbone. One request → one final result. See `docs/15`. |
| Frontend ↔ Backend (DEBUG only) | **SSE** | Progress events per stage. Exposed only when `DEBUG=true`. |
| Core ↔ Modules | **in-process interface calls** | No network. Ports/adapters. |
| Backend ↔ Vector store | client library / HTTP | Inside the retrieval module only. |

## 7. The DEBUG flag

`DEBUG` (env var) selects the transport shape, not two separate products:
- `DEBUG=true`: the API also exposes an SSE endpoint that emits an event as each pipeline stage completes (retrieval done, Gemini done, OpenAI done, MIVE done). For developer diagnosis.
- `DEBUG=false` (default, user-facing): no progress stream is exposed; the API returns a single final result. The frontend shows a spinner until it arrives.

The final rendered result is identical in both modes. `DEBUG` must never be enabled in a user-facing deployment.

## 8. Docker

- `backend/Dockerfile` — Python + FastAPI (or equivalent) + Uvicorn.
- `frontend/Dockerfile` — Node build stage → static assets served by a small web server.
- `docker-compose.yml` at the repo root — brings up `backend`, `frontend`, and the vector store on one internal network; one documented command starts the stack.
- Secrets come from the environment / `.env`, never baked into images (`docs/11`).

## 9. What must not happen

- No ION logic in the frontend.
- No module-to-module calls; no module reaching the frontend.
- No provider/SDK/store detail leaking into the core or API contracts.
- No second, parallel "debug build" — one code path gated by `DEBUG`.
- No microservice explosion in v0.1.
- No cross-model leakage between the Gemini and OpenAI modules before MIVE.
