# ION MIVE CLEAN-ROOM --- CLAUDE HANDOVER

**Date:** 2026-07-12\
**Project root:**
`C:\Users\murenia\Documents\Projects\ION_ON\ION_MIVE_CLEANROOM_PACK_v1`\
**Status:** Clean-room implementation start\
**Developer mandate:** Claude / Anthropic

------------------------------------------------------------------------

## 1. Read this first

You are receiving a clean-room project.

Do **not** reconstruct, repair, imitate, or ask for the previous Codex
implementation.

Do **not** request the old `ION_PLUS` repository, old `ION_CORPUS_v3`
implementation, debugging transcripts, path fixes, or previous module
structure unless the operator explicitly changes this mandate.

The previous implementation history is intentionally excluded.

Your task is to understand the specifications and build the smallest
reliable implementation independently.

------------------------------------------------------------------------

## 2. Project objective

Build a local working ION MIVE product with this execution path:

``` text
User Question
      ↓
Corpus Retrieval
      ↓
Canonical Context Pack
      ↓
Gemini IVE ─────────┐
                    ├──→ MIVE Comparison
OpenAI IVE ─────────┘
      ↓
Human-readable Answer
      ↓
Evidence + Uncertainty
      ↓
Token Usage + Cost + Latency
```

Gemini and OpenAI are the two runtime intelligence providers for version
1.

Claude is the software architect and developer. Claude is **not**
required as a runtime reasoning provider.

------------------------------------------------------------------------

## 3. Core epistemic rule

> Intelligence does not equal truth.

Retrieval is not reasoning.

Model confidence is not proof.

Evidence is stronger than confidence.

Disagreement is information, not failure.

The system must preserve: - evidence traceability; - model
independence; - uncertainty; - disagreement; - engine attribution.

The first product does not automatically publish validated knowledge.

------------------------------------------------------------------------

## 4. MIVE invariant

A successful MIVE execution requires **two independent intelligence
reports**.

For version 1:

``` text
Gemini IVE
+
OpenAI IVE
=
minimum valid MIVE input
```

Both providers must receive the **same canonical Context Pack**.

Gemini must not see OpenAI output.

OpenAI must not see Gemini output.

Neither provider may compare itself with the other provider.

A single-provider fallback is **not** a successful MIVE result.

If one required provider fails, report an incomplete/failed MIVE state
with the exact stage.

------------------------------------------------------------------------

## 5. Source corpus

The operator will place approved source books and documents in:

``` text
C:\Users\murenia\Documents\Projects\ION_ON\ION_MIVE_CLEANROOM_PACK_v1\corpus\source
```

Build a new clean corpus ingestion and retrieval path from these source
files.

Do not assume an old vector index is authoritative.

Each retrieved evidence item must remain traceable through stable
identifiers.

Minimum evidence metadata:

-   document ID;
-   source ID;
-   title;
-   content;
-   similarity/relevance score;
-   page/location when available;
-   chunk ID when available;
-   ingestion/index version when useful.

Retrieval stores and selects evidence. Retrieval does not interpret it.

------------------------------------------------------------------------

## 6. Canonical Context Pack

Construct one provider-independent Context Pack.

Both Gemini and OpenAI receive the same pack.

Required conceptual structure:

``` text
context_pack_id
question
documents
metadata
```

Each context document must include:

``` text
document_id
title
content
source
optional page
optional chunk_id
```

Context construction must not perform reasoning.

Any truncation must be explicit and measurable.

------------------------------------------------------------------------

## 7. IVE

IVE means **Intelligence Validation Engine**.

Each provider independently converts the same question and Context Pack
into one canonical structured intelligence report.

Required IVE fields:

``` text
engine_id
provider
model
question
abstract
highlights
claims
concepts
relations
evidence_mapping
uncertainty
confidence
optional raw_response
```

Each claim must include:

``` text
claim_id
statement
evidence_document_ids
confidence
```

Provider-native output may vary.

Provider-specific normalization belongs inside the provider adapter.

Do not allow Gemini-specific or OpenAI-specific output shapes to leak
into MIVE.

Do not invent missing semantic content merely to satisfy a schema.

------------------------------------------------------------------------

## 8. MIVE

MIVE means **Multi-Intelligence Validation Engine**.

MIVE compares valid independent IVE reports.

Required comparison dimensions:

-   agreements;
-   partial agreements;
-   conflicts;
-   unique findings by engine;
-   evidence overlap;
-   unsupported or weakly supported findings;
-   shared uncertainty;
-   overall comparison status.

Preserve engine attribution.

Do not manufacture consensus.

Do not discard unique findings simply because only one engine produced
them.

MIVE must be testable using synthetic IVE reports without live API
calls.

For version 1, MIVE must not silently invoke a third language model.

------------------------------------------------------------------------

## 9. Required user result

The local service must expose a public entry point equivalent to:

``` python
result = ask(question: str, top_k: int = 5)
```

The result must support a human-readable presentation containing:

1.  Question
2.  Primary Answer
3.  MIVE Assessment
4.  Agreements
5.  Disagreements / conflicts
6.  Unique findings
7.  Uncertainty
8.  Evidence
9.  Gemini usage/cost/latency
10. OpenAI usage/cost/latency
11. Total estimated cost
12. Total latency

