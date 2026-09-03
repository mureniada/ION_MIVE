# ION E4 — Integrated Governed Pilot Contract v1

**Type:** Bounded contract document. It states what the E4 integrated governed
pilot IS and what it is NOT. It authorises no deployment, no commit, no content
selection, and no scope expansion.
**Status at time of writing:** E4 IMPLEMENTED / VERIFIED. **Not** yet
CLOSED / DURABLE — durable closure requires a later, separately authorised
exact commit (E4F).

## How to read this document

Every substantive line is one of:

| Marker | Meaning |
|---|---|
| **BOUND** | A contract term fixed by E4. Changing it requires a new authorised phase. |
| **OBSERVED** | A fact measured during E4D, with the measurement named. |
| **QUALIFIED** | A deliberately limited claim. The limit is part of the claim. |
| **NOT** | An explicit non-goal or prohibition. Absence is stated, never implied. |

A **QUALIFIED** line must never be quoted with its qualification removed.

---

## 1. Pilot topology

**BOUND — dedicated pilot session transport.** E4 adds exactly three routes:

```
POST /pilot/sessions
POST /pilot/sessions/{session_id}/turn
POST /pilot/sessions/{session_id}/close
```

**BOUND — legacy transport is unchanged.** `POST /ask` and `GET /ask/stream`
keep their existing paths, request contracts, response contracts and behaviour.
Neither is routed through `SessionController`. The pilot transport is
**additive only**.

**BOUND — composition.**

```
ONE PROCESS -> ONE SHARED CORE -> ONE SessionController -> MANY IN-MEMORY SESSIONS
```

The composition seam is `container.build_session_controller(core)`, which wraps
the one already-constructed `Core` instance. No second `Core` and no second
retrieval stack is built for the pilot path.

**NOT part of E4**, with no field, table, route or module carrying them:

- persistent session storage
- conversation memory
- a `DialogueState` framework
- persistent personalization
- domain routing
- multi-pack routing
- a pilot framework, service layer, repository, manager, registry or state machine

---

## 2. Integrated execution path

**BOUND** — the governed path a PROCEED turn takes, end to end:

```
USER / PILOT TRANSPORT
      -> SessionController
      -> Session admission
      -> ActiveTurnReservation
      -> AdaptiveDialogueEngine
      -> CLARIFY | PROCEED

PROCEED
      -> Core.ask
      -> RetrievalPort
      -> QdrantRetrieval
      -> active logical alias
      -> governance / Core Adapter
      -> GovernedEvidenceSet
      -> ModelContextAssembly
      -> ModelGateway
      -> STANDARD_GEMINI / SINGLE
      -> renderer
      -> TurnRecord
      -> SessionTurnEntry
```

**BOUND — all pre-existing authority laws are preserved unchanged.** E4
introduced no new authority, reordered no stage, and relaxed no invariant. In
particular: the Controller sits strictly above `Core.ask()`; the dialogue
evaluation happens strictly after admission and strictly before `Core.ask()`;
governance decides admission; only admitted governed evidence reaches model
input; and a single configured engine under SINGLE yields no MIVE comparison.

**BOUND — no pilot route reaches `Core.ask()` directly.** The turn route's only
path to a turn is `SessionController.run_turn`.

---

## 3. CLARIFY

**BOUND — CLARIFY is a distinct type at the public boundary, never a
fabricated result.**

```
CLARIFY != AskResult
CLARIFY != failure
CLARIFY != TurnRecord
```

**BOUND — a CLARIFY interaction causes exactly zero of each of the following:**

| Effect | Count |
|---|---|
| `Core.ask` calls | 0 |
| retrieval calls | 0 |
| governance calls | 0 |
| model executions | 0 |
| `TurnRecord` | 0 |
| `SessionTurnEntry` | 0 |

and leaves the ordinal unchanged, the reservation released, and the session
**ACTIVE**.

**BOUND — E4 introduced no new dialogue semantics.** The single deterministic
CLARIFY rule and its reason code are the pre-existing E1 rule, unchanged. The
transport reports the decision; it does not make one.

**BOUND — transport representation.** The turn route returns the smallest
explicit tagged shape: `kind = "answer"` (carrying the existing rendered
result) or `kind = "clarify"` (carrying `session_id`, `turn_ordinal`,
`reason_code`). No new dialogue vocabulary is introduced by the transport.

