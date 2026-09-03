# ION E1 — Minimal Adaptive Dialogue Runtime — Closure Receipt

**Date:** 2026-09-03
**Type:** Closure receipt. Evidence record bound to a qualified baseline.
**Companion:** `docs/ION_E1_ADAPTIVE_DIALOGUE_RUNTIME_INTEGRATION_ADDENDUM_v1.md`

---

## 1. Baseline binding

```
QUALIFIED BASELINE = 4d5a5000da92cc52cf22115b659d5a2138c6512e
HEAD AT CLOSURE    = 4d5a5000da92cc52cf22115b659d5a2138c6512e
HEAD MODE          = DETACHED
BASELINE MATCH     = YES
PRE-E1 TRACKED WORKTREE DIFF = NONE
PRE-E1 STAGED DIFF           = NONE
```

## 2. Gate state

```
E1.1 = CLOSED / APPROVED
E1.2 = CLOSED / APPROVED
E1.3 = EXECUTED
E1.4 = EXECUTED
E1.5 = VERIFIED
```

---

## 3. Production files changed (5)

```
backend/app/modules/adaptive_dialogue/__init__.py
backend/app/modules/adaptive_dialogue/engine.py
backend/app/modules/adaptive_dialogue/models.py
backend/app/modules/session/__init__.py
backend/app/modules/session/controller.py
```

`backend/app/modules/session/models.py` was **not** modified.

## 4. Test files changed (4)

```
backend/tests/test_adaptive_dialogue_engine_v0_1.py
backend/tests/test_adaptive_dialogue_models_v0_1.py
backend/tests/test_session_controller_v0_1.py
backend/tests/test_session_models_v0_1.py
```

## 5. Final diff summary

```
 backend/app/modules/adaptive_dialogue/__init__.py  |   7 +-
 backend/app/modules/adaptive_dialogue/engine.py    |  58 ++-
 backend/app/modules/adaptive_dialogue/models.py    |  37 +-
 backend/app/modules/session/__init__.py            |   2 +
 backend/app/modules/session/controller.py          | 102 +++++-
 backend/tests/test_adaptive_dialogue_engine_v0_1.py|  63 +++-
 backend/tests/test_adaptive_dialogue_models_v0_1.py|   7 +-
 backend/tests/test_session_controller_v0_1.py      | 389 ++++++++++++++++++++-
 backend/tests/test_session_models_v0_1.py          |   3 +
 9 files changed, 615 insertions(+), 53 deletions(-)
```

Plus the two durable artifacts materialized under E1.6 (this file and the
addendum), which are new untracked documentation files.

---

## 6. The deterministic CLARIFY rule and reason code

```
RULE        = the question contains no alphanumeric character
PREDICATE   = not any(character.isalnum() for character in turn_input.question)
TRUE        -> CLARIFY / QUESTION_HAS_NO_ANSWERABLE_CONTENT
FALSE       -> PROCEED / NO_RULE_TRIGGERED
REASON CODE = QUESTION_HAS_NO_ANSWERABLE_CONTENT
POSITIVE    = "???"       -> CLARIFY
NEGATIVE    = "Question"  -> PROCEED
```

Exactly one CLARIFY rule is reachable. `DialogueReasonCode` declares exactly two
members.

## 7. Observed runtime behavior

```
ordinal before CLARIFY      = 1
CLARIFY outcome type        = SessionClarificationOutcome
reason_code                 = QUESTION_HAS_NO_ANSWERABLE_CONTENT
Core.ask() on CLARIFY       = 0
Core turn_id created        = NO
TurnRecord created          = NO
SessionTurnEntry created    = NO
ordinal after CLARIFY       = 1        (RESERVED, not committed)
reservation released        = YES
session status after CLARIFY= ACTIVE
--- next interaction ---
result type                 = AskResult
Core.ask() total            = 1
ordinals committed          = [1]      (the CLARIFY-reserved ordinal reused)
next_turn_ordinal           = 2
```

---

## 8. Targeted E1 tests

```
COMMAND =
python -m pytest tests/test_session_controller_v0_1.py \
  tests/test_adaptive_dialogue_engine_v0_1.py \
  tests/test_adaptive_dialogue_models_v0_1.py \
  tests/test_session_models_v0_1.py -q
  (run from backend/)

RESULT = 116 passed, 0 failed
```

## 9. Bounded regression

