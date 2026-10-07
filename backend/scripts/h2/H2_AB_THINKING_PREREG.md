# H2 live A/B (IVE thinking budget 1280): preregistration

Prepared 2026-10-07 for David's "OPERATOR DECISION — H2 1280, FINAL PREPARATION ONLY" (21:25Z). **Not executed.** No provider call, no staging change and no deploy were made to prepare it. Execution needs a separate GO.

Labels used throughout: **VERIFIED** (checked in code, data or a live source, with the source named), **INFERRED**, **ESTIMATED**, **UNKNOWN**.

## 1. Status and authority

- **Operator decisions (David):**
  - 21:13Z: H1 is DEFERRED / NOT PURSUED (not a FAIL); H2 is the IVE thinking budget; a live H2 is worth running only for a median gain of at least 2.0 s.
  - 21:25Z: **IVE thinking budget = 1280** (not 1024, no 1024 experiment); 81 pairs / 3 passes; finalize the quality guardrails, calibrate the abstract and highlights margins offline, freeze this file and the harness and scorer hashes.
- **Design basis:** `VOE_LATENCY_H2_THINKING_CALIBRATION.md` and `H2_THINKING_PREREG_DESIGN.md` (21:20Z). Readings that were PROPOSED there or in the H1 prereg are finalized here under the 21:25Z instruction and listed in section 18.
- **Freeze:** this file's sha256 is the frozen identity. The harness refuses to start unless `H2AB_PREREG_SHA256` equals the sha256 of the file it is given (section 17).
- **Execution** needs a separate GO. The run is never retried, relaunched or run as a second instance.
- **Not combined with H1.** No schema change in either arm.

## 2. Question and expectation

**Question.** Does an IVE thinking budget of 1280 cut IVE latency by at least 2.0 s on average without degrading claims, evidence attribution, uncertainty, confidence, abstract, highlights, or downstream governance behaviour (the CG-A1 citation guard)?

**Expectation before data (ESTIMATED, offline, `VOE_LATENCY_H2_THINKING_CALIBRATION.md`):**

- Unchanged IVE thinking: median 1,657 tokens (81 Phase A calls); latency ≈ 1.60 s + 7.65 ms per thinking token + 7.33 ms per visible token (R² 0.89).
- Median gain **2.9 s** if the budget only truncates (M1) to **6.0 s** if the model compresses as it did with the composer at 512 (M2); p90 gain 6.6–9.7 s.
- Thinking cut 23% (M1) to 48% (M2) at the median. **Quality risk: HIGH.** The IVE writes the claims, the attribution and the uncertainty.

## 3. The one change

| | Arm A | Arm B |
|---|---|---|
| Thinking config | none sent (provider default, dynamic), as deployed | `ThinkingConfig(thinking_budget=1280)` |
| How | the deployed IVE `GeminiBackend` object | a shallow copy of that object whose only difference is `_thinking_budget = 1280`; the app's own `GeminiBackend.generate` then sends the config (`gemini_ive/backend.py`, sha256 `af468211…1e43`) |
| Response schema | `ive_common.IVE_RESPONSE_SCHEMA`, the module object, unchanged (canonical sha256 `e4e577d6…5d8`) | the identical object |
| System prompt | `IVE_SYSTEM_PROMPT`, sha256 `6b7f7a6b…83f6` | the identical object |
| User prompt | built once per turn by the adapter | the identical object |
| Model, SDK client | `gemini-2.5-pro`; google-genai 2.28.0 | the same model and the **same SDK client object** (one connection pool) |

- **VERIFIED offline (real google-genai 2.28.0 client, mock HTTP transport, no network):** the two HTTP request bodies differ only by `/generationConfig/thinkingConfig = {"thinking_budget": 1280}`. Same URL (`…/models/gemini-2.5-pro:generateContent`), method and headers; one client is created for both arms. Test: `test_wire_requests_differ_only_by_the_thinking_budget`.
- **VERIFIED (this project, E3):** the same SDK and code path already send a thinking budget for the deployed composer (512), and it binds on `gemini-2.5-pro`: 0 of 240 budgeted calls exceeded 512; median thinking 345 tokens.
- **VERIFIED (web, Firebase AI Logic "Thinking", updated 2026-10-06):** Gemini 2.5 Pro budgets range 128–32,768; thinking cannot be turned off. Google's thinking guide says the model "might overflow or underflow the token budget". B's adherence is therefore recorded (section 11), not assumed.
- **No new prompt instruction** anywhere. A start check fails if the IVE system prompt sha256 differs (`ive_system_prompt`).
- **No product code change.** The change exists only inside the harness process.

