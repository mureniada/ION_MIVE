# ION E4 — Integrated Governed Pilot Closure Record

**Verification performed:** 2026-09-03 (E4D runtime verification).
**Document materialized:** 2026-09-04 (E4E closure materialization).
The filename carries the verification date, which is the date the bound
evidence was produced.

**Type:** Factual closure record. It records measured state and bound
identities. It authorises no commit, push, deployment, content selection, or
scope expansion.

**Status:**

```
E4 = IMPLEMENTED / VERIFIED — READY FOR EXACT COMMIT AUTHORIZATION
E4 = NOT YET CLOSED / DURABLE
```

Durable closure requires a later, separately authorised exact commit and
durable closure binding (E4F). Nothing in this document constitutes one.

Companion contract: `docs/ION_E4_INTEGRATED_GOVERNED_PILOT_CONTRACT_v1.md`.

---

## 1. Phase acceptance

| Phase | Result |
|---|---|
| E4A — read-only integrated pilot reality check | **PASS** |
| E4B — pilot assembly / identity decision | **PASS / CLOSED** |
| E4C — bounded integration implementation | **PASS** |
| E4D — end-to-end integrated pilot verification | **PASS** |
| E4 | **READY FOR CLOSURE MATERIALIZATION** |

---

## 2. Repository and worktree identity

```
REPOSITORY = C:/Users/murenia/Documents/Projects/ION_ON/ION_MIVE_CLEANROOM_PACK_v1
WORKTREE   = .claude/worktrees/e4c-bounded-integration-785cc0
BRANCH     = claude/e4c-bounded-integration-785cc0
HEAD       = a58c35a2b9d113f77877b2a86929443068bd2884

DURABLE PREDECESSOR REF    = e3-derived-index-lifecycle-20260903
DURABLE PREDECESSOR TARGET = a58c35a2b9d113f77877b2a86929443068bd2884

REPOSITORY MOVEMENT = NONE
STAGED = NONE   COMMIT = NONE   PUSH = NONE
```

---

## 3. E4 file identities

Measured at E4E, after all E4D runtime work. The three implementation files are
byte-identical to their E4C pre-E4D binding.

| Path | Bytes | SHA256 |
|---|---|---|
| `backend/app/container.py` | 5524 | `69ee002a520f2b6eac3aac32c70e30277ac76d5a5f556cf496b38dfed02b42cf` |
| `backend/app/main.py` | 7777 | `10dbb25c99c7c3791a433b7b843efdb4126a97c8e64c55b780bfe561945ff81e` |
| `backend/tests/test_e4_pilot_transport_v0_1.py` | 8793 | `3ccd44c19b93d43a6f821a2184f3ed12b7ecb544653c3c8184678ed6ec4485b1` |

The two documentation files' own identities are recorded in the E4E final
report, since a document cannot contain its own hash.

---

## 4. External E4D evidence files

Produced outside the repository during E4D and **not** copied into it. These are
evidence artefacts, **not** canonical Product objects and **not** part of the
Product contract.

| Path | Bytes | SHA256 |
|---|---|---|
| `C:/Temp/e4d/lifecycle_evidence.json` | 7578 | `27626f8a1d374fae4c569c2628c329f1b0d869fb650c93c06efd3f23d101ae9d` |
| `C:/Temp/e4d/pilot_evidence.json` | 5483 | `2918e7452d836cddfac780736b492c536e43293d0cdd921391f76360e9bb5e77` |

**Correspondence to the final corrected E4D run — verified, not assumed.**
`pilot_evidence.json` was confirmed to carry all three corrected-run markers:
`governed_evidence_set.admitted_count == 5`, exactly one PROCEED dialogue
decision recorded for the PROCEED turn, and the per-turn CLARIFY decision
field. Superseded first-run capture values are **not** bound anywhere in this
document (see §12).

The two E4D runner scripts are supporting harness only. They are not bound as
durable pilot identity; no material claim in this document depends on their
exact bytes.

