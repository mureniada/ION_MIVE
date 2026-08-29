# MIVE Specification

## Definition

MIVE means Multi-Intelligence Validation Engine.

MIVE compares multiple independent IVE reports. It does not perform the original interpretation of the corpus.

## Minimum input

Whenever MIVE executes, its own contract is unchanged: two valid, distinct
IVE reports generated from:
- the same question;
- the same canonical Context Pack;
- independent provider executions.

For version 1:
- Gemini;
- OpenAI.

## MIVE invocation is profile-conditional (TASK 20)

MIVE invocation is controlled by the active Model Execution Profile, not
performed unconditionally on every turn. The first live profile,
STANDARD_GEMINI (mode SINGLE), authorizes exactly one engine and does not
invoke MIVE at all for the turns it governs — MIVE is NOT APPLICABLE to a
SINGLE-mode turn, never a failed or degraded MIVE result, and never
represented as one. A deliberately configured SINGLE profile is not a
one-model fallback (CLAUDE.md); it is a distinct, legitimate Product policy
that simply does not include a comparison stage. MIVE's own two-report,
distinct-engine invariant above is never weakened or bypassed for any
profile that DOES invoke it — a future profile that requests comparison
semantics (e.g., a dual-engine profile) would call MIVE exactly as specified
here, unchanged.

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