Raw JSON may be available as technical detail but must not be the
default user experience.

Failures must be stage-specific:

``` text
configuration
corpus ingestion
retrieval
context pack
Gemini API
Gemini normalization
OpenAI API
OpenAI normalization
MIVE comparison
rendering
```

Do not hide the original exception chain during development.

Do not expose secrets.

------------------------------------------------------------------------

## 10. Cost and usage measurement

Cost telemetry is part of version 1.

For every request, record when available:

-   provider;
-   model;
-   input tokens;
-   output tokens;
-   total tokens;
-   latency;
-   estimated provider cost;
-   retrieval latency;
-   comparison latency;
-   total latency;
-   total estimated cost;
-   request status;
-   failure stage.

Pricing assumptions must be isolated and maintainable.

Unknown pricing must return unavailable/null rather than a fabricated
number.

Provider usage metadata is preferred over estimated token counting.

------------------------------------------------------------------------

## 11. Security and runtime configuration

Expected secrets include:

``` text
GEMINI_API_KEY
OPENAI_API_KEY
```

Vector-store configuration depends on your chosen implementation.

Rules:

-   never commit `.env`;
-   never print API keys;
-   never place fallback fake keys in production runtime;
-   imports must not require secrets;
-   imports must not initialize external clients;
-   imports must not open network connections;
-   validate runtime configuration immediately before the relevant
    external operation;
-   produce clear configuration errors.

Use one reproducible Python environment.

Document the exact setup and run commands.

------------------------------------------------------------------------

## 12. Implementation freedom

You may independently choose:

-   package architecture;
-   module names;
-   vector database or local vector implementation;
-   Python libraries;
-   configuration loader;
-   prompt implementation;
-   test framework;
-   internal result classes.

Do not inherit old implementation decisions merely because they existed
before.

The specifications and acceptance criteria are authoritative.

Prefer the smallest architecture that is:

-   testable;
-   observable;
-   replaceable;
-   explicit;
-   reproducible.

------------------------------------------------------------------------

## 13. Required implementation order

Follow this order:

``` text
1. Read all docs/ and schemas/
2. Inspect corpus/source/
3. Report corpus file inventory
4. Propose minimal architecture
5. Identify only blocking ambiguities
6. Create reproducible Python project
7. Implement corpus ingestion
8. Implement retrieval
9. Test retrieval
10. Implement Context Pack
11. Test Context Pack
12. Implement Gemini IVE adapter
13. Test Gemini normalization
14. Implement OpenAI IVE adapter
15. Test OpenAI normalization
16. Implement canonical IVE validation
17. Implement MIVE comparison
18. Test MIVE with synthetic reports
19. Implement ask()
20. Add mocked end-to-end tests
21. Run one controlled live Gemini + OpenAI smoke test
22. Verify cost and latency telemetry
23. Run full local acceptance
24. Only after local PASS, implement Streamlit
25. Run Streamlit end-to-end test
26. Stop at Local Working Product v0.1
```

Do not start Streamlit before the core `ask()` path passes.

Do not start cloud deployment before local Streamlit passes.

Do not build CRUD unless the operator explicitly authorizes it after
v0.1.

------------------------------------------------------------------------

## 14. Scope suppression

Version 1 does **not** include:

-   Claude as runtime provider;
-   knowledge graph publication;
-   ORKG integration;
-   autonomous agents;
-   user accounts;
-   billing;
-   multi-tenancy;
-   advanced CRUD;
-   background pipelines;
-   Big Bang knowledge capsule generation;
-   public production cloud;
-   redesign of ION epistemology.

Do not expand scope.

If you identify an attractive future feature, record it under
`DEFERRED.md` and continue the current acceptance path.

------------------------------------------------------------------------

## 15. Definition of success

The project is not complete because modules exist.

It is complete only when this is demonstrated:

``` text
Real user question
      ↓
Relevant corpus evidence
      ↓
Same Context Pack
      ↓
Real Gemini IVE PASS
+
Real OpenAI IVE PASS
      ↓
MIVE PASS
      ↓
Human-readable answer
      ↓
Evidence visible
      ↓
Uncertainty visible
      ↓
Token/cost/latency visible
      ↓
Streamlit displays the result
      ↓
Full tests PASS
```

Release label:

``` text
STATUS: LOCAL WORKING PRODUCT v0.1
```

Do not declare this status without executed evidence.

------------------------------------------------------------------------

## 16. First action

Before editing any file:

1.  Read `README.md`.
2.  Read `CLAUDE.md`.
3.  Read every file in `docs/`.
4.  Read every schema in `schemas/`.
5.  Inspect `corpus/source/`.
6.  Return a concise report with:

``` text
A. UNDERSTANDING
B. CORPUS INVENTORY
C. PROPOSED MINIMAL ARCHITECTURE
D. BLOCKING AMBIGUITIES
E. IMPLEMENTATION PHASES
F. FIRST PHASE ACCEPTANCE TEST
```

Do not write code in the first action.

Do not request the old Codex project.

Do not broaden the project.

After the operator approves the architecture, begin Phase 1.