---

## 4. Content strategy

**BOUND — E4 content is a synthetic, closed-API pilot pack.**

```
E4 CONTENT = SYNTHETIC CLOSED-API PILOT PACK
```

**NOT** Content Pack #1. **NOT** The Works. **NOT** domain or client content.

**BOUND — exact synthetic identity:**

| Field | Value |
|---|---|
| `pack_id` | `e4_synthetic_pilot_pack` |
| `pack_version` | `1.0.0` |
| `contract_version` | `0.1` |
| `source_id` | `e4_pilot_alpha` |
| `source_version` | `1.0.0` |
| source SHA256 | `aff7fb1f9098ef89795e4b6467bc351c301433ad7b16617d9aad3b42395a05ca` |
| `pack_canonical_fingerprint` | `30c0a862e02524fb349ca5f198e2d6e1c84604aeb5076d46fbe72561148dac7e` |

**BOUND — no durable fingerprint in this document or the closure document is
ever abbreviated.**

**BOUND — the synthetic pack is a verification fixture.** It carries no
business meaning, states no domain claim, and confers no content authority.
Selecting real content is a separate, later product/content stage.

---

## 5. E2 / E3 integration

**BOUND — the pilot consumes the closed E2/E3 APIs and modifies none of them.**

```
SYNTHETIC CONTENT PACK (E2.1)
      -> CONTENT ENGINE (E2.2)
      -> EXPECTED DERIVED INDEX (E2.3)
      -> CANDIDATE MATERIALIZATION (E3)
      -> MEASURE (E3, read-only)
      -> VERIFY (E3, pure)
      -> ACTIVATE (E3, one alias cutover)
      -> QdrantRetrieval via the active logical alias
```

**BOUND — Content Engine parameters and output for this pilot:**

| Field | Value |
|---|---|
| content engine contract | `0.1` |
| content engine version | `0.1` |
| `chunk_chars` | `1200` |
| `overlap` | `200` |
| record count | `6` |

**BOUND — the six document ids, all unique:**

```
e4_pilot_alpha::pall::c0
e4_pilot_alpha::pall::c1
e4_pilot_alpha::pall::c2
e4_pilot_alpha::pall::c3
e4_pilot_alpha::pall::c4
e4_pilot_alpha::pall::c5
```

**BOUND — the Content Engine itself is UNCHANGED by E4.**

**BOUND — expected derived index:**

| Field | Value |
|---|---|
| `derived_index_fingerprint` | `e406986fbfbb4ccc21dbd9a47c3cebd745728b64d3c2d0b730ad9765a4915cc8` |
| record count | `6` |

**BOUND — embedding profile (E2.3 closed contract):**

| Field | Value |
|---|---|
| `backend` | `fake` (the closed-contract `BACKEND_FAKE` representation) |
| `dimension` | `256` |
| `normalization_profile` | `L2_NORMALIZED_BY_ADAPTER` |
| `model_name` | `None` — the closed-contract not-applicable representation |
| `model_revision` | `None` — the closed-contract not-applicable representation |
| `implementation_revision` | `e4d-declared-test-scope-2026-09-03` |

**QUALIFIED — the embedding profile is a DECLARED TEST EXECUTION IDENTITY.**
It is **NOT** an independently measured implementation attestation. No claim is
made that a particular embedding implementation build was loaded or executed;
`embedding_execution_binding` is `DECLARED_ONLY` throughout, exactly as the E3
contract states at this version.

---

## 6. Alias and identity rules

**BOUND:**

```
logical alias = e4_pilot_active          -> RUNTIME ADDRESS ONLY
active physical collection = e4_pilot_candidate
```

**BOUND — the alias is not a content identity.**

```
alias != canonical content identity
EXPECTED IDENTITY != MEASURED STORE STATE
VERIFIED != ACTIVE
BUILD != MEASURE != VERIFY != ACTIVATE
```

**BOUND — E4 minted no new canonical fingerprint.** Every identity above is one
an already-closed module computed. E4 binds existing identities together; it
does not compute a new one.

**BOUND — no `IntegratedPilotBinding` production object exists.** There is no
pilot canonical fingerprint, no pilot framework, and no pilot persistence. E4
identity exists as a bounded closure binding across already-existing identities
and observed receipts, recorded in the closure document.

