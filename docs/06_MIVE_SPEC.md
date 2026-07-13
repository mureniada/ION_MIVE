# MIVE Specification

## Definition

MIVE means Multi-Intelligence Validation Engine.

MIVE compares multiple independent IVE reports. It does not perform the original interpretation of the corpus.

## Minimum input

Two valid IVE reports generated from:
- the same question;
- the same canonical Context Pack;
- independent provider executions.

For version 1:
- Gemini;
- OpenAI.

## Required comparison dimensions

- agreements;
- partial agreements;
- conflicts;
- unique findings by engine;
- evidence overlap;
- unsupported or weakly supported claims;
- uncertainty overlap;
- overall comparison status.

## Required output

- `question`
- `engine_ids`
- `agreements`
- `partial_agreements`
- `conflicts`
- `unique_findings`
- `unsupported_findings`
- `shared_uncertainty`
- `overall_status`
- `comparison_notes`

## Rules

1. Preserve engine attribution.
2. Do not convert disagreement into false consensus.
3. Do not discard unique findings merely because only one engine produced them.
4. Evidence overlap strengthens comparison but does not automatically prove truth.
5. MIVE must not silently call a third language model unless a future specification explicitly permits it.
6. A provider failure produces an incomplete MIVE state, not a successful MIVE result.
7. Comparison logic must be testable with synthetic IVE reports without API access.