---

## 5. Synthetic pilot content

```
CONTENT PACK #1 = NOT ENTERED
The Works       = NOT ENTERED / NOT SELECTED BY E4
```

| Field | Value |
|---|---|
| `pack_id` / `pack_version` | `e4_synthetic_pilot_pack` / `1.0.0` |
| `contract_version` | `0.1` |
| `source_id` / `source_version` | `e4_pilot_alpha` / `1.0.0` |
| source bytes | 6000 |
| source SHA256 | `aff7fb1f9098ef89795e4b6467bc351c301433ad7b16617d9aad3b42395a05ca` |
| `pack_canonical_fingerprint` | `30c0a862e02524fb349ca5f198e2d6e1c84604aeb5076d46fbe72561148dac7e` |

The synthetic source was created in an OS temporary directory outside the
repository and was removed after verification. **Classification:** E4 SYNTHETIC
PILOT PACK — verification fixture / pilot content only.

**Content Engine:** contract `0.1`, version `0.1`, `chunk_chars` 1200,
`overlap` 200, **6 records**, document ids `e4_pilot_alpha::pall::c0` through
`::c5`, all unique. Content Engine itself unchanged.

---

## 6. Derived index lifecycle receipts

| Stage | Value |
|---|---|
| Expected derived index fingerprint | `e406986fbfbb4ccc21dbd9a47c3cebd745728b64d3c2d0b730ad9765a4915cc8` |
| CandidateMaterializationReceipt fingerprint | `44737caa003c842fe7db73c78dc65ec6b89a75ab8dbbd39007ab87bacfd86d08` |
| Measured state fingerprint | `09e26557e35c216f0ce549c26c2efe07fd02d482660cd03b4b03de9543ff0c33` |
| VerificationReceipt fingerprint | `cbd8b55454442a190a709bce5f4e6f9421388d3913c847bc587301562b52944f` |
| ActivationReceipt fingerprint | `a83c629dc5e5bfe52b8b35c46d8bf0b40ddfd9be282944a587fd5deec8d91845` |

```
Verification status = PASS
Verification scope  = STRUCTURAL_V0_1
expected record count = 6   written = 6   reported = 6   enumerated = 6
missing ids = []  unexpected ids = []  duplicates = []
evidence-fingerprint mismatches = []
bindings_match = True   schema_match = True
vector schema = dimension 256 / COSINE / unnamed vector
embedding_execution_binding = DECLARED_ONLY
```

**Activation:**

```
logical alias              = e4_pilot_active
active physical collection = e4_pilot_candidate
previous active collection = NONE
activation method          = ALIAS_BOOTSTRAP_CREATE
```

The physical collection was preserved (not deleted) so rollback stays truthful.

```
alias = RUNTIME ADDRESS ONLY
alias != canonical content identity
```

**Alias retrieval proof:** a `QdrantRetrieval` addressed at `e4_pilot_active`
returned 3 hits, all from the synthetic build, with provenance payload keys
(`ion_source_provenance`, `ion_canonical_provenance`, `evidence_fingerprint`)
intact across the round trip.

---

## 7. Qdrant — E4D observation

| Field | Value |
|---|---|
| container | `e4d-disposable-qdrant` |
| image tag | `qdrant/qdrant:latest` |
| image digest | `sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c` |
| host port | 6399 |
| persistent mounts | NONE |
| server semantic version | **1.18.2** |
| server commit | `44ad62f8cd69642be5afa6441612525e24a0d063` |

**Version classification: INDEPENDENTLY MEASURED VIA `GET /`.** The version is
**not** inferred from the `latest` tag; `latest` is an image tag and carries no
semantic version meaning.

```
PROJECT / LIVE QDRANT MUTATION = NONE
DISPOSABLE QDRANT CLEANUP      = PASS  (stopped, removed, host port released)
TEMP SYNTHETIC SOURCE CLEANUP  = PASS  (verified absent)
```

---

## 8. PROCEED — end-to-end proof

