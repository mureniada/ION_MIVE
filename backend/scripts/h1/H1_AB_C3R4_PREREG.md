# H1 live A/B (C3/R4): preregistration

Prepared 2026-10-07 for David's "H1 LIVE A/B — PREPARE ONLY, DO NOT EXECUTE" (18:31Z). **Not executed.** No provider call, no staging change and no deploy were made to prepare it.

Labels used throughout: **VERIFIED** (checked in code, data or a live source, with the source named), **INFERRED**, **ESTIMATED**, **UNKNOWN**, and **PROPOSED** (a choice that waits for David's approval).

## 1. Status and authority

- **Operator decisions (David, 18:31Z):** the candidate cap is C3/R4; the mechanism is the structured-output schema `maxItems` only; arm A is the unchanged v0.4 IVE schema; no new prompt instruction; the IVE prompt is identical in both arms; same frozen 27-question set; same retrieval and Context Pack per pair; model `gemini-2.5-pro` unchanged; IVE thinking unchanged; sequential paired execution with a predetermined alternating AB/BA order; 0 composer calls; 3 passes × 27 questions = 81 paired rows; the frozen provider-aware classification and whole-pair replacement are reused; the recommended latency threshold is a median improvement of at least 0.5 s.
- **Proposals in this document** are marked PROPOSED and are listed in section 18. They take effect only when David approves this file.
- **Freeze:** once approved, this file's sha256 is the frozen identity. The harness refuses to start unless `H1AB_PREREG_SHA256` equals the sha256 of the file it is given (section 17).
- **Execution** needs a separate GO. The run is never retried, relaunched or run as a second instance.

## 2. Question and expectation

**Question.** Does capping the IVE's `concepts` at 3 and `relations` at 4, through the response schema alone, cut IVE latency by a material amount without degrading claims, evidence attribution, uncertainty, confidence, or downstream governance behaviour (the CG-A1 citation guard)?

**Expectation before data (ESTIMATED, H1 Step 0 / 0.5, offline):**

- Concepts and relations are a median 36.3% of the IVE's visible output.
- C3/R4 would remove about 0.8 s of the median IVE call, if the model wrote the same items and stopped at the caps.

This experiment is the first measurement of what the model actually does under the caps.

## 3. The one change

| | Arm A | Arm B |
|---|---|---|
| Response schema | `ive_common.IVE_RESPONSE_SCHEMA`, the module object itself, unchanged | a deep copy of it plus exactly `properties.concepts.maxItems = 3` and `properties.relations.maxItems = 4` |
| Canonical schema sha256 | `e4e577d629a3b7bc1309b22a45f6a698db2b747b403601e7cb1c5b288f39e5d8` (1,160 chars) | `dbe6bc784763fc9b2a555b991209e4cc66bbbf52879794fae54c5b39a3a0074e` (1,186 chars) |
| System prompt | `IVE_SYSTEM_PROMPT`, sha256 `6b7f7a6b…83f6` (330 chars) | the identical object |
| User prompt | built once per turn by the adapter from the turn's model input | the identical object |
| Model, backend | `gemini-2.5-pro`, the deployed IVE backend object | the same |
| Thinking | no thinking config sent (model default), as deployed | the same |

- **VERIFIED (repo, equal to deployed `e6880e7`):** the schema diff is exactly the two added keywords. The property order on the wire is kept.
- **VERIFIED offline (real google-genai 2.28.0 client, mock HTTP transport, no network):** the two HTTP request bodies differ only at:
  - `/generationConfig/responseJsonSchema/properties/concepts/maxItems = 3`;
  - `/generationConfig/responseJsonSchema/properties/relations/maxItems = 4`.

  They use the same URL (`…/v1beta/models/gemini-2.5-pro:generateContent`) and the same method. Headers differ only in content length. Neither body carries a `thinkingConfig`. Test: `test_wire_requests_differ_only_by_the_two_caps`.
- **VERIFIED (web, ai.google.dev/gemini-api/docs/structured-output, last updated 2026-09-23 UTC):** `maxItems` and `minItems` are listed among the supported JSON Schema keywords. The same page says "Not all JSON Schema features are supported", warns that very large or deeply nested schemas may be rejected, and advises validating values in the application. It makes no `gemini-2.5-pro`-specific statement.
- **UNKNOWN:** whether `gemini-2.5-pro` enforces `maxItems` while decoding. Every B output is therefore checked against schema B (G2, section 7).
- **No new prompt instruction** exists anywhere. A start check fails if the IVE system prompt sha256 differs (`ive_system_prompt`).

## 4. Design and order

- **Where:** inside the ION_MIVE staging container, deployment `2c91c45e-997c-4d8f-80e7-83be99e9b0af` (code `e6880e7`), in a new directory `/tmp/h1ab/`. This is the same path as H1 Step 0. `/tmp/h1cap/` is not touched.
- **Programme:** 3 sequential passes over the frozen 27-question set (sha256 `b6a414cd…b833`). That makes 81 scheduled slots, one pair per slot.
- **One turn per pair.** Each slot runs one normal `Core.ask(question)`, so retrieval and the Context Pack run once. Inside that turn, a wrapper on `GeminiBackend.generate` makes the IVE call twice, once per arm, with the identical system and user prompt objects. Both arms therefore receive the same retrieval and Context Pack by construction.
- **Order (PROPOSED reading of "predetermined alternating AB/BA"):** the 81 slots alternate AB, BA, AB, … in run order.
  - Slot = (pass − 1) × 27 + index; AB when the slot is even, BA when it is odd.
  - With 27 questions, every question meets both orders across the three passes: 41 AB and 40 BA.
  - A replacement keeps its slot's order.
  - Single source: `h1_ab_score.expected_order`. A start check verifies the alternation and balance (`order_alternates_and_balances`).
- **The turn is the unchanged baseline turn.** Arm A's result, or arm A's exception, goes back to the Core. Arm B's output never reaches the Core.
- **Arm B handling.** Arm B's text is normalized in the harness process with the app's own `parse_json` and `normalize`, with the arguments the adapter uses. A B failure is wrapped exactly as the adapter and `Core._run_engine` would wrap it, so both arms are classified by the same frozen rule. Test: `test_adapter_equivalent_classifies_like_the_core`, 7 failure kinds.
- **Arm A parity check.** Arm A is normalized the same way and must equal the Core's own report. A mismatch stops the run (section 6).
- **No composer.** Composition is skipped through the Core's own no-composer path, in the harness process only (`core._composer = None`), as in Step 0. Planned composer calls: 0.
- **No retries.** google-genai 2.28.0 never retries without retry options, and the backend sets none. VERIFIED in H1 Step 0 and re-checked by the start checks `backend_sets_no_retry` and `google_genai_version`.
- **No timeout effect.** The Core path has no timeout or deadline. VERIFIED: `orchestrator.py`, `gemini_ive/`, `ive_common.py`. The two arm calls are separate HTTP requests.
- **Guard (fail-closed, before the provider).** It refuses:
  - any Gemini call whose backend label is not `ive`;
  - a second IVE `generate()` in one turn;
  - an IVE call whose schema is not the module's schema object;
  - any IVE call beyond **324**. That is 81 slots × 2 attempts × 2 arms, the most the frozen replacement logic can ever make.
- **Recorded per arm:**
  - input digests (system, user, schema);
  - the frozen E3 tap row (usage, SDK latency, sanitized error, thinking config sent);
  - the verbatim output text and its sha256;
  - the normalized report;
  - the classification.
- **Recorded per pair:** the admitted evidence ids (`model_input.evidence[*].candidate_id`).
- **Cost and time (ESTIMATED from the 81 unchanged Phase A IVE calls; pricing verified 2026-10-06):**
  - Phase A per-call means: 1,133 input, 1,352 visible and 1,687 thinking tokens. That is about $0.032 per call.
  - 162 calls: about **$5.15**. At most about $10.31 at the 324-call cap.
  - Run time: about **67 minutes** (2 × 24.4 s per pair plus about 1 s), plus 30 s per replacement.

## 5. Provider faults, whole-pair replacement and the scored set (frozen)

- **Classification:** the frozen `classify_failure` (`voe_e3_index17_probe.py`, sha256 `2b63a7e3…ecb6`), imported unchanged by sha256. It returns PROVIDER_FAULT only when:
  - the wrapped error's direct cause is a google-genai `APIError` with an allowlisted code and status:
    - 429 RESOURCE_EXHAUSTED or Too Many Requests;
    - 500 INTERNAL or Internal Server Error;
    - 502 UNAVAILABLE, INTERNAL or Bad Gateway;
    - 503 UNAVAILABLE or Service Unavailable;
    - 504 DEADLINE_EXCEEDED or Gateway Timeout;
  - or the cause is exactly `httpx.ConnectError` or `httpx.ConnectTimeout`.

  Everything else is not a provider fault, for example a read timeout, a 400, a 402 or an invalid output.
- **Replacement:** the frozen rule of the v0.4/512 provider-aware reconfirmation (`voe_e3_pa_reconfirm.py`, sha256 `7f242c00…207c`; `REPLACEMENT_WAIT_S`, `Health` and its constants imported unchanged).
  - A PROVIDER_FAULT on either arm invalidates the whole pair.
  - The harness waits 30 s and reruns the whole pair once, in the same order.
  - A second fault leaves the slot UNRESOLVED. It is excluded and reported.
- **Scored set:** for each slot, the primary attempt if it has no PROVIDER_FAULT, else the replacement if it has none, else UNRESOLVED.
- **PENDING:** a faulted primary whose replacement never ran, because a stop fired first, is neither scored nor UNRESOLVED. It is reported, and the run counts as incomplete.
- **Report-only:** PROVIDER_FAULT calls are counted per arm. A fault pattern only on arm B could mean schema-induced server errors that the frozen allowlist counts as faults. That is reported, and the verdict stays as section 12 says.

## 6. Run stops (checked after every attempt, in this order)

1. **Harness guard:** a refusal, a non-IVE call or composition, a thinking config sent, an order mismatch, a prompt difference between arms, a request-schema identity mismatch, or a change to the module IVE schema → `STOPPED_HARNESS_GUARD`.
2. **Harness capture:** a provider text not captured exactly once, a capture that differs from the provider text, or an arm-A parity failure → `STOPPED_HARNESS_CAPTURE`.
3. **S1 (frozen F1):** a turn-level failure that is not a PROVIDER_FAULT, including arm A's own invalid output → `INCONCLUSIVE_IVE_OR_TURN_NON_PROVIDER_FAILURE`. Arm A is the unchanged system, so such a failure means the baseline itself failed.
4. **S2 (frozen F2):** HTTP 402 on any call → `STOPPED_HTTP_402`, with no billing or credential change. A 402 on arm A fails the turn, so the frozen F1-before-F2 order reports it as S1. The ledger keeps the 402, and the verdict treats both cases the same way (section 12).
5. **S3 (frozen F3):** 3 consecutive PROVIDER_FAULT calls, or 4 within 20 consecutive calls, over the ordered call sequence → `INCONCLUSIVE_PROVIDER_HEALTH`.
6. **S4 (PROPOSED, new):** 3 consecutive scored pairs that each carry a hard-fail event (section 7) → `STOPPED_SYSTEMATIC_B_HARD_FAIL`. If the server rejects or ignores the caps, the run then ends after about 6 IVE calls (about $0.19) instead of 162.

## 7. Hard FAIL gate (G1–G3)

Hard-fail events are evaluated only for scored pairs in which **arm A succeeded**. This is the PROPOSED reading of "new B-only". If arm A fails with a provider fault, the pair is replaced (section 5). If it fails for any other reason, the run stops under S1. Either way, the failure is reported and never counted against B.

- **G1, new B-only IVE failure.** Arm B failed (a call failure that is not a PROVIDER_FAULT, or an output the app would reject) while arm A succeeded.
  - Exception (PROPOSED): an HTTP 402 on arm B is an account state, not arm-B behaviour. S2 stops the run there, and it is not a G1 event.
  - Arm-B states set by the harness itself (refused by the guard, not run, or not scorable) are not G1 events. The guard or capture stop decides those (section 6).
  - Asymmetry, kept as the request words it (PROPOSED reading): a transient non-provider failure, for example a read timeout, is G1 and so FAIL when it hits arm B, but it stops the run under S1 and so gives INCONCLUSIVE when it hits arm A. VERIFIED: 0 non-provider failures in 270 earlier Gemini calls on this deployment (H1 Step 0: 27 IVE; Phase A: 81 IVE and 162 composer, 0 replacements; `VOE_LATENCY_H1_STEP0_MEASUREMENT.md`, `VOE_LATENCY_V04_512_PROVIDER_AWARE_RECONFIRMATION.md`). ESTIMATED 95% upper bound: about 1.1% per call.
- **G2, malformed or schema-invalid B output, or missing required fields.** B's raw output is parsed exactly as the app parses it and checked against schema B.
  - Any `MAX_ITEMS` violation (a cap not honoured) always counts.
  - Any other violation kind counts when arm A's output in the same pair has no violation of that kind: `WRONG_TYPE`, `MISSING_REQUIRED`, `EXTRA_PROPERTY` or `MIN_ITEMS`.
  - A B output the app cannot parse or normalize is already G1.
- **G3, an evidence-id attribution defect not present in A.** A defect in B that A does not have in the same pair:
  - `STRAY_CLAIM_ID`: a claim cites an id outside the turn's admitted evidence;
  - `STRAY_RELATION_ID`: a relation cites one;
  - `CLAIM_WITHOUT_EVIDENCE`: a claim cites none.

  The admitted set is `model_input.evidence[*].candidate_id`, the exact CG-A1 basis (VERIFIED `orchestrator.py:1020`; CG-A1 checks claims and relations).
- **Any scored pair with an event gives verdict FAIL (HARD_GATE).** There is no noise allowance.
- **CG-A1 does not run on these turns.** VERIFIED `orchestrator.py:543-551`: it runs only on turns that carry a conversation context, and these turns carry none, as at Step 0. The scorer evaluates offline what CG-A1 would decide for each arm (section 11).
- **Baseline (VERIFIED, H1 Step 0, 27 unchanged reports; `h1_ab_baseline.json`):**
  - stray claim ids: 0/27;
  - claims without evidence: 0/27;
  - schema violations: 0/27;
  - relation-only ids: present in 2/27, but Step 0 did not record the admitted set, so the baseline rate of `STRAY_RELATION_ID` is UNKNOWN.

  0/27 bounds the per-report rate at about 11% (95% upper bound, ESTIMATED). A G3 from noise alone is therefore possible, but none was seen at Step 0.

## 8. Quality endpoints and margins

All endpoints are differences B − A, over scored pairs where both arms succeeded. The resampling unit is the question (27 clusters).

| Endpoint | Measure | Test | Margin (PROPOSED) |
|---|---|---|---|
| Claim count | mean B − A claims per report | noninferiority | 0.5 claims |
| Evidence coverage | mean B − A share of the turn's admitted evidence ids cited by claims | noninferiority | 0.05 |
| Claim content | per question: mean cross-arm claim-statement similarity minus mean within-A similarity (across passes) | noninferiority | 0.10 |
| Uncertainty count | mean B − A uncertainty items per report | noninferiority | 0.25 items |
| Uncertainty content | as claim content, on the uncertainty items | noninferiority | 0.10 |
| Overall confidence | mean B − A report confidence | equivalence | ± 0.05 |

**States:**

- Noninferiority endpoints:
  - NONINFERIOR when the 95% CI lower bound > −margin;
  - INFERIOR when the upper bound < −margin;
  - otherwise NOT_SHOWN.
- Equivalence (confidence):
  - EQUIVALENT when the whole CI lies inside ±margin;
  - DIVERGENT when it lies entirely outside;
  - otherwise NOT_SHOWN.

**Similarity** is the symmetric mean best-match token Jaccard over casefolded word tokens. It is a lexical proxy for semantic equivalence; there is no embedding model and no LLM judge, because no provider calls are allowed. Subtracting the within-A similarity removes the IVE's own run-to-run rewording.

**Noise and chance to show noninferiority if the cap truly changes nothing (ESTIMATED, normal approximation).** Source: within-question variability of the 81 unchanged Phase A IVE calls (3 passes × 27; `e3pa_ive_sizing.csv`, sha256 `892e9e49…dd21`). Reproduced by `h1_ab_sizing.py`; output `h1_ab_sizing.json`, sha256 `a218f69e…c904`.

| Endpoint | Within-question SD | 95% CI half-width (81 pairs) | Chance |
|---|---|---|---|
| Claim count | 0.68 | 0.21 | about 99.6% |
| Uncertainty count | 0.75 | 0.23 | about 57% at 0.25; 73% at 0.30; 85% at 0.35 |
| Uncertainty characters | 118 | 36 | (warning only) |
| Coverage, content, confidence | UNKNOWN (no prior multi-pass data) | UNKNOWN | UNKNOWN |

A real drop of 0.25 uncertainty items per report would still show noninferiority about 2.5% of the time at margin 0.25, 6% at 0.30, and 13% at 0.35.

## 9. Uncertainty warnings (W1–W4)

Uncertainty is user-visible. Any one of these makes the verdict WARNING, never PASS, even when every margin holds:

- **W1, count reduced:** the 95% CI of mean B − A uncertainty items lies entirely below 0.
- **W2, text reduced:** the 95% CI of mean B − A uncertainty characters lies entirely below 0.
- **W3, emptied:** B has no uncertainty item where A has some in more pairs than the reverse, with an exact two-sided sign test p < 0.05.
- **W4, flattened:** the 95% CI of the cross-arm minus within-A uncertainty similarity lies entirely below 0.

ESTIMATED false-warning rate if the cap changes nothing: at most about 10% (four correlated one-sided 2.5% tails).

## 10. Latency and tokens

- **Latency** is the frozen tap's `sdk_latency_ms` per IVE call, the provider call alone. It is taken over scored pairs where both arms' calls returned OK.
- **Reported:**
  - A and B p50 and p90, with the full distributions;
  - the paired B − A distribution;
  - the median improvement, median(A − B), with its 95% CI;
  - the median improvement by order (AB vs BA);
  - visible tokens (`candidates_token_count`) and thinking tokens (`thoughts_token_count`) for A, B and B − A;
  - prompt and cached tokens per arm;
  - estimated cost per arm (ESTIMATED).
- **Thinking change:** the cap is reported as changing thinking-token usage when the 95% CI of mean B − A thinking tokens excludes 0. This has no verdict effect.
- **Materiality rule (David's 0.5 s threshold; the CI condition is PROPOSED):**
  - MATERIAL when median(A − B) ≥ 500 ms and the 95% cluster-bootstrap CI of that median lies above 0;
  - NOT_SHOWN when the median is ≥ 500 ms but the CI reaches 0;
  - NOT_MATERIAL when the median is < 500 ms. The observed gain did not reach the threshold; this does not prove the true gain is below it.
- **Operating characteristics (ESTIMATED).** Simulated by `h1_ab_sizing.py` from the 81 unchanged Phase A IVE latencies (within-question SD 3.1 s), with independent arms, 400 runs per row, seed 20261007:

  | True median gain | Median ≥ 0.5 s alone | Median ≥ 0.5 s and CI above 0 |
  |---|---|---|
  | 0 | 20% | 4% |
  | 0.5 s | 54% | 20% |
  | 0.8 s (Step 0.5 estimate) | 73% | 31% |
  | 1.2 s | 92% | 53% |
  | 1.6 s | 97% | 75% |
  | 2.0 s | 100% | 92% |

  Without the CI condition, a cap with no effect would be called material about 1 time in 5. With it, a true 0.8 s gain is shown about 1 time in 3. Adjacent calls share provider load, so the true pair noise may be lower and these figures pessimistic. That is INFERRED, not measured.
- **Report-only, "gain at equal thinking":** the intercept of the least-squares line of the A − B latency on the A − B thinking tokens, with a cluster-bootstrap CI.
  - It isolates the visible-output mechanism. VERIFIED on the 81 Phase A calls: latency ≈ 1.44 s + 7.56 ms per output token, R² 0.89, residual SD 1.35 s; visible and thinking tokens cost about the same per token.
  - It has no verdict effect.

## 11. Report-only comparisons (no verdict effect)

- **Claims:** counts per arm; pairs with identical statement sets (whitespace and case normalized); same-pair statement similarity.
- **Evidence:** coverage per arm; claim-id set Jaccard within the pair.
- **Uncertainty:** item counts and characters per arm.
- **Confidence:** per arm.
- **Abstract:** length per arm; cross-arm minus within-A token Jaccard, with CI.
- **Highlights:** count per arm; cross-arm minus within-A similarity, with CI.
- **Concepts and relations:**
  - raw emitted counts per arm;
  - A pairs over the caps;
  - B `MAX_ITEMS` violations;
  - schema-violation pairs per arm;
  - top-level key order per arm.
- **CG-A1, evaluated offline:**
  - pairs where A would fail, where B would fail, and where only B would fail;
  - relation-only ids per arm;
  - guard-id counts per arm;
  - defect counts per arm.
- **Run:** replacements, UNRESOLVED and PENDING slots, PROVIDER_FAULT calls per arm, HTTP 402 attempts.
- **Excluded pairs, by kind:** only A failed; both failed; B failed with a G1 event; B failed without one (an HTTP 402 or a harness state).

Abstract and highlights are report-only by design (PROPOSED). They are composer-facing, but there is no measured noise level for them, and gating on them would add multiplicity.

## 12. Verdict (ordered; the first matching step decides)

1. **INCONCLUSIVE** when:
   - harness integrity failed or a guard/capture stop occurred (HARNESS_INTEGRITY);
   - an HTTP 402 stopped the run, on either arm (HTTP_402);
   - provider health stopped it (PROVIDER_HEALTH);
   - a non-provider turn failure stopped it (IVE_OR_TURN_NON_PROVIDER_FAILURE).

   Hard-fail pairs seen before the stop are reported.
2. **FAIL (HARD_GATE):** any scored pair with a G1–G3 event, including an S4 stop.
3. **INCONCLUSIVE (INCOMPLETE):** not all 81 slots ended scored or UNRESOLVED (a PENDING slot has not ended), or the ledger is damaged.
4. **FAIL (QUALITY):** any endpoint INFERIOR or DIVERGENT.
5. **INCONCLUSIVE (NI_NOT_SHOWN):** any endpoint NOT_SHOWN or not evaluable.
6. **WARNING (UNCERTAINTY):** any of W1–W4.
7. **Latency:** MATERIAL → **PASS**; NOT_MATERIAL → **NOT_MATERIAL**; otherwise **INCONCLUSIVE (LATENCY_NOT_SHOWN)**.

PASS is reached only when no hard-fail event occurred, every margin is shown, no uncertainty warning fired, and the latency rule is met. A PASS licenses a staging proposal only. It is not Humanization acceptance and not a production change.

## 13. Statistics

- **Resampling:** pair-level differences B − A clustered by question (27 clusters).
- **CIs:** 95% percentile CIs from 10,000 cluster-bootstrap resamples (questions with replacement), seed 20261006, with linear-interpolation quantiles. Each endpoint reseeds, so no result depends on the order of computation.
- **Pairs used:** the quality endpoints use pairs where both arms succeeded. Latency and tokens use pairs where both calls returned OK.
- **No interim analysis** other than the run stops S1–S4. Nothing is re-run or re-scored with other settings. All thresholds, margins and the seed are fixed in `h1_ab_score.py` before data.

## 14. Baseline and noise sources (VERIFIED)

- **H1 Step 0 (27 unchanged IVE reports):**
  - `h1_ab_baseline.json`, sha256 `17bd625085a3f4252df1cd0880d98949eadc05600dfc063b0b022e0292836bd4` (7,208 bytes);
  - from the Step 0 ledger, sha256 `cb985f7bf5c687fc7f5e0aa4db96025917477b0f11a6416dde86fd4fbe249bbf`.

  It reports concepts > 3 in 17/27 reports and relations > 4 in 15/27.
- **H1 Step 0 measurement:** `h1s_summary.json`, sha256 `7d6433f6671cf39064ac571c8f38c7f676faa23d7918a2f5e4e4da8b2ff86a9a`. It reports:
  - claims median 6;
  - uncertainty items median 1 (mean 1.52, range 0–4);
  - IVE latency median 23.8 s;
  - visible tokens median 1,353 and thinking median 1,677.
- **Phase A (81 unchanged IVE calls, 3 passes × 27):** `e3pa_ive_sizing.csv`, sha256 `892e9e494aadadc108511ad43a8ceac39d09931e061c1f846b8531c60930dd21` (6,436 bytes). Its within-question figures:
  - uncertainty count differs across the three passes in 23 of 27 questions;
  - claim count differs in 19 of 27.
- **Sizing output:** `h1_ab_sizing.json`, sha256 `a218f69e654618ae06f55bf3ece081606da25b75d84249e2ceead460bf09c904`, written by `h1_ab_sizing.py` from the file above.

## 15. Identity (all checked before any provider call; 19 Step 0 checks + 18 A/B checks)

| Item | sha256 or value |
|---|---|
| A/B harness `voe_h1_ab_harness.py` | `0ff6752c770729d63f28c3408058b6e712fe0d253723473cf2031ef21aa7acaa` |
| Scorer `h1_ab_score.py` (pinned inside the harness) | `9a20742112a4299bb9d6c39dc445bf65322dce2da0bafa193155cec6ab46e8c7` |
| Sizing `h1_ab_sizing.py` (offline; not used by the run) | `15b56584bf7844fea637dc542ba2873fb40d5950e8b2228899482dc0c41efd7a` |
| Step 0 capture `voe_h1_ive_capture.py` | `4284a5ce8176a5ebf6b712bc2a6896325a5c0aa597cc64b71c039f14b69dbfb7` |
| Frozen E3 tap `voe_e3_paired_replay.py` | `1134c4f646c7c667d5d93c14d14bec07012be94096b7e492d92f25d2486865c7` |
| Frozen classifier `voe_e3_index17_probe.py` | `2b63a7e32d5d8dfe888d1eaf49103b566743dd1165319c76103e61ce524eecb6` |
| Frozen Phase A orchestrator `voe_e3_pa_reconfirm.py` | `7f242c00e8014078bcc16f5abaf640dc0274e2214ac60bbb89043f2ea5b2207c` |
| Questions (`e3q.json`, 27) | `b6a414cd8680c28e468a2fde5482800df8a9edb6d5b2e899119476726514b833` |
| Deployment | `2c91c45e-997c-4d8f-80e7-83be99e9b0af` (code `e6880e7`) |
| v0.4 profile | version 0.4; fingerprint `ba22801e…95b7`; composer system instruction `eba5b8c8…0e64`; deployed composer budget 512 |
| Model, SDK | `gemini-2.5-pro`; google-genai 2.28.0 |
| IVE system prompt | `6b7f7a6b6e66f88c69880ca0a780d367ca6375055050d4e0f3cf9e6ddcc883f6` |
| Schema A, schema B | `e4e577d6…5d8`, `dbe6bc78…074e` (section 3) |
| `orchestrator.py` | `73f8c89a83d9f102a34600318baae1a2e930d9f47442f8f67140d1d2e458fe4f` |
| `gemini_ive/backend.py` | `af468211d38a87874323c5efff324a4f0457b264911f81b3fc0f2a1f365b1e43` |
| `gemini_ive/adapter.py` | `89155a7bac3ba6741ab32caed4af0d00258e159c39fe2667beef3ab3d2bc7c4f` |
| `ive_common.py` | `d9af7362dea0c56b0d74b3c83e63bddf2c31084118ea0559b2e67d0151a12819` |

The four source files equal deployed `e6880e7`: VERIFIED by the H1 Step 0.5 12-file comparison on the PC, and re-checked in the container at launch (`source_files`).

## 16. Outputs and run procedure (only after GO)

**Outputs.** All files are new. The harness refuses to start, before any wiring, unless `H1AB_OUT_DIR` names a directory that does not exist yet.

- `h1ab_ledger.jsonl`, ASCII-escaped JSON (so no model output can stop a write), written with fsync after every line:
  - one `H1AB_META` line, with identity, all start checks, all hashes, both schemas and the plan;
  - one `H1AB_ATTEMPT` line per pair attempt;
  - one `H1AB_SUMMARY` line.
- stdout carries one `H1AB_PROGRESS` line per attempt and a final `H1AB_DONE`, `H1AB_STOP` or `H1AB_PREFLIGHT` line.
- The outputs never contain secrets or the environment. `RAILWAY_DEPLOYMENT_ID` is read by name only.
- Scoring is offline and read-only: `python h1_ab_score.py score <ledger> <prefix>` writes `<prefix>_summary.json` (every number, every state, the verdict) and `<prefix>_pairs.csv` (one row per scored pair).

**Procedure.**

1. On the PC, verify every sha256 in `SHA256SUMS.txt` and the approved sha256 of this file.
2. Upload these files to a **new** container directory `/tmp/h1ab/` with chunked base64 over `railway ssh`, as for Step 0:
   - `voe_h1_ab_harness.py`, `h1_ab_score.py`, `voe_h1_ive_capture.py`;
   - the three frozen modules;
   - `e3q.json`;
   - this file.
3. Re-verify every hash inside the container.
4. Run the preflight with `H1AB_PREFLIGHT_ONLY=1`. It must print `H1AB_PREFLIGHT` with `"provider_calls": 0`. Anything else means STOP and report.
5. Launch one detached process with `nohup setsid`, with a lock directory and a `run.exit` marker. A hidden PC poller mirrors `out/` and the logs.
6. The run is never relaunched and never runs as a second instance.
7. After exit, verify the hashes and run the scorer on the mirrored ledger.

## 17. Freeze and deviations

- **On approval:** this file's sha256 is recorded and passed as `H1AB_PREREG_SHA256`. The harness compares it with the file before anything else and records it in `H1AB_META`.
- **What the harness pins:** the scorer and the three frozen modules, by sha256.
- **Changes after approval:** any change to a margin, rule or file needs a new version of this file and a new approval, never after seeing data.
- **Deviations** during a run are reported as deviations. The verdict rule does not change.

## 18. Decisions needed from David before freezing

1. **Margins (section 8):**
   - claims 0.5;
   - coverage 0.05;
   - claim content 0.10;
   - uncertainty count 0.25 (strict: about 57% chance to show noninferiority if nothing changes; 0.35 raises that to about 85% but lets a real 0.25-item drop pass about 13% of the time instead of 2.5%);
   - uncertainty content 0.10;
   - confidence ±0.05.
2. **Latency rule (section 10):** David's median ≥ 0.5 s, plus the PROPOSED CI condition. Without the condition, a no-effect cap is called material about 20% of the time; with it, about 4%, but a true 0.8 s gain is shown only about 31% of the time.
3. **S4 systematic-failure stop (section 6):** new; it stops the run after 3 consecutive hard-fail pairs.
4. **Readings of the request:**
   - G1–G3 apply only when A succeeded;
   - an HTTP 402 is never a B failure;
   - a transient non-provider failure on B is G1 (FAIL), while the same failure on A stops the run (INCONCLUSIVE); none was seen in 270 earlier calls (section 7);
   - the AB/BA alternation follows run order;
   - abstract and highlights are report-only.