## 4. Design and order

- **Where:** inside the ION_MIVE staging container, deployment `2c91c45e-997c-4d8f-80e7-83be99e9b0af` (code `e6880e7`), in a new directory `/tmp/h2ab/`. `/tmp/h1cap/` is not touched. No staging configuration change.
- **Programme:** 3 sequential passes over the frozen 27-question set (sha256 `b6a414cd…b833`): **81 scheduled slots, one pair per slot, 162 IVE calls** when no replacement is needed.
- **One turn per pair.** Each slot runs one normal `Core.ask(question)`, so retrieval and the Context Pack run once. Inside that turn, a wrapper on `GeminiBackend.generate` makes the IVE call twice, once per arm, with the identical prompt and schema objects.
- **Order:** the 81 slots alternate AB, BA, AB, … in run order. Slot = (pass − 1) × 27 + index; AB when even. Every question meets both orders across the three passes (41 AB, 40 BA in all). A replacement keeps its slot's order. Single source: `h2_ab_score.expected_order`; start check `order_alternates_and_balances`.
- **The turn is the unchanged baseline turn.** Arm A's result or exception goes back to the Core. Arm B's output never reaches the Core.
- **Arm B handling.** B's text is normalized in-process with the app's own `parse_json` and `normalize`; a B failure is wrapped exactly as the adapter and Core would wrap it, so both arms are classified by the same frozen rule. Arm A is normalized the same way and must equal the Core's report (parity check).
- **No composer.** Composition is skipped through the Core's own no-composer path in the harness process only (`core._composer = None`). Planned composer calls: 0. The deployed composer stays at its confirmed 512 baseline.
- **No retries** (google-genai 2.28.0 without retry options) and **no timeout effect** (no deadline on the Core path), as verified for H1.
- **Guard (fail-closed, before the provider).** It refuses any Gemini call whose backend label is not `ive`, a second IVE `generate()` in one turn, an IVE call whose schema is not the module's schema object, and any IVE call beyond **324** (81 slots × 2 attempts × 2 arms, the most the frozen replacement logic can make).
- **Recorded per arm:** input digests; the frozen E3 tap row (usage, SDK latency, sanitized error, `thinking_config_sent`, `thinking_budget_sent`); verbatim output text and sha256; normalized report; classification. **Per pair:** the admitted evidence ids (the CG-A1 basis).
- **Cost and time (ESTIMATED; pricing verified 2026-10-06, $1.25/M input, $10/M output incl. thinking):** arm A about $0.032 per call; arm B about $0.024–0.028. A clean run is about **$4.7** and about **1.1 hours** (81 × (24.4 s + about 20 s + about 1 s)); at the 324-call cap at most about $9.5. Each replacement adds 30 s.

## 5. Provider faults, whole-pair replacement and the scored set (frozen)

- **Classification:** the frozen `classify_failure` (`voe_e3_index17_probe.py`, sha256 `2b63a7e3…ecb6`), imported unchanged. PROVIDER_FAULT only for an allowlisted google-genai `APIError` (429 RESOURCE_EXHAUSTED; 500 INTERNAL; 502; 503 UNAVAILABLE; 504 DEADLINE_EXCEEDED, with their HTTP reason phrases) or a direct `httpx.ConnectError` / `httpx.ConnectTimeout`. Everything else (a read timeout, a 400, a 402, an invalid output) is not a provider fault.
- **Replacement:** the frozen rule of the v0.4/512 provider-aware reconfirmation (`voe_e3_pa_reconfirm.py`, sha256 `7f242c00…207c`). A PROVIDER_FAULT on either arm invalidates the whole pair; wait 30 s and rerun the whole pair once in the same order; a second fault leaves the slot UNRESOLVED (excluded and reported).
- **Scored set:** per slot, the primary if it has no PROVIDER_FAULT, else the replacement if it has none, else UNRESOLVED. A faulted primary whose replacement never ran because a stop fired first is PENDING; the run then counts as incomplete.
- **Report-only:** PROVIDER_FAULT calls per arm.

## 6. Run stops (checked after every attempt, in this order)