**Result: PASS.** HTTP 200, `kind = "answer"`, through the real E4C FastAPI
pilot transport.

| Observation | Value |
|---|---|
| session id | `9af70a644ee64d0cafb50196912f091f` |
| dialogue evaluations | 1 |
| dialogue decision | `PROCEED` / `NO_RULE_TRIGGERED` |
| `Core.ask` calls | 1 |
| retrieval calls | 1 |
| retrieval address | `e4_pilot_active` |
| retrieved document ids | `::c5`, `::c3`, `::c0`, `::c4`, `::c1` (all from the synthetic build) |
| governance outcome | `GOVERNANCE_COMPLETE` |
| governed candidates | 5 candidates / 5 governed |
| GovernedEvidenceSet | `ION_GOVERNED_EVIDENCE_SET_V0_1` / `0.1` — admitted 5, rejected 0, unknown 0 |
| ModelContextAssembly | `context_pack_id` `cp_21be2ce91f47e18e`, 5 evidence items |
| model executions | 1 |
| MIVE comparison | NONE / not applicable under SINGLE |
| TurnRecord count | 1 |
| TurnRecord closure | `COMPLETED` |
| TurnRecord `turn_id` | `e1c9fd83c0334b51abae1e64ae9f335f` |
| SessionTurnEntry count | 1 |
| turn ordinal | 1 |
| next ordinal | 1 → 2 (advanced exactly once) |
| session status after | ACTIVE |

**Operational metrics:** status `success`, 5 retrieved chunks, 5 context
documents, 5801 context characters, comparison latency `None` (no comparison
ran). Provider row: `gemini` / `gemini-2.5-pro`, 101 input tokens, 57 output
tokens, `usage_is_estimated: false`, `estimated_cost: null`, and consequently
`total_estimated_cost: null` — consistent with the pre-existing absence of a
pricing entry for this Gemini model, which is a known open defect recorded
elsewhere and is **not** an E4 finding.

---

## 9. Response-evidence subset proof

**Result: PASS.**

```
authorized ModelContext basis = {::c0, ::c1, ::c3, ::c4, ::c5}
rendered response evidence    = {::c0, ::c1}
subset relation               = PASS
```

The rendered evidence is a strict subset of the authorized basis the executed
engine itself received. No citation was resolved against any wider retrieved
candidate list.

---

## 10. CLARIFY — end-to-end proof

**Result: PASS.** HTTP 200, `kind = "clarify"`.

| Observation | Value |
|---|---|
| session id | `d4ee609f53854533ad73894bd6adfc41` |
| reason code | `QUESTION_HAS_NO_ANSWERABLE_CONTENT` |
| dialogue decision | `CLARIFY` / `QUESTION_HAS_NO_ANSWERABLE_CONTENT` |
| reserved ordinal reported | 1 |
| `Core.ask` delta | 0 |
| retrieval delta | 0 |
| governance delta | 0 |
| model execution delta | 0 |
| TurnRecord count | 0 |
| SessionTurnEntry count | 0 |
| next ordinal | unchanged (1 → 1) |
| active reservation after return | NONE |
| session status | ACTIVE |

No Core turn was fabricated, and no history was written to claim one occurred.

---

## 11. Session close proof

**Result: PASS.** `POST /pilot/sessions/{session_id}/close` returned HTTP 200
and delegated to the real `SessionController.close_session()`. Controller
status `CLOSED`, `ordered_turns` 0. No additional turn was fabricated.

---

## 12. Corrected-evidence record

Two defects existed in the E4D **evidence-capture harness** — never in ION, and
never in any repository file. Both were corrected and the pilot re-run; only
the corrected run is bound in this document.

1. `governed_evidence_set.admitted_count` was read from a guessed attribute
   name and reported `0`. The correct field is `GovernedEvidenceSet.admitted`;
   the corrected run records **admitted 5 / rejected 0 / unknown 0**.
