# Research Log

Every entry is tagged: **[VERIFIED FACT]** (confirmed from a current external source), **[OPERATOR DECISION]** (instructed by the operator), **[ARCH ASSUMPTION]** (a design choice we made, revisable), or **[DEFERRED]** (deliberately postponed).

Claude Code appends to this log during the build. Nothing version-sensitive is taken from memory. This file supersedes the earlier pre-seed version and reflects the operator's locked decisions of 2026-07-13.

## 2026-07-13 — Preparation pass (pre-implementation)

### Providers / SDKs
- **[VERIFIED FACT]** OpenAI's current structured-output path is the **Responses API** with strict schema via `text.format`; classic JSON mode is legacy. SDK accepts Pydantic models directly. (OpenAI structured-outputs docs.)
- **[VERIFIED FACT]** Google's current SDK is the unified **`google-genai`**; structured output via `response_schema` / `response_json_schema` / `response_mime_type` in `GenerateContentConfig`; Pydantic supported; usage metadata returned. (Google AI for Developers docs.)
- **[VERIFIED FACT]** Both providers return token usage metadata suitable for cost telemetry. Prefer provider usage over local estimation (`docs/08`).

### Models / pricing (see `docs/MODEL_AND_PRICING_REGISTER.md`)
- **[VERIFIED FACT]** OpenAI standard text rates 2026-07-13 (USD/1M in·out): `gpt-5.4-nano` 0.20·1.25 [GA]; `gpt-5.4-mini` 0.75·4.50 [GA]; `gpt-5.4` 2.50·15.00 [GA]; `gpt-5.5` 5.00·30.00 [GA]. (OpenAI API pricing page.)
- **[VERIFIED FACT]** Gemini rates 2026-07-13 (USD/1M in·out): `gemini-3.1-flash-lite` 0.25·1.50 [GA]; `gemini-3.5-flash` 1.50·9.00 [GA]; `gemini-3.1-pro` 2.00·12.00 [Preview]; `gemini-2.5-pro` [GA]. (Gemini Developer API pricing page.)
- **[OPERATOR DECISION]** Propose an economical pair (A) and a quality pair (B); no live call until the operator approves Pair A + estimated cost. Names/prices are configuration, not logic.
- **[ARCH ASSUMPTION]** Pair A = `gpt-5.4-mini` + `gemini-3.1-flash-lite`; Pair B = `gpt-5.5` + `gemini-3.1-pro`. Revisable if Pair A underperforms on IVE structure quality.

### Budget
- **[OPERATOR DECISION]** Total initial dev + live-test ceiling **USD 10**; max live spend without extra approval **USD 1**; start mocked/deterministic; first live test = **one** question; report models/#calls/est. max cost/purpose before any larger batch.

### Backend / API
- **[VERIFIED FACT]** FastAPI is the standard Python REST framework; native SSE (`EventSourceResponse`) since 0.135.0; SSE generators must check client disconnect. (FastAPI docs.)
- **[OPERATOR DECISION]** FastAPI is the service boundary; REST backbone + **DEBUG-gated SSE** progress; separated frontend; Docker Compose is the reproducible runtime; **the MIVE core must be independently testable before full-stack Docker integration is declared complete.**
- **[ARCH ASSUMPTION]** Core + modules run in-process in one backend container for v0.1 (ports/adapters), extractable to services later.

### Vector store
- **[OPERATOR DECISION]** Use **Qdrant** only; do not add Chroma or any second store for v0.1. Retrieval sits behind a provider-independent interface. Report deployment mode, collection naming, embedding dimension, payload contract, rebuild procedure, persistence volume before implementation.
- **[VERIFIED FACT]** Qdrant is a Docker-native, Rust vector DB with payload/metadata filtering, stable IDs, and a local→hosted path. (Vector DB comparison research, 2026.)
- **[DEFERRED]** Embedding model + dimension — confirm at build (candidate: a current OpenAI or open embedding model; dimension follows the chosen embedder).

### Frontend
- **[VERIFIED FACT]** For an internal, behind-login dashboard, React + Vite SPA is the pragmatic 2026 choice (no SSR needed). (Frontend framework research, 2026.)
- **[ARCH ASSUMPTION]** Frontend = React + Vite SPA; consumes REST + (in DEBUG) SSE; holds no ION logic.

### Corpus
- **[VERIFIED FACT]** 9 files in `corpus/source/`, 0 duplicate checksums, 3 TXT + 6 PDF, all text-extractable, no OCR needed. Checksums in `docs/CORPUS_REGISTER.md` (audited 2026-07-13).
- **[OPERATOR DECISION]** All 9 files approved and in scope; private; no public redistribution of raw text; excerpts only for traceability.

### Representative questions
- **[OPERATOR DECISION]** 20-question validation set locked (see `docs/OPERATOR_CHECKLIST.md`). Question 1 ("What is money?") is the single first live end-to-end test. Questions 2–20 need separate approval before live runs.

### Tooling
- **[VERIFIED FACT]** Git available in the build environment (2.34.1). Docker Desktop could **not** be verified from this environment (operator-side, Windows host) — see `docs/OPERATOR_CHECKLIST.md`.

### Structured-output validation
- **[ARCH ASSUMPTION]** Pydantic v2 models validate provider output against the canonical IVE schema inside each provider adapter; failures raise precise provider-stage errors (no fabricated repair).

## Template for future entries

```
## YYYY-MM-DD — <topic>
- [VERIFIED FACT] <fact> (source URL, date checked)
- [OPERATOR DECISION] <decision>
- [ARCH ASSUMPTION] <assumption + why + how to revisit>
- [DEFERRED] <what and when to decide>
```

## Sign-off (Claude Code completes before Phase 1 code)
- [ ] All version-sensitive facts re-confirmed from official sources at build time.
- [ ] No hardcoded deprecated model names.
- [ ] Pricing dated and isolated from runtime logic.
- [ ] Operator approved economical pair + first-question cost.
- [ ] Both API keys confirmed configured.
