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

#### Single-engine response shape (`STANDARD_GEMINI`, mode `SINGLE`)
Under a single-engine Model Execution Profile the renderer's `render_single`
output has the same seven top-level keys, with these differences (per
`backend/app/modules/renderer/renderer.py`):

- `mive_assessment` is `null` — no comparison ran.
- `uncertainty` is `{ "reported": [ "string" ] }` — the one report's own
  uncertainty, verbatim.
- `operational_metrics.comparison_latency_ms` is `null`, and `providers`
  holds exactly one entry.
- `disclaimer` states that a single configured model execution produced the
  response and that no cross-model claim applies.

#### VOE composition additions (only when `VOE_PROFILE_ENABLED=true`)
When VOE Dialogue Profile composition is **attempted** for a turn (see
`backend/app/core/orchestrator.py`), the response differs from the shape
above as follows. When it is not attempted (VOE disabled), the response is
exactly the renderer's output, byte for byte, and none of these keys exist.

- `presentation` (new top-level key):
  `{ "composition_status": "COMPOSED" | "FALLBACK" }`.
- `primary_answer`: on `COMPOSED`, the composer's restyled text; on
  `FALLBACK`, the renderer's deterministic answer, unchanged.
- `disclaimer`: on `COMPOSED`, replaced by a disclaimer stating that the
  interpretation came from one configured model execution and that a
  separate presentation step, run under the named VOE Dialogue Profile
  version, restyled its wording and was instructed not to add claims or
  evidence. On `FALLBACK`, the renderer's disclaimer, unchanged.
- `uncertainty` and `evidence`: always unchanged.
- `operational_metrics.composition` (new block):
  ```json
  { "status": "COMPOSED | FALLBACK_PROVIDER_ERROR | FALLBACK_MALFORMED_OUTPUT",
    "provider": "string|null", "model": "string|null",
    "input_tokens": 0, "output_tokens": 0, "usage_is_estimated": false,
    "latency_ms": 0.0, "attempt_latency_ms": 0.0, "estimated_cost": 0.0,
    "voe_profile_id": "string", "voe_profile_version": "string",
    "voe_runtime_behavioral_fingerprint_sha256": "string" }
  ```
  `latency_ms` is the composer-measured provider call (`null` on fallback);
  `attempt_latency_ms` is the backend's own measurement of the whole
  composition attempt, present on success and fallback alike. On fallback,
  `provider`, `model`, tokens and `estimated_cost` are `null`.
- `operational_metrics.total_latency_ms`: the pipeline span (which ends
  before rendering) **plus** `composition.attempt_latency_ms`.
- `operational_metrics.total_estimated_cost`: the provider total **plus**
  `composition.estimated_cost`; `null` whenever the composition cost is
  unknown, which includes every fallback (the provider may still have billed
  the attempt).
- `operational_metrics.providers` stays IVE-only; the composition call is
  never listed there.

All cost values are estimates from the dated pricing table
(`backend/app/modules/telemetry/pricing.py`), not billing figures: the Gemini
backend does not capture thinking tokens, so a thinking model's cost can be
under-reported. The internal Turn Record's `pipeline_latency_ms` is
unchanged by composition and is not part of this HTTP contract.

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

VOE runtime configuration (G4, G5):
- A malformed `VOE_PROFILE_ENABLED` returns `503 not_ready` on `POST /ask` and the `/pilot/sessions` routes, with the fixed message `"Invalid runtime configuration (values never shown)."`. Nothing is cached, so correcting the value recovers without a restart. `GET /health` stays 200.
- `GET /ask/stream` stays hidden (404) whenever `DEBUG` cannot be confirmed as true, including when settings fail to load.
- With `VOE_PROFILE_ENABLED=true`, if the running Core has no bound VOE profile, or its binding differs from the currently configured bundle, readiness returns `503 not_ready` until the process restarts. The Core is never rebuilt or changed in place.

A single-provider failure is an **incomplete MIVE state**, surfaced as an error with `error_stage`, not a 200 success (invariant, `docs/06`).

## Invariants for the API layer

1. The API never performs retrieval, provider calls, comparison, or rendering itself — it delegates to the core.
2. The `DEBUG` flag is the only switch between "final result only" and "final result + SSE progress".
3. Request validation (non-empty question, valid `top_k`) happens before any external call.
4. No secret appears in any response, log line, or error message.
5. Public payloads are provider- and framework-independent.