2. The captured dialogue-decision list was stored by reference, so the PROCEED
   record aliased a later CLARIFY append and appeared to show two decisions.
   The corrected run records **exactly one** PROCEED decision for the PROCEED
   turn.

**Superseded value, recorded so it is never reintroduced.** An earlier E4E
instruction carried `turn_id = 7177d75707b44b5ba3861673954a75f4`. That value
originates from the **first, superseded** pilot run. The bound value is the
final corrected run's `turn_id`:

```
BOUND      turn_id = e1c9fd83c0334b51abae1e64ae9f335f
SUPERSEDED turn_id = 7177d75707b44b5ba3861673954a75f4   (first run — do not bind)
```

Session ids are per-run and likewise come from the corrected run only. The
`context_pack_id` `cp_21be2ce91f47e18e` is identical across both runs, which is
expected: it is deterministic from the content, not from the run.

---

## 13. Provider boundary qualification

```
EXECUTION PROFILE = STANDARD_GEMINI / 0.1 / SINGLE
DECLARED PROVIDER = gemini
DECLARED MODEL    = gemini-2.5-pro

AUTOMATED E4D ACTUAL EXTERNAL NETWORK PROVIDER = NONE
PROVIDER NETWORK BOUNDARY SUBSTITUTE           = tests.fakes.FakeBackend
SUBSTITUTION SCOPE = the GeminiBackend network/provider client ONLY
```

Real production components retained in the proven path: `SessionController`,
`AdaptiveDialogueEngine`, `Core` orchestration, `QdrantRetrieval`, Core Adapter
/ governance, `GovernedEvidenceSet`, `ModelContextAssembly`, `ModelGateway`,
renderer, `TurnRecord`, `SessionTurnEntry`, via the production `build_core` /
`build_session_controller` composition.

```
E4 VERIFIED INTEGRATED PILOT != LIVE EXTERNAL-GEMINI PROVIDER PROOF
```

---

## 14. Live Gemini qualification

```
LIVE GEMINI SMOKE = NOT EXECUTED / CREDENTIALS UNAVAILABLE
GEMINI_API_KEY    = ABSENT (presence-only check)
GOOGLE_API_KEY    = ABSENT (presence-only check)
SECRETS           = NOT READ / NOT PRINTED
PROVIDER-REPORTED IMMUTABLE MODEL REVISION = UNBOUND
```

No secret value, length, prefix, or suffix was read, printed, hashed, or
partially masked. No `.env` file was opened; reading one is denied outright by
the project permission model and is never an authorised step. `OPENAI_API_KEY`
was observed present in the ambient environment, but the authorised smoke was
Gemini-only under STANDARD_GEMINI / SINGLE, and no provider substitution was
made.

Per the accepted E4B/E4D contract, this qualification does **not** invalidate
the mandatory automated integrated E4D proof. It does bound what that proof
covers (§13).

---

## 15. Reservation observability qualification

E4D did **not** freeze the integrated runtime mid-flight to directly sample the
`ActiveTurnReservation` object. **No direct mid-flight reservation snapshot
occurred, and none is claimed.**

Direct E4D evidence covers: reserved-ordinal behaviour (CLARIFY reported
reserved ordinal 1 while `next_turn_ordinal` remained 1), release behaviour
(`active_turn` NONE after return on both paths), single ordinal commitment on
PROCEED (1 → 2), and no ordinal commitment on CLARIFY.

The reservation-before-dialogue law is independently closed and tested in the
existing `SessionController` / E1 contract and in the E4C transport proofs.

```
CLASSIFICATION = NON-BLOCKING OBSERVABILITY QUALIFICATION
```

---

## 16. Identity qualifications

**Core / application compatibility identity.** Bound as: repository
implementation identity (§2, §3) + existing `APP_VERSION = 0.1.0` + the
existing closed Core / Product contract ancestry.

**OBSERVED — no dedicated Core contract-version constant exists in code.** That
fact is stated rather than filled with an invented constant.

```
PRICING_AS_OF = runtime/product metadata only — NOT pilot compatibility identity
```

