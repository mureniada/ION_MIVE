# ION / MIVE --- SESSION HANDOVER

Date: 2026-07-14 Project: ION_ON / ION_MIVE_CLEANROOM_PACK_v1

## PRIMARY OBJECTIVE

Finish the existing ION/MIVE product without architecture expansion.
Target: a user opens a browser, asks a question, and receives the
existing MIVE result from the frozen intelligence core.

Canonical path: Qdrant Retrieval → Context Pack → Gemini IVE → OpenAI
IVE → MIVE Comparator → User Answer → Uncertainty → Evidence →
Operational Metrics.

Constraints: no new conceptual modules, no corpus redesign, no third
model, no speculative optimization. Minimize operator time, API spend,
token spend, and engineering drift.

## VERIFIED CURRENT STATE

The intelligence core works live. The question "What is money?"
completed the full two-provider path.

Latest live metrics: - status: success - error_stage: null -
retrieved_chunks: 5 - context_documents: 5 - context_characters: 5965 -
Gemini: gemini-3.1-flash-lite; 1526 input / 894 output tokens;
\$0.0017225; 9884.573 ms - OpenAI: gpt-5.4-mini; 1702 input / 1117
output tokens; \$0.006303; 14395.973 ms - total estimated cost:
\$0.0080255 - retrieval latency: 101927.459 ms - total latency:
126351.475 ms

Output contains: question, primary_answer, mive_assessment, uncertainty,
evidence, operational_metrics, disclaimer.

## COMPLETED --- M7 LIVE MIVE CORE

Operational: - exactly one Gemini reasoning call - exactly one OpenAI
reasoning call - no third model - provider normalization and canonical
schema validation - MIVE preserves agreements, partial agreements,
disagreements, unique findings, weak support, uncertainty - telemetry
records models, tokens, latency, estimated cost

### OpenAI strict-schema surgical fix

Root cause: provider-facing `evidence_mapping` used a dynamic-key object
rejected by OpenAI strict structured outputs.

Fix: - removed `evidence_mapping` from provider-facing
IVE_RESPONSE_SCHEMA - normalization derives mapping from each claim's
cited evidence when absent - explicit mapping still respected -
canonical schema, domain models, retrieval, MIVE and renderer unchanged

Docker tests: 48/48 PASS. Commit: f372aec --- Fix OpenAI strict provider
schema and derive evidence mapping

## COMPLETED --- M8 FASTAPI / SSE TRANSPORT

Thin transport over frozen `core.ask()`.

Routes: - GET /health - POST /ask - GET
/ask/stream?question=...&top_k=...

SSE stages: retrieval → context_pack → gemini → openai → mive → answer

Termination: exactly one result or error event.

Docker tests: 59/59 PASS. Health verified live: HTTP 200
{"status":"ok"}.

Commit: 4ac05e874827eb8ac59016a1015f7dda708ddaf5 Add FastAPI and SSE
transport layer over frozen MIVE core

## SECURITY --- API KEY ROTATION

Old OpenAI and Gemini keys had appeared in chat before the message was
edited. Security decision: rotate both.

Completed: - new OpenAI key created under ION_ON - new Gemini key
created - local `.env` updated - backend restarted - /health passed -
real live MIVE call succeeded with both providers

REMAINING SECURITY ACTION: Delete/revoke the OLD OpenAI `ION_PLUS` key
and the OLD Gemini key.

Never paste API keys into ChatGPT or Codex. Edit `.env` locally only.

## M8.1 --- PERSISTENT EMBEDDING CACHE

Purpose: eliminate repeated Hugging Face model network downloads in
fresh Docker processes.

Prepared changes: - docker-compose.yml - backend/Dockerfile -
backend/tests/test_embedding_cache.py

Volume: hf_cache

Mount: hf_cache:/root/.cache/huggingface

Environment: HF_HOME=/root/.cache/huggingface
TRANSFORMERS_CACHE=/root/.cache/huggingface/transformers
SENTENCE_TRANSFORMERS_HOME=/root/.cache/huggingface/sentence-transformers

Codex local result: 66 total / 63 passed / 3 skipped. Expected Docker
result: 66 passed / 0 failed / 0 skipped.

Live observation: Docker created `ion_mive_cleanroom_pack_v1_hf_cache`.
The next live MIVE run downloaded the \~90 MB sentence-transformer
model. This is interpreted as first population of the newly created
cache volume.

M8.1 IS NOT YET CLOSED.

Required next verification: Run a fresh retrieval process and verify
there are NO Hugging Face download bars and the retrieval result remains
unchanged.

Command: docker compose run --rm backend python -c "from app.container
import build_core; from app.core.config import Settings;
c=build_core(Settings.load()); print(c.\_retrieval.retrieve('What is
money?',5)\[0\].chunk_id)"

Expected first chunk: sacred_economics_book_text::p12::c1

Then run: docker compose run --rm backend python run_tests.py

Required: TOTAL 66 / PASSED 66 / FAILED 0 / SKIPPED 0

Then: git status

Review only M8.1 changes, commit them, and confirm clean working tree.

## CURRENT PERFORMANCE ISSUE

Retrieval latency is extremely high.

Observed retrieval: \~65.5 s \~113.4 s \~101.9 s

Latest total: \~126.4 s

Latest provider latency: Gemini \~9.9 s OpenAI \~14.4 s

Current dominant latency appears to be retrieval startup / embedding
model acquisition or loading.

Policy: First close persistent cache verification. Then measure again.
If latency falls materially, preserve architecture. If retrieval remains
\~100 s, identify the exact latency split before changing code. No
embedding replacement or corpus re-ingestion without measurement.

## STRICT NEXT TASK ORDER

1.  Revoke old OpenAI ION_PLUS key and old Gemini key.
2.  Verify M8.1 second-run cache reuse.
3.  Run Docker tests: require 66/66.
4.  Inspect git status, commit only M8.1, confirm clean tree.
5.  Measure post-cache retrieval and total latency against baseline:
    retrieval 101927.459 ms; total 126351.475 ms; cost \$0.0080255.
6.  Build the minimal user-facing browser UI over existing FastAPI/SSE
    transport.
7.  Full tests, one live question, record metrics, commit, clean tree,
    then freeze/tag after operator review.

## MINIMUM WEB UI

-   ION / MIVE title
-   question input
-   Ask button
-   SSE progress stages
-   primary answer
-   MIVE assessment
-   uncertainty
-   evidence
-   operational metrics
-   disclaimer

Frontend constraints: thin frontend; no intelligence logic; no new
model; no new MIVE logic; no architecture expansion. Local browser
first. External exposure only after local product works.

## DO NOT DO

Do not rebuild corpus. Do not re-ingest 6,063 vectors. Do not change
embedding model or dimension. Do not change Qdrant collection. Do not
change retrieval contract. Do not add a third model, agents, ORKG,
Knowledge Capsules, Big Bang processing, or token-economy
implementation. Do not redesign MIVE or refactor the frozen core.

Those are future tracks.

## NEXT SESSION INSTRUCTION

Treat this handover as canonical operational state.

M8 is committed and verified. New OpenAI and Gemini keys are live and
working. M8.1 is prepared but still requires second-run cache reuse
verification, Docker 66/66 verification, git review, and commit.

Do not explain the architecture again. Do not expand scope. Guide the
operator one command at a time.

Mission: FINISH THE EXISTING MIVE PRODUCT.

Primary conservation rule: time + energy + tokens + money.

Target: a working browser-accessible MIVE product over the already
working frozen core.
