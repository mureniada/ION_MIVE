# Internal REST API Contract

The REST API is the **only** way the frontend reaches the backend. It is a thin surface over `core.ask`. It performs transport, validation, and error mapping — no reasoning.

Paths, field names, and status codes below are the intended contract; the implementer may refine details during the research phase but must keep the shape and the DEBUG behavior.

## Base

- JSON request and response bodies (`Content-Type: application/json`).
- Versioned base path recommended: `/api/v1`.
- CORS restricted to the frontend origin(s) from `CORS_ALLOWED_ORIGINS`.
- Secrets are never returned in any payload or error.

## Endpoints

### `GET /api/v1/health`
Liveness/readiness. Returns service status and whether required configuration is present (booleans only — never secret values, per `docs/11`).

```json
{ "status": "ok", "config_present": true, "debug": false }
```

### `POST /api/v1/ask`
The primary endpoint. Runs the full pipeline and returns one final result.

Request:
```json
{ "question": "string (required, non-empty)", "top_k": 5 }
```

Response (200): the rendered result plus the structured payload behind it. It carries the User Output Contract (`docs/07`) content and the underlying MIVE result, IVE reports, evidence, and metrics (`docs/08`). Raw JSON stays available but is not the default view in the frontend.

```json
{
  "request_id": "string",
  "question": "string",
  "rendered": { "...": "human-readable sections per docs/07" },
  "mive_result": { "...": "per schemas/mive_result.schema.json" },
  "ive_reports": [ { "...": "per schemas/ive_report.schema.json" } ],
  "metrics": { "...": "per docs/08 telemetry fields" },
  "status": "success"
}
```

### `GET /api/v1/ask/stream` — DEBUG ONLY
Exposed **only when `DEBUG=true`**. When `DEBUG=false` this route must not exist (return 404). Server-Sent Events; one event per completed stage, ending with the final result.

Event sequence (example):
```
event: stage   data: {"stage":"retrieval","status":"done","latency_ms":120}
event: stage   data: {"stage":"context_pack","status":"done"}
event: stage   data: {"stage":"gemini_ive","status":"done","latency_ms":2100}
event: stage   data: {"stage":"openai_ive","status":"done","latency_ms":1980}
event: stage   data: {"stage":"mive","status":"done"}
event: result  data: { ...same payload as POST /ask... }
```

The generator must check for client disconnect and stop cleanly. The `result` event payload is byte-for-byte the same result a `POST /ask` would return.

## Error model

Failures are precise and stage-specific (`docs/07` failure output). Never a generic success when a required provider failed.

```json
{
  "request_id": "string",
  "status": "error",
  "error_stage": "retrieval | context_pack | gemini | openai | normalization | mive | configuration",
  "message": "human-readable, secret-free",
  "partial_metrics": { "...": "whatever telemetry was captured before failure" }
}
```

Suggested status codes: `400` invalid request (e.g. empty question, bad `top_k`); `422` normalization/validation failure; `424` a required provider/dependency failed; `500` unexpected; `503` missing/invalid configuration before external calls.

A single-provider failure is an **incomplete MIVE state**, surfaced as an error with `error_stage`, not a 200 success (invariant, `docs/06`).

## Invariants for the API layer

1. The API never performs retrieval, provider calls, comparison, or rendering itself — it delegates to the core.
2. The `DEBUG` flag is the only switch between "final result only" and "final result + SSE progress".
3. Request validation (non-empty question, valid `top_k`) happens before any external call.
4. No secret appears in any response, log line, or error message.
5. Public payloads are provider- and framework-independent.