**Session runtime.** Documented v0.1, durable closed ancestry (TASK 22).
**OBSERVED — no code-exported Session contract-version constant.**

**Adaptive Dialogue.** Documented v0.1, durable closed E1 ancestry, frozen by
`docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md`.
**OBSERVED — no code-exported Adaptive Dialogue contract-version constant.**

No constant was invented for either. Where a version field does exist in code
it is bound verbatim: `TurnRecord` contract `ION_TURN_RECORD_V0_1` / `0.1`
(materializer `0.1`); `GovernedEvidenceSet` `ION_GOVERNED_EVIDENCE_SET_V0_1` /
`0.1`; Execution Profile `STANDARD_GEMINI` / `0.1` / `SINGLE`.

**No pilot framework.**

```
IntegratedPilotBinding production object = NONE
Pilot canonical fingerprint              = NONE
General pilot framework                  = NONE
Pilot persistence                        = NONE
```

E4 identity exists as a bounded closure binding across already-existing
identities and observed receipts. No new canonical pilot hash was created.

---

## 17. Test and regression record

```
E4C TARGETED TRANSPORT TESTS   = 7 PASS / 0 FAIL
E4C REQUIRED TRANSPORT PROOFS  = T01-T18 EXECUTED / PASS
E4D PROTECTED SUITES           = 336 PASS / 6 FAIL
```

**Exact qualification mapping for those 6 failures** — all six were measured to
fail with the same governance/provenance mechanism, and **none** was
demonstrated to be a CRLF byte-identity failure:

| Failures | Test | Mechanism | Qualification |
|---|---|---|---|
| 1 | `test_transport_api.py::test_post_ask_returns_complete_rendered_result_for_real_question` | HTTP 500 from `ContextPackError: Runtime evidence bridge rejected: CANONICAL_REJECTED:d1:…MISSING_PROVENANCE` | **Q4** |
| 5 | `test_transport_service.py` (5 tests) | identical `CANONICAL_REJECTED:d1:…MISSING_PROVENANCE` governance-fixture rejection | members of the pre-existing 33-failure baseline set |

All six arise from test fixtures whose candidates carry no provenance, so the
real governance gate rejects them. This is pre-existing and non-E4.

```
PREPARED-ENVIRONMENT BOUNDED REGRESSION = 1393 PASS / 34 FAIL / 1 SKIP
POST-E4D BOUNDED REGRESSION             = 1393 PASS / 34 FAIL / 1 SKIP
FAILURE-SET DIFF                        = IDENTICAL
NEW E4D REGRESSION                      = NOT SUPPORTED
```

**Historical E3 baseline, unchanged and not rewritten:**

```
1381 PASS / 33 FAIL / 7 SKIP
```

The difference between the historical baseline and the prepared-environment
figures is environmental, not code-attributable: enabling `fastapi` / `httpx`
un-masked 6 previously skipped tests (5 now pass, 1 now fails as Q4).

---

## 18. Q1 / Q2 / Q3 / Q4

**Q1 — PRE-EXISTING OVERLAY-DEPENDENT COLLECTION BLOCKER. UNREPAIRED.**
`tests/test_production_canonical_materialization_wiring_v0_1.py` cannot be
collected in this worktree (`ModuleNotFoundError:
app.modules.retrieval.source_provenance_manifest`). Normalized classification
as accepted under E3; excluded from the bounded regression run.

**Q2 — PRE-EXISTING CRLF / BYTE-IDENTITY QUALIFICATION**, historically
associated with the 33-failure baseline. **UNREPAIRED.**
**Precision note:** membership in the historical 33-failure baseline set does
**not** establish that a given failure's own mechanism is CRLF byte-identity.
Where a mechanism was actually measured (the 5 `test_transport_service.py`
failures in §17), it was a governance-fixture provenance rejection. No claim is
made here that every current failure is itself a CRLF failure.