```
COMMAND =
python -m pytest tests/test_session_controller_v0_1.py \
  tests/test_session_models_v0_1.py \
  tests/test_adaptive_dialogue_engine_v0_1.py \
  tests/test_adaptive_dialogue_models_v0_1.py \
  tests/test_orchestrator_turn_record_v0_1.py \
  tests/test_orchestrator_capture_seam_v0_1.py \
  tests/test_execution_profile_v0_1.py \
  tests/test_core_ask_mocked.py \
  tests/test_import_safety.py -q
  (run from backend/)

RESULT = 211 passed, 3 failed
```

### 9.1 The three qualified non-E1 failures

```
tests/test_core_ask_mocked.py::test_full_pipeline_success_with_mocked_provider
tests/test_core_ask_mocked.py::test_progress_events_are_emitted_in_order
tests/test_core_ask_mocked.py::test_the_sole_provider_failure_is_not_a_success
```

**Cause:** `backend/app/modules/runtime_evidence_bridge/bridge.py` (tracked,
untouched by E1) rejects that module's in-memory fixtures with
`CANONICAL_REJECTED: ... UNPROVEN_CHECKSUM_SEMANTICS | UNRESOLVED_FINGERPRINT_PROFILE |
MISSING_PROVENANCE | MISSING_PROVENANCE_ORIGIN | MISSING_PROVENANCE_PRODUCER |
MISSING_PROVENANCE_CREATED_AT`.

**Proven non-attributable to E1**, not merely asserted: no E1-modified module
appears anywhere in that test module's import closure. Verified by importing
`tests.test_core_ask_mocked` and inspecting `sys.modules` for any
`adaptive_dialogue` or `modules.session` entry — result: NONE.

**Not repaired.** Out of the authorized E1 surface. Carried forward as a
pre-existing condition requiring its own operator decision.

```
NEW E1 SEMANTIC REGRESSION = NOT SUPPORTED
NEW E1 WIRING REGRESSION   = NOT SUPPORTED
NEW FAILURES               = NONE
```

---

## 10. Protected surfaces preserved

```
TurnRecord schema                UNCHANGED
TurnClosureState                 UNCHANGED
SessionTurnEntry schema          UNCHANGED
Session schema                   UNCHANGED
SessionStatus semantics          UNCHANGED
ordinal invariant                UNCHANGED
Core.ask semantics               UNCHANGED
Content Pack / Content Engine / Pack Factory   UNCHANGED
RetrievalPort / Qdrant           UNCHANGED
GovernedEvidenceSet              UNCHANGED
ModelContext / ModelGateway      UNCHANGED
Execution Profile                UNCHANGED

Dialogue retrieval authority         NOT GRANTED
Dialogue evidence-admission authority NOT GRANTED
Dialogue governance authority        NOT GRANTED
Dialogue model-execution authority   NOT GRANTED
persistent DialogueState             NOT INTRODUCED
persistent clarification history     NOT INTRODUCED
WAITING_FOR_USER persistence         NOT INTRODUCED
DialogueProfile / memory / routing   NOT INTRODUCED
DIRECT_RESPONSE / DEEPEN / DUAL / VERIFY   NOT INTRODUCED

PROTECTED SURFACE MUTATION = NONE
AUTHORITY BOUNDARIES       = PRESERVED
```

---

## 11. Hash binding

### 11.1 E1-changed production files (SHA256)

```
E0F7F363644F9F3C5F8C70BCABC9F2312F1995D55B53CF8BE6E6B30241C77396  backend/app/modules/adaptive_dialogue/__init__.py
A85CBEF7B7CF161EB65E39DDBFB3404D232B247B968DC44CB770582686DCD563  backend/app/modules/adaptive_dialogue/engine.py
D4DB65EF7A0688AD0A73082413F783A3C9B45784555B517ACD2B856D184C0AA5  backend/app/modules/adaptive_dialogue/models.py
5167C637E66CD2FC00B4FD8309BD86033E4C21E396A8B94109D914065797FF5D  backend/app/modules/session/__init__.py
56B188CD36CAF54A68110F6782963F76D2533CBC307D5406EDB87381ED890CCD  backend/app/modules/session/controller.py
```

### 11.2 E1-changed test files (SHA256)

