# Cost and Usage Specification

## Principle

Cost measurement is part of the product, not later analytics.

## Per-request telemetry

Record:

- `request_id`
- `timestamp`
- `question`
- `retrieved_chunks`
- `context_characters`
- `context_documents`
- Gemini input tokens
- Gemini output tokens
- Gemini latency
- Gemini estimated cost
- OpenAI input tokens
- OpenAI output tokens
- OpenAI latency
- OpenAI estimated cost
- retrieval latency
- comparison latency
- total latency
- total estimated cost
- status
- error stage, if any

## Pricing

- Pricing tables must be isolated from runtime logic.
- Unknown model pricing returns `null`, not a fabricated estimate.
- Price assumptions must be versioned or dated.
- Usage metadata from the provider is preferred.
- Estimated fallback token counting must be clearly marked as estimated.

## Initial measurement set

After the product passes locally, run 20–50 representative questions and calculate:

- average cost per question;
- median cost;
- P95 cost;
- average latency;
- P95 latency;
- failure rate;
- estimated cost per 100 questions;
- estimated monthly laboratory budget.

## Optimization rule

Measure first. Optimize only after a real baseline exists.
