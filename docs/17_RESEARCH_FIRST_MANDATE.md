# Research-First Mandate

## Why this exists

Model SDKs, model names, pricing, and framework APIs change frequently. Training memory is stale by the time you build. **You must confirm every version-sensitive fact from current sources before writing implementation code.** Do not build from memory.

This is Phase 0. No implementation code is written until this research is done and recorded.

## Rule

Before coding, research the current state of each item below, then record what you found and the version/decision you will use in a **research log** (`docs/RESEARCH_LOG.md`, created by you). If a fact cannot be confirmed, mark it unconfirmed and stop rather than guess — especially for pricing and model identifiers.

## What to research (minimum)

1. **OpenAI Python SDK** — current package, the current recommended API surface for structured JSON output (as of this pack's research, the **Responses API** with strict structured outputs via `text.format`; JSON mode is legacy), how to attach a Pydantic/JSON-schema response format, and how usage/token metadata is returned.
2. **Google Gemini Python SDK** — the current unified **`google-genai`** SDK, structured output via `response_schema` / `response_json_schema` / `response_mime_type`, Pydantic support, and how usage/token metadata is returned.
3. **Current model names + pricing** for both providers. Do not hardcode a model or price from memory. Put confirmed model IDs in `.env` (`GEMINI_MODEL`, `OPENAI_MODEL`) and dated pricing in the telemetry pricing table. Unknown pricing returns `null`, never a fabricated estimate (`docs/08`).
4. **FastAPI** (or the chosen backend framework) — current project-structure conventions, dependency injection, and the current way to serve **Server-Sent Events** (native `EventSourceResponse` support arrived in FastAPI 0.135.0; confirm current version and usage, including client-disconnect handling).
5. **Vector store** — pick and justify one for a local/Docker research corpus (candidates confirmed current: Chroma, Qdrant, pgvector, LanceDB). Confirm the current client library and how it runs under Docker Compose.
6. **Frontend stack** — confirm the current recommended SPA setup (research indicates React + Vite for an internal, behind-login dashboard; no SSR needed) and how it consumes REST + SSE.
7. **Docker / Docker Compose** — current best practice for a two-container (frontend + backend) monorepo plus a vector-store service, and secret handling via environment.
8. **Structured-output validation** — current Pydantic (v2+) patterns for validating provider output against the canonical IVE schema.

## Research log format

For each item, record:
- source(s) consulted (URL + date checked);
- the current fact/version;
- the decision you will implement;
- any risk or unconfirmed point.

## After research

1. Post a short summary of findings and chosen versions.
2. Present the minimal architecture plan (consistent with `docs/14`–`docs/16`).
3. Ask only essential clarifying questions.
4. Then, and only then, create the skeleton and begin implementing per `docs/12` and `docs/09`.

## Non-negotiable

- No implementation code before the research log exists.
- No hardcoded model names or prices taken from memory.
- No assumption that an API surface still looks the way it did in training data — verify it.