1. **Harness guard** → `STOPPED_HARNESS_GUARD`: a refusal; a non-IVE call or composition; **a thinking config that is not the preregistered one** (any config on arm A, or arm B without exactly `thinking_budget = 1280`); an order mismatch; a prompt difference between arms; a request-schema identity mismatch; a change to the module IVE schema.
2. **Harness capture** → `STOPPED_HARNESS_CAPTURE`: a provider text not captured exactly once, or an arm-A parity failure.
3. **S1 (frozen F1)** → `INCONCLUSIVE_IVE_OR_TURN_NON_PROVIDER_FAILURE`: a turn-level failure that is not a PROVIDER_FAULT, including arm A's own invalid output.
4. **S2 (frozen F2)** → `STOPPED_HTTP_402`: HTTP 402 on any call. **STOP, with no billing or credential change.**
5. **S3 (frozen F3)** → `INCONCLUSIVE_PROVIDER_HEALTH`: 3 consecutive PROVIDER_FAULT calls, or 4 within 20 consecutive calls.
6. **S4** → `STOPPED_SYSTEMATIC_B_HARD_FAIL`: 3 consecutive scored pairs that each carry a hard-fail event (section 7).

## 7. Hard FAIL gate (G1–G3)

Evaluated only for scored pairs in which **arm A succeeded** (a failing A is replaced or stops the run, and is never counted against B).

- **G1, new B-only IVE failure:** arm B failed (a call failure that is not a PROVIDER_FAULT, or output the app rejects) while arm A succeeded. An HTTP 402 on B is an account state (S2), not G1. Harness states (refused, not run) are decided by the guard or capture stop.
- **G2, malformed or schema-invalid B output, or missing required fields:** B's raw output is parsed exactly as the app parses it and checked against the unchanged schema; a violation counts when arm A's output in the same pair has no violation of that kind (`WRONG_TYPE`, `MISSING_REQUIRED`, `EXTRA_PROPERTY`, `MIN_ITEMS`, `MAX_ITEMS`). Output the app cannot parse or normalize is already G1.
- **G3, an evidence-id attribution defect not present in A:** `STRAY_CLAIM_ID`, `STRAY_RELATION_ID` or `CLAIM_WITHOUT_EVIDENCE` in B but not in A. The admitted set is `model_input.evidence[*].candidate_id`, the CG-A1 basis. A B-only CG-A1 failure is therefore a G3 event.
- **Any scored pair with an event gives FAIL (HARD_GATE).** No noise allowance.
- **Baseline (VERIFIED, H1 Step 0, 27 unchanged reports):** stray claim ids 0/27, claims without evidence 0/27, schema violations 0/27.

## 8. Quality endpoints and margins

All endpoints are B − A over scored pairs where both arms succeeded; the resampling unit is the question (27 clusters). Each margin is the narrowest that an unchanged system passes at least about 95% of the time at 81 pairs.

| Endpoint | Measure | Test | Margin | Source |
|---|---|---|---|---|
| Claim count | mean B − A claims per report | noninferiority | 0.45 claims | `VOE_LATENCY_H1_RULE_CALIBRATION.md` (81-pair set) |
| Evidence coverage | mean B − A share of admitted evidence ids cited by claims | noninferiority | 0.05 | same |
| Claim content | per question: mean cross-arm claim-statement similarity minus mean within-A similarity | noninferiority | 0.04 | same |
| Uncertainty count | mean B − A uncertainty items per report | noninferiority | 0.45 items | same |
| Uncertainty content | as claim content, on uncertainty items | noninferiority | 0.125 | same |
| Overall confidence | mean B − A report confidence | equivalence | ± 0.02 | same |
| **Abstract content** | per question: mean cross-arm abstract token Jaccard minus mean within-A | noninferiority | **⟨ABSTRACT_MARGIN⟩** | section 8.1 |
| **Highlights content** | as claim content, on the highlights | noninferiority | **⟨HIGHLIGHTS_MARGIN⟩** | section 8.1 |

**States.** Noninferiority: NONINFERIOR when the 95% CI lower bound > −margin; INFERIOR when the upper bound < −margin; otherwise NOT_SHOWN. Equivalence: EQUIVALENT when the CI lies inside ±margin; DIVERGENT when entirely outside; otherwise NOT_SHOWN.

