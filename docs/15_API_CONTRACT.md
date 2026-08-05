# Internal REST API Contract

The REST API is the **only** way the frontend reaches the backend. It is a thin surface over `core.ask`. It performs transport, validation, and error mapping — no reasoning.

Paths, field names, and status codes below are the intended contract; the implementer may refine details during the research phase but must keep the shape and the DEBUG behavior.

## Base

- JSON request and response bodies (`Content-Type: application/json`).
- **No versioned base path is currently implemented.** Endpoints are unprefixed
  (see below) — verified directly against `backend/app/main.py`. A versioned
  prefix such as `/api/v1` remains a possible future proposal, not built.
- CORS restricted to the frontend origin(s) from `CORS_ALLOWED_ORIGINS`.
- Secrets are never returned in any payload or error.

## Endpoints

### `GET /health`
Liveness. Returns exactly `{"status": "ok"}` (verified directly against
`backend/app/main.py`). This endpoint currently returns no configuration or
`debug` fields; documenting those would describe unimplemented behavior.

### `POST /ask`
The primary endpoint. Runs the full pipeline and returns the rendered result
directly — verified by `backend/tests/test_transport_api.py::test_post_ask_returns_complete_rendered_result_for_real_question`
(Phase P2, `1 passed`, exit code `0`), which asserts the HTTP response body is
byte-for-byte the renderer's output with no wrapping.

Request:
```json
{ "question": "What is money?", "top_k": 5 }
```
(`question`: required, non-empty string. `top_k`: optional integer.)

Response (200): **the rendered result directly** — this is the current,
verified public contract. It is a flat object with exactly these top-level
keys (per `backend/app/modules/renderer/renderer.py`):

```json
{
  "question": "What is money?",
  "primary_answer": "string",
  "mive_assessment": {
    "agreements": [ { "...": "per-pair comparison entries" } ],
    "partial_agreements": [ { "...": "..." } ],
    "disagreements": [ { "...": "..." } ],
    "unique_findings": [ { "...": "..." } ],
    "weakly_supported": [ { "...": "..." } ],
    "overall_status": "strong_agreement | partial_agreement | conflict | divergent"
  },
  "uncertainty": {
    "shared": [ "string" ],
    "per_engine": { "engine_id": [ "string" ] },
    "weakly_supported_claims": [ { "...": "..." } ]
  },
  "evidence": [
    { "document_id": "string", "title": "string", "source": "string",
      "page": "string|number|null", "chunk_id": "string|null",
      "excerpt": "string", "claim_linkage": "string" }
  ],
  "operational_metrics": {
    "request_id": "string", "timestamp": "ISO-8601 string",
    "question": "string", "retrieved_chunks": 0, "context_characters": 0,
    "context_documents": 0, "retrieval_latency_ms": 0.0,
    "comparison_latency_ms": 0.0, "total_latency_ms": 0.0,
    "providers": [
      { "provider": "string", "model": "string", "input_tokens": 0,
        "output_tokens": 0, "latency_ms": 0.0, "estimated_cost": 0.0,
        "usage_is_estimated": false }
    ],
    "total_estimated_cost": 0.0, "status": "success", "error_stage": null
  },
  "disclaimer": "string"
}
```

**Distinct from the internal Core result.** Internally, `core.ask()` returns a
fuller `AskResult` (`request_id`, `question`, `status`, `rendered`,
`mive_result`, `ive_reports`, `metrics`, per `backend/app/core/models.py`).
`POST /ask` returns only that result's `rendered` field — the internal
`mive_result`, `ive_reports`, and top-level `metrics`/`status` are **not**
exposed at the HTTP layer today. An envelope exposing those fields (as an
earlier draft of this document showed) is a **proposed future shape, not the
implemented current contract** — it must not be treated as already built.

### `GET /ask/stream` — DEBUG ONLY
Exposed **only when `DEBUG=true`**. When `DEBUG=false` this route must not exist (return 404). Server-Sent Events; one event per completed stage, ending with the final result.

Event sequence (example):
```
event: progress data: {"stage":"retrieval","status":"done","latency_ms":120}
event: progress data: {"stage":"context_pack","status":"done"}
event: progress data: {"stage":"gemini_ive","status":"done","latency_ms":2100}
event: progress data: {"stage":"openai_ive","status":"done","latency_ms":1980}
event: progress data: {"stage":"mive","status":"done"}
event: result  data: { ...same payload as POST /ask... }
```

The generator must check for client disconnect and stop cleanly. The `result` event payload is byte-for-byte the same result a `POST /ask` would return.

## Error model

Failures are precise and stage-specific (`docs/07` failure output). Never a generic success when a required provider failed.

The implemented error response shape is exactly this (verified against
`backend/app/api/service.py`'s `validate_request`, `not_ready_payload`, and
`core_error_payload`):

```json
{
  "status": "error",
  "error_stage": "invalid_request | not_ready | retrieval | context_pack | gemini | openai | normalization | mive | configuration",
  "message": "human-readable, secret-free"
}
```

There is no `request_id` or `partial_metrics` field in the current
implementation — an earlier draft of this document showed both, but neither
is returned today.

Exact implemented `error_stage` → HTTP status mapping (verified against
`backend/app/api/service.py`'s `_STAGE_STATUS`, `not_ready_payload`, and
`validate_request`; no `424` mapping exists anywhere in the implementation):

| `error_stage` | HTTP status | Notes |
|---|---|---|
| `invalid_request` | 400 | transport-level validation (empty question, bad `top_k`) — before any core call |
| `not_ready` | 503 | missing/invalid configuration, checked before any external call |
| `retrieval` | 502 | |
| `gemini` | 502 | |
| `openai` | 502 | |
| `context_pack` | 500 | |
| `mive` | 500 | |
| `configuration` | 500 | only reachable if a `ConfigurationError` originates inside `core.ask()` itself, rather than at the earlier `require_ready()` check (which maps to `not_ready` instead) |
| `normalization` | 422 | |

A single-provider failure is an **incomplete MIVE state**, surfaced as an error with `error_stage`, not a 200 success (invariant, `docs/06`).

## Invariants for the API layer

1. The API never performs retrieval, provider calls, comparison, or rendering itself — it delegates to the core.
2. The `DEBUG` flag is the only switch between "final result only" and "final result + SSE progress".
3. Request validation (non-empty question, valid `top_k`) happens before any external call.
4. No secret appears in any response, log line, or error message.
5. Public payloads are provider- and framework-independent.