---

## 7. Provider boundary — load-bearing distinction

**BOUND — the execution profile actually composed and executed:**

```
EXECUTION PROFILE = STANDARD_GEMINI / 0.1 / SINGLE
DECLARED PROVIDER = gemini
DECLARED MODEL    = gemini-2.5-pro
```

**BOUND — in the automated E4D proof, the actual external network provider was
NONE.**

```
AUTOMATED E4D ACTUAL EXTERNAL NETWORK PROVIDER = NONE
PROVIDER NETWORK BOUNDARY SUBSTITUTE           = tests.fakes.FakeBackend
SUBSTITUTION SCOPE = the GeminiBackend network/provider client ONLY
```

**BOUND — every other component in the path was the real production one:**
`SessionController`, `AdaptiveDialogueEngine`, `Core` orchestration,
`QdrantRetrieval`, Core Adapter / governance, `GovernedEvidenceSet`,
`ModelContextAssembly`, `ModelGateway`, renderer, `TurnRecord`,
`SessionTurnEntry`. The production `build_core` / `build_session_controller`
composition was used. All call counting used delegating spies — observation,
never replacement.

**NOT permitted, anywhere, in any document or summary derived from E4:**

- "REAL GEMINI E4D PASS"
- "gemini-2.5-pro was actually executed by Google"

**BOUND — the separating statement:**

```
E4 VERIFIED INTEGRATED PILOT != LIVE EXTERNAL-GEMINI PROVIDER PROOF
```

**QUALIFIED — provider-reported immutable model revision is UNBOUND.** No
provider-reported model revision was obtained, because no provider network call
was made. `gemini-2.5-pro` is the **declared/requested** model identity only.

---

## 8. Response-evidence decision

**BOUND — the current `render_single` authorized-basis path is ACCEPTED for
E4.** The renderer resolves the executed report's citations only against
`ModelContextAssembly.evidence` — the exact evidence the executed engine itself
received — and excludes any cited id absent from that basis.

**BOUND — Task17 `ResponseEvidenceProjection` remains PRESERVED / UNWIRED /
REUSABLE.** E4 wires no projector.

**QUALIFIED — E4-R01.** The renderer's inline duplicate-candidate-id behaviour
differs from the Task17 projector's fail-closed behaviour.

```
E4-R01 CLASSIFICATION = NON-BLOCKING FOR THE BOUNDED E4 SYNTHETIC PILOT
E4-R01 ACTION         = NO E4 REPAIR
```

The qualification holds because the synthetic pack's document ids are unique,
so the differing branch is not reached by this pilot. **This is a bounded
non-encounter, not a proof of equivalence.**

**BOUND — `renderer.py` and `response_evidence/projector.py` are NOT modified
by E4.**

---

## 9. Protected surfaces — unchanged by E4

E4 made **no** internal modification to any of:

`SessionController` semantics · Session models · `AdaptiveDialogueEngine`
semantics · Adaptive Dialogue models · `Core.ask()` · `RetrievalPort` ·
`QdrantRetrieval` · `GovernedEvidenceSet` · `ModelContext` · `ModelGateway` ·
Execution Profile · `TurnRecord` schema · Content Pack identity · Content
Engine · Expected Derived Index identity · Derived Index Lifecycle · renderer
semantics · `ResponseEvidenceProjection`.

**BOUND — the entire E4 production surface is two files:**

```
backend/app/container.py   (one composition seam added)
backend/app/main.py        (three additive routes + one shared-controller accessor)
```

---

## 10. Non-goals

E4 does **NOT**:

- enter Content Pack #1, The Works, or any domain/client content;
- select, activate, or endorse any real content;
- prove a live external Gemini (or any external provider) execution;
- establish an embedding implementation attestation;
- introduce persistence of any kind;
- change legacy `/ask` or `/ask/stream`;
- constitute a commit, push, tag, release, or deployment;
- repair Q1, Q2, Q3, Q4, or E4-R01.

**BOUND — Content Pack #1 boundary.**

```
CONTENT PACK #1 = NOT ENTERED
The Works       = NOT ENTERED / NOT SELECTED BY E4
```

After durable E4 closure, Content Pack #1 becomes the next separate
product/content stage, under its own authorisation.