**Similarity** is token Jaccard over casefolded word tokens (abstract), or the symmetric mean best-match token Jaccard over a list (claims, uncertainty, highlights). It is a lexical proxy; no embedding model or LLM judge, because no provider calls are allowed. Subtracting the within-A similarity removes the IVE's own run-to-run rewording.

**Joint false-fail risk (ESTIMATED):** an unchanged system passes all six H1-calibrated endpoints about 75% of the time at 81 pairs; with two more endpoints at about 95% each, about 68–70% if independent. Noise alone gives NOT_SHOWN (INCONCLUSIVE), never FAIL.

### 8.1 Abstract and highlights calibration

⟨CALIBRATION_SECTION⟩

## 9. Uncertainty warnings (W1–W4)

Any one makes the verdict WARNING, never PASS, even when every margin holds:

- **W1, count reduced:** the 95% CI of mean B − A uncertainty items lies entirely below 0.
- **W2, text reduced:** the 95% CI of mean B − A uncertainty characters lies entirely below 0.
- **W3, emptied:** B has no uncertainty item where A has some, in more pairs than the reverse, exact two-sided sign test p < 0.05.
- **W4, flattened:** the 95% CI of the cross-arm minus within-A uncertainty similarity lies entirely below 0.

ESTIMATED false-warning rates for an unchanged system (H1 null simulation on the 215 stored reports): W1 3.2%, W2 4.6%, W3 1.3%, W4 2.6%; any warning 9.7%. A systematic reduction that crosses a margin is a quality FAIL (section 8). This guards the open UNCERTAINTY-CARRY watchpoint.

## 10. Latency and tokens

- **Latency** is the frozen tap's `sdk_latency_ms` per IVE call, over scored pairs where both calls returned OK.
- **Rule (operator threshold 2.0 s):**
  - **MATERIAL** when mean(A − B) ≥ **2,000 ms** and the one-sided 95% cluster-bootstrap lower bound of that mean is > 0 (the 5th percentile of 10,000 bootstrap means);
  - NOT_SHOWN when the mean is ≥ 2,000 ms but the bound is ≤ 0;
  - NOT_MATERIAL when the mean is < 2,000 ms (the observed gain did not reach the threshold).
- **Operating characteristics at 81 pairs (ESTIMATED; pair-mean noise 0.49 s; `h2_thinking_calibration.json`):**

  | True gain | P(MATERIAL) |
  |---|---|
  | 0 | about 0% |
  | 1 s | 2.5% |
  | 2 s | 49% (capped near 50%: 2 s is the threshold) |
  | 3 s | 98% |
  | 4 s | 100% |
  | projected 1280 profile (M1 or M2) | 100% |

- **Report-only:** A and B p50/p90 and distributions; paired B − A; median gain with its 95% CI; Hodges–Lehmann; mean and median by order; "gain at equal thinking" (intercept of A − B latency on A − B thinking tokens); visible, thinking, prompt and cached tokens per arm and B − A; estimated cost per arm.

## 11. Report-only comparisons (no verdict effect)

- **Thinking adherence:** B thinking-token distribution; number and share of B calls above 1,280; A thinking distribution.
- **Visible output:** B − A visible tokens (UNKNOWN before data whether less thinking changes visible length).
- **Claims, evidence, uncertainty, confidence:** per-arm distributions; identical statement sets; same-pair similarities.
- **Abstract and highlights:** length and count per arm; same-pair similarities.
- **Schema:** raw concepts and relations counts per arm; schema-violation pairs per arm; top-level key order per arm.
- **CG-A1, evaluated offline:** pairs where A, B, or only B would fail; relation-only ids; guard-id counts; defect counts per arm. CG-A1 does not run on these turns (they carry no conversation context), as at H1 Step 0.
- **Run:** replacements, UNRESOLVED and PENDING slots, PROVIDER_FAULT calls per arm, HTTP 402 attempts; excluded pairs by kind.

## 12. Verdict (ordered; the first matching step decides)

