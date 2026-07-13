# Acceptance Criteria

## Definition of done for Local Working Product v0.1

All mandatory criteria must pass.

## A. Retrieval

- [ ] Corpus can be ingested from a clean environment.
- [ ] Retrieval returns relevant evidence for representative questions.
- [ ] Evidence includes stable document identifiers.
- [ ] Importing modules does not require external secrets.
- [ ] Missing runtime configuration fails clearly before external calls.

## B. Context Pack

- [ ] Both providers receive the same Context Pack.
- [ ] Context Pack validates against its schema.
- [ ] Document IDs survive through both reports.

## C. Gemini IVE

- [ ] Real Gemini API call succeeds.
- [ ] Output normalizes into canonical IVE schema.
- [ ] Invalid output produces a precise provider-stage error.
- [ ] Usage and latency are captured.

## D. OpenAI IVE

- [ ] Real OpenAI API call succeeds.
- [ ] Output normalizes into canonical IVE schema.
- [ ] Invalid output produces a precise provider-stage error.
- [ ] Usage and latency are captured.

## E. Independence

- [ ] Gemini receives no OpenAI output.
- [ ] OpenAI receives no Gemini output.
- [ ] Both execute against the same evidence context.

## F. MIVE

- [ ] Two valid reports are compared.
- [ ] Agreements are visible.
- [ ] Conflicts are visible.
- [ ] Unique findings remain attributed.
- [ ] Evidence gaps are visible.
- [ ] One-provider failure is not reported as MIVE success.

## G. User output

- [ ] `ask()` returns a structured result.
- [ ] A human-readable answer is rendered.
- [ ] Uncertainty is visible.
- [ ] Evidence is visible.
- [ ] Raw JSON is hidden by default.

## H. Metrics

- [ ] Provider token use is recorded when available.
- [ ] Provider latency is recorded.
- [ ] Total estimated cost is recorded or explicitly unavailable.
- [ ] Unknown pricing does not produce fabricated cost.

## I. REST API + Frontend + Docker

- [ ] The backend exposes the core over the REST API.
- [ ] `POST /ask` returns a complete result for a real question.
- [ ] With `DEBUG` on, the SSE progress stream emits stage events; with `DEBUG` off, no progress stream is exposed and a single final result is returned.
- [ ] The frontend is a separate container that reaches the backend only through the REST API.
- [ ] The frontend contains no ION reasoning, retrieval, or comparison logic.
- [ ] `docker compose up` starts backend + frontend + vector store with one documented command.
- [ ] Errors are readable and stage-specific in both API responses and the UI.
- [ ] No secret is displayed or logged.

## J. Tests

- [ ] Unit tests pass.
- [ ] Provider adapters have normalization tests.
- [ ] MIVE comparison has synthetic tests.
- [ ] Core `ask()` has mocked integration tests.
- [ ] One controlled live smoke test passes.

## Release decision

Only after every mandatory criterion passes:

`STATUS: LOCAL WORKING PRODUCT v0.1`