**Q3 — `ION_REPO_ROOT` ENVIRONMENT REQUIREMENT.** Set explicitly for every test
run. **UNREPAIRED.**

**Q4 — PRE-EXISTING TRANSPORT/API GOVERNANCE-FIXTURE FAILURE.**
PREVIOUSLY SKIP-MASKED · UNMASKED BY E4C TEST-ENVIRONMENT ENABLEMENT ·
**PROVEN PRESENT ON PRE-E4C HEAD** (the same test fails identically when
`main.py` and `container.py` are restored to HEAD in an isolated copy) ·
NON-E4C · **UNREPAIRED.**

No repair of Q1, Q2, Q3, or Q4 was attempted or authorised.

---

## 19. E4 environment preparation

```
Python        = 3.13.14
pip           = 26.1.2   (not upgraded)
fastapi       = 0.141.1  (added to the local test execution environment)
httpx         = 0.28.1   (already present)
annotated_doc = 0.0.5    (transitive dependency of fastapi)

REPOSITORY DEPENDENCY FILES CHANGED = NONE
PACKAGE UPGRADES OF EXISTING DEPENDENCIES = NONE
```

Exactly two `dist-info` entries changed, confirming no incidental upgrades.
No `pyproject.toml`, requirements file, lockfile, `Dockerfile`, or
`docker-compose.yml` was modified.

**Transparency note — partial pre-install snapshot.** `python --version` was
captured before installation, but the Python executable path and the pip
version were captured **after**. Neither is altered by adding two packages, and
pip's own pre-install notice independently confirms it was 26.1.2 at install
time. **Full pre-install snapshot compliance is not claimed.**

**Classification:** TEST EXECUTION ENVIRONMENT PREPARATION.

---

## 20. Protected surfaces and response-evidence decision

E4 made no internal modification to: `SessionController` semantics, Session
models, `AdaptiveDialogueEngine` semantics, Adaptive Dialogue models,
`Core.ask()`, `RetrievalPort`, `QdrantRetrieval`, `GovernedEvidenceSet`,
`ModelContext`, `ModelGateway`, Execution Profile, `TurnRecord` schema, Content
Pack identity, Content Engine, Expected Derived Index identity, Derived Index
Lifecycle, renderer semantics, or `ResponseEvidenceProjection`.

```
render_single AUTHORIZED-BASIS PATH = ACCEPTED FOR E4
Task17 ResponseEvidenceProjection   = PRESERVED / UNWIRED / REUSABLE

E4-R01 = renderer inline duplicate-candidate-id behaviour differs from the
         Task17 fail-closed projector behaviour
E4-R01 CLASSIFICATION = NON-BLOCKING FOR THE BOUNDED E4 SYNTHETIC PILOT
E4-R01 ACTION         = NO E4 REPAIR
```

`renderer.py` and `response_evidence/projector.py` were not modified. The
synthetic pack's document ids are unique, so the differing branch was not
reached — a bounded non-encounter, not a proof of equivalence.

---

## 21. Final state

```
HEAD = a58c35a2b9d113f77877b2a86929443068bd2884

TRACKED MODIFIED (exactly two):
  backend/app/container.py
  backend/app/main.py

UNTRACKED NON-IGNORED (exactly three):
  backend/tests/test_e4_pilot_transport_v0_1.py
  docs/ION_E4_INTEGRATED_GOVERNED_PILOT_CONTRACT_v1.md
  docs/ION_E4_INTEGRATED_GOVERNED_PILOT_CLOSURE_2026-09-03.md

STAGED = NONE
COMMIT = NONE
PUSH   = NONE

PROJECT / LIVE QDRANT MUTATION = NONE
DISPOSABLE QDRANT              = CLEANED UP
CONTENT ACTIVATION (product)   = NONE
CONTENT PACK #1                = NOT ENTERED
```

```
E4 = IMPLEMENTED / VERIFIED — READY FOR EXACT COMMIT AUTHORIZATION
E4 = NOT YET CLOSED / DURABLE
```