1. **INCONCLUSIVE** when harness integrity failed or a guard/capture stop occurred (HARNESS_INTEGRITY); an HTTP 402 stopped the run (HTTP_402); provider health stopped it (PROVIDER_HEALTH); a non-provider turn failure stopped it (IVE_OR_TURN_NON_PROVIDER_FAILURE). Hard-fail pairs seen before the stop are reported.
2. **FAIL (HARD_GATE):** any scored pair with a G1–G3 event, including an S4 stop.
3. **INCONCLUSIVE (INCOMPLETE):** not all 81 slots ended scored or UNRESOLVED, or the ledger is damaged.
4. **FAIL (QUALITY):** any endpoint INFERIOR or DIVERGENT.
5. **INCONCLUSIVE (NI_NOT_SHOWN):** any endpoint NOT_SHOWN or not evaluable.
6. **WARNING (UNCERTAINTY):** any of W1–W4.
7. **Latency:** MATERIAL → **PASS**; NOT_MATERIAL → **NOT_MATERIAL**; otherwise **INCONCLUSIVE (LATENCY_NOT_SHOWN)**.

A PASS licenses a staging proposal only. It is not Humanization acceptance and not a production change. Composer-level checks (claim loss, uncertainty carry, blocking, rule 8(d)) need composed answers and are **not part of this experiment**; a composer-level second stage would need its own approval.

## 13. Statistics

- Pair-level differences B − A clustered by question (27 clusters).
- 95% percentile CIs from 10,000 cluster-bootstrap resamples, seed 20261006, linear-interpolation quantiles; each endpoint reseeds.
- Quality endpoints use pairs where both arms succeeded; latency and tokens use pairs where both calls returned OK.
- No interim analysis other than stops S1–S4. Nothing is re-run or re-scored with other settings. All thresholds, margins and the seed are fixed in `h2_ab_score.py` before data.

## 14. Baseline and noise sources (VERIFIED)

- Phase A, 81 unchanged IVE calls: `e3pa_ive_sizing.csv`, sha256 `892e9e494aadadc108511ad43a8ceac39d09931e061c1f846b8531c60930dd21`.
- 240 budgeted composer pairs (E3, 512 vs none): `e3pa_pairs.csv`, `e3v04_pairs.csv`, `part8_pairs.csv`.
- H2 thinking calibration: `h2_thinking_calibration.json`, sha256 `185263f97d1f30472c41501c9466ddb3d88af0fe2fdb2a47d23ae5febeb41442`.
- H1 rule calibration (215 stored unchanged reports, PC): `h1_rule_calibration.json`, sha256 `27c19416669b4ae6977b636269f5e48637318030edc328bc001af42fb0f29611`.
- H1 Step 0 baseline: `h1_ab_baseline.json`, sha256 `17bd625085a3f4252df1cd0880d98949eadc05600dfc063b0b022e0292836bd4`.

## 15. Identity (all checked before any provider call; 19 Step 0 checks + 19 A/B checks)

| Item | sha256 or value |
|---|---|
| A/B harness `voe_h2_ab_harness.py` | `⟨HARNESS_SHA256⟩` |
| Scorer `h2_ab_score.py` (pinned inside the harness) | `⟨SCORER_SHA256⟩` |
| Content-margin calibration `h2_content_margin_calibration.py` (offline; not used by the run) | `⟨CALIB_SHA256⟩` |
| Step 0 capture `voe_h1_ive_capture.py` | `4284a5ce8176a5ebf6b712bc2a6896325a5c0aa597cc64b71c039f14b69dbfb7` |
| Frozen E3 tap `voe_e3_paired_replay.py` | `1134c4f646c7c667d5d93c14d14bec07012be94096b7e492d92f25d2486865c7` |
| Frozen classifier `voe_e3_index17_probe.py` | `2b63a7e32d5d8dfe888d1eaf49103b566743dd1165319c76103e61ce524eecb6` |
| Frozen Phase A orchestrator `voe_e3_pa_reconfirm.py` | `7f242c00e8014078bcc16f5abaf640dc0274e2214ac60bbb89043f2ea5b2207c` |
| Questions (`e3q.json`, 27) | `b6a414cd8680c28e468a2fde5482800df8a9edb6d5b2e899119476726514b833` |
| Deployment | `2c91c45e-997c-4d8f-80e7-83be99e9b0af` (code `e6880e7`) |
| v0.4 profile | version 0.4; fingerprint `ba22801e…95b7`; composer system instruction `eba5b8c8…0e64`; deployed composer budget 512 |
| Model, SDK | `gemini-2.5-pro`; google-genai 2.28.0 |
| IVE thinking budget | arm A none (deployed IVE backend `_thinking_budget is None`, start check `ive_backend_no_thinking_budget`); arm B 1280 (`arm_b_budget_1280`, `arm_b_backend_differs_only_in_budget`) |
| IVE system prompt | `6b7f7a6b6e66f88c69880ca0a780d367ca6375055050d4e0f3cf9e6ddcc883f6` |
| Schema (both arms) | `e4e577d629a3b7bc1309b22a45f6a698db2b747b403601e7cb1c5b288f39e5d8` |
| `orchestrator.py` | `73f8c89a83d9f102a34600318baae1a2e930d9f47442f8f67140d1d2e458fe4f` |
| `gemini_ive/backend.py` | `af468211d38a87874323c5efff324a4f0457b264911f81b3fc0f2a1f365b1e43` |
| `gemini_ive/adapter.py` | `89155a7bac3ba6741ab32caed4af0d00258e159c39fe2667beef3ab3d2bc7c4f` |
| `ive_common.py` | `d9af7362dea0c56b0d74b3c83e63bddf2c31084118ea0559b2e67d0151a12819` |

