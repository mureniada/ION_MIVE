# User Output Contract

## Transport

The backend returns this result as a structured JSON payload over the REST API (`docs/15_API_CONTRACT.md`). The frontend renders it into the human-readable form below; the frontend performs presentation only and adds no ION logic. When `DEBUG` is true, the same stages are also emitted incrementally over the SSE progress stream, but the final rendered result is identical to live mode.

## Default presentation

The user should not see raw JSON by default.

The rendered result must contain:

## 1. Question
The exact user question.

## 2. Primary Answer
A concise synthesis grounded in retrieved evidence and MIVE comparison.

The renderer may synthesize deterministically from structured fields. It must not hide conflicts.

## 3. MIVE Assessment
- agreements;
- disagreements;
- unique findings;
- weakly supported claims;
- overall status.

## 4. Uncertainty
Unresolved limitations, ambiguity, evidence gaps, or model disagreement.

## 5. Evidence
For each important claim:
- document title/source;
- document or chunk identifier;
- short supporting excerpt;
- claim linkage.

## 6. Operational Metrics
- request ID;
- total latency;
- Gemini latency;
- OpenAI latency;
- retrieval latency;
- input/output tokens per provider;
- estimated cost per provider;
- estimated total cost;
- success/failure status.

## Technical details

Raw provider reports and raw JSON may be available under an optional expandable technical section.

## Failure output

Failures must be precise:
- retrieval failure;
- Gemini failure;
- OpenAI failure;
- normalization failure;
- MIVE failure;
- configuration failure.

Do not return a generic successful answer when one required MIVE provider has failed.