```
5901CC10021F18DC64E0451F37EE7CDB7503BA1DC9B6DF24F8D2D2082B3E5CCD  backend/tests/test_adaptive_dialogue_engine_v0_1.py
197C947CACD05AB48E40D3ECC1B92B6B810E63172ACB858809B0EE45082B90A6  backend/tests/test_adaptive_dialogue_models_v0_1.py
5910662BECB0AB3ADDD4F3221CC92241FA3F022B64D8AF09131C35CF35BA492B  backend/tests/test_session_controller_v0_1.py
A8ED3B9C200D800ED252B34DAB8FA0A130050721B4781BEE78EB03098BBA4C13  backend/tests/test_session_models_v0_1.py
```

### 11.3 E1 durable artifacts (SHA256)

Recorded in the E1.6 execution report. The addendum's digest is stable at
materialization time; this receipt cannot state its own digest inside itself.

```
docs/ION_E1_ADAPTIVE_DIALOGUE_RUNTIME_INTEGRATION_ADDENDUM_v1.md
docs/ION_E1_MINIMAL_ADAPTIVE_DIALOGUE_RUNTIME_CLOSURE_2026-09-03.md
```

### 11.4 Pre-existing overlay — PRE-EXISTING / NON-E1 / UNCHANGED

Re-verified byte-identical to their pre-Claude identities. **Not staged, not
modified, not attributed to E1.**

```
BCE938EBC881E50E49F954BED79F2564A94EE16124CF5E174E820F8D757DCDD6  backend/app/modules/admission/receipts.py
4CC8D1EBADB1C33EB0145C7C2006DE6DB0442D771477A13E646BB9EA9FC3C76C  backend/app/modules/retrieval/source_provenance_manifest.py
0C1A9486CADC5C9DC0D74B9EFAA38F00DB2644402F2E42F2BEC4BB5068FDF893  backend/t4/contract/STATUS.md
F097E2D5EF1C3585E06D0E133B17579E8653D4CDDCD9A8692C1FD91D9CC31F2A  schemas/ion_evidence_record_v0.1.schema.json
```

---

## 12. Contract-amendment status — SATISFIED

```
TASK23 HISTORICAL CONTRACT                   = PRESERVED / NOT REWRITTEN
E1 RUNTIME INTEGRATION ADDENDUM              = AUTHORITATIVE POST-TASK23 AMENDMENT
TASK23 CONTRACT-AMENDMENT REQUIREMENT FOR E1 = SATISFIED
```

`docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md` §7 anticipates that a
deterministic CLARIFY rule arrives "under a contract amendment." By operator
decision (E1.6A), that requirement is satisfied by
`docs/ION_E1_ADAPTIVE_DIALOGUE_RUNTIME_INTEGRATION_ADDENDUM_v1.md`, which is
recognized as the authoritative post-Task 23 amendment for the E1 runtime
integration.

The relationship is amendment-by-addendum, and is unambiguous in both
directions:

- the **historical contract is preserved, unedited**, as evidence of the pre-E1
  pure / deterministic / stateless / unwired state — including its §7 "no rule
  authorized" statement and its §13 protected list naming
  `backend/app/modules/session/*`, both of which describe the pre-E1 state and
  the scope of Task 23 itself;
- the **addendum carries the amending force** for everything E1 changed: the
  session-layer pre-Core gate, the one deterministic CLARIFY rule, its new
  reason code, and the Session-level clarification outcome.

**No contract-amendment debt is carried forward.** Any further change — a
second CLARIFY rule, a widening of the existing one, or any new dialogue
authority — falls outside this amendment and requires its own separate
authorization.

## 13. Carried-forward qualification

One item is outstanding. It was not resolved by E1, and is not claimed to be.

1. **Three pre-existing `test_core_ask_mocked.py` failures** (§9.1), proven
   non-attributable to E1 and deliberately not repaired. They require their own
   operator decision as to whether they become a tracked issue.

---

## 14. Final state

```
REPOSITORY MOVEMENT = NONE
COMMIT              = NONE
PUSH                = NONE
BRANCH CREATED      = NONE
HEAD MOVED          = NO
STAGED FILES        = 0
STASHES             = 0
E2                  = BLOCKED / NOT STARTED

E1 = READY FOR DURABLE CLOSURE / COMMIT AUTHORIZATION
```

Commit authorization is a separate, explicit operator decision. It has not been
taken, and nothing in this receipt constitutes it.