## 16. Outputs and run procedure (only after GO)

**Outputs.** All new; the harness refuses to start, before any wiring, unless `H2AB_OUT_DIR` names a directory that does not exist yet.

- `h2ab_ledger.jsonl` (ASCII-escaped JSON, fsync per line): one `H2AB_META` line (identity, start checks, hashes, schema, `thinking_budget_b`, plan), one `H2AB_ATTEMPT` line per pair attempt, one `H2AB_SUMMARY` line.
- stdout: one `H2AB_PROGRESS` line per attempt and a final `H2AB_DONE`, `H2AB_STOP` or `H2AB_PREFLIGHT` line. No secrets or environment; `RAILWAY_DEPLOYMENT_ID` is read by name only.
- Scoring is offline and read-only: `python h2_ab_score.py score <ledger> <prefix>` writes `<prefix>_summary.json` and `<prefix>_pairs.csv`.

**Procedure.**

1. On the PC, verify every sha256 in `SHA256SUMS.txt` and the frozen sha256 of this file.
2. Upload to a **new** container directory `/tmp/h2ab/` with chunked base64 over `railway ssh`: `voe_h2_ab_harness.py`, `h2_ab_score.py`, `voe_h1_ive_capture.py`, the three frozen modules, `e3q.json`, this file.
3. Re-verify every hash inside the container.
4. Preflight with `H2AB_PREFLIGHT_ONLY=1`: it must print `H2AB_PREFLIGHT` with `"provider_calls": 0`; anything else means STOP and report.
5. Launch one detached process (`nohup setsid`) with a lock directory and a `run.exit` marker; a hidden PC poller mirrors `out/` and the logs.
6. Never relaunched, never a second instance.
7. After exit, verify the hashes and run the scorer on the mirrored ledger.

## 17. Freeze and deviations

- This file's sha256 is passed as `H2AB_PREREG_SHA256`; the harness compares it with the file before anything else and records it in `H2AB_META`.
- The harness pins the scorer and the three frozen modules by sha256.
- Any change to a margin, rule or file needs a new version of this file and a new approval, never after seeing data.
- Deviations during a run are reported as deviations; the verdict rule does not change.

## 18. Decisions

**Recorded (David):**

1. 21:13Z: H1 deferred (not FAIL); H2 = IVE thinking budget; ≥ 2.0 s median or no live H2.
2. 21:25Z: budget 1280; 81 pairs / 3 passes; finalize the guardrails; calibrate abstract and highlights offline; freeze; no live call, no staging change, no deploy, no H1 work, no 1024 experiment.

**Finalized under the 21:25Z instruction (PROPOSED in the H2 design or the H1 prereg):**

1. Arm B is a shallow copy of the deployed IVE backend with only `_thinking_budget = 1280`, sharing arm A's SDK client.
2. Margins of section 8: the H1-calibrated 81-pair set, and the abstract and highlights margins of section 8.1.
3. Latency rule of section 10 at 2.0 s.
4. IVE call cap 324.
5. S4 systematic-failure stop after 3 consecutive hard-fail pairs.
6. G1–G3 apply only when A succeeded; an HTTP 402 is never a B failure; a transient non-provider failure on B is G1, the same on A stops the run (none seen in 270 earlier calls on this deployment).
7. G2 counts a schema-violation kind only when A has none of that kind in the same pair.
8. AB/BA alternation follows run order.
9. Abstract and highlights are gating noninferiority endpoints (they were report-only in H1).
10. Composer-level checks are outside this experiment.
