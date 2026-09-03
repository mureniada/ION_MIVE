# ION E1 — Adaptive Dialogue Runtime Integration Addendum — v1

**Date:** 2026-09-03
**Type:** Addendum. The authoritative post-Task 23 contract amendment for the
E1 runtime integration, and the record of the authorized transition it makes.
**Qualified baseline:** `4d5a5000da92cc52cf22115b659d5a2138c6512e`
**Authority:** E1 operator exception (bounded), E1.6 durability materialization
authorization, E1.6A durability reconciliation.

---

## 0. What this document is, and what it is not

This addendum records the authorized transition of the Adaptive Dialogue
Decision Engine from an UNWIRED decision instrument to a WIRED, session-layer
pre-Core gate.

**It does not rewrite `docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md`.** That
contract remains, deliberately and in full, the historical evidence of the
pre-E1 state: pure, deterministic, stateless, unwired, and carrying no
authorized CLARIFY rule. Nothing in this addendum edits, corrects, supersedes
in place, or reinterprets a single line of it. Read together, the two documents
state a before and an after — not a contradiction, and not a correction.

Two consequences of that choice are stated here rather than left implicit:

- **The Task 23 contract is now historically accurate but not currently
  descriptive.** Its §7 ("no CLARIFY rule is authorized") and its §13 protected
  list (which names `backend/app/modules/session/*`) describe the state before
  E1 and the scope of Task 23 itself. E1's separate operator authority is what
  permits the change this addendum records.
- **This document IS that contract amendment.** §7 of the Task 23 contract
  anticipates that a deterministic CLARIFY rule arrives "under a contract
  amendment." By operator decision (E1.6A), this addendum is recognized as the
  authoritative post-Task 23 amendment for the E1 runtime integration:

```
TASK23 HISTORICAL CONTRACT                   = PRESERVED / NOT REWRITTEN
E1 RUNTIME INTEGRATION ADDENDUM              = AUTHORITATIVE POST-TASK23 AMENDMENT
TASK23 CONTRACT-AMENDMENT REQUIREMENT FOR E1 = SATISFIED
```

  The amendment is therefore satisfied by amendment-by-addendum: the historical
  contract is preserved intact as evidence of the pre-E1 state, and this
  document carries the amending force for everything E1 changed. No
  contract-amendment debt is carried forward. Any FURTHER change — a second
  CLARIFY rule, a widening of the existing one, or any new dialogue authority —
  is outside this amendment and requires its own separate authorization.

---

## 1. Task 23 historical state

```
TASK23 HISTORICAL STATE =
PURE / DETERMINISTIC / STATELESS / UNWIRED
```

As frozen by `docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md`:

- `AdaptiveDialogueEngine.evaluate()` accepted one `DialogueTurnInput` and
  returned one `DialogueDecision`, and did nothing else.
- It returned `PROCEED` / `NO_RULE_TRIGGERED` for every valid input,
  unconditionally.
- `CLARIFY` was vocabulary-valid but **structurally unreachable**: the only
  declared reason code was `NO_RULE_TRIGGERED`, and `DialogueDecision`'s pairing
  invariant forbids `CLARIFY` paired with it.
- Nothing in the repository imported the package.

---

## 2. E1 selected architecture

```
E1 SELECTED ARCHITECTURE =
SESSION-LAYER PRE-CORE DIALOGUE GATE
```

The engine is consulted by the Session layer, above Core, before any turn
begins. It was not placed inside Core, inside retrieval, inside the Model
Gateway, or in transport.

### Runtime topology

```
SessionController.run_turn(...)
        ↓
Session admission
   (unknown-session refusal, CLOSED refusal, concurrency refusal)
        ↓
ActiveTurnReservation
   (Controller-owned reservation_id; ordinal RESERVED, not committed)
        ↓
AdaptiveDialogueEngine.evaluate(DialogueTurnInput(question=...))
        ↓
CLARIFY | PROCEED
```

Evaluation happens **exactly once per eligible interaction**. An interaction
refused by admission never reaches the engine at all — admission is strictly
upstream of dialogue.

The dependency is strictly one-way. `session.controller` imports
`adaptive_dialogue`; nothing in `adaptive_dialogue` imports, names, or can
reach the session, core, turn_record, retrieval, governance, model, provider,
renderer, or transport layers.

### PROCEED

```
PROCEED =
existing Core.ask() path, unchanged
```

Exactly one `Core.ask()`, through the frozen `on_turn_record` capture seam
(TASK 22.3B1), with the same preservation rules, the same
`TurnRecord` → `SessionTurnEntry` behavior, and the same ordinal advancement as
before E1. The governed path was not redesigned, re-ordered, or re-entered.

### CLARIFY

```
CLARIFY =
zero Core.ask()
zero Core turn_id
zero TurnRecord
zero SessionTurnEntry
zero ordinal commitment
reservation released
Session remains ACTIVE
explicit Session-level clarification outcome
```

The reserved ordinal is released **without being committed**, and the very next
eligible interaction takes that same ordinal. No history is written, and none
is fabricated to claim a turn occurred.

---

## 3. Boundary laws recorded

```
DIALOGUE DECISION              != EVIDENCE
PROCEED                        != AUTHORIZATION TO RETRIEVE
PROCEED                        != AUTHORIZATION TO ADMIT EVIDENCE
CLARIFY                        != TURN CLOSURE
ACTIVE TURN RESERVATION        != CORE TURN START
ORDINAL RESERVED               != ORDINAL COMMITTED
SESSION HISTORY                != DIALOGUE MEMORY
```

`PROCEED` states only that the dialogue layer raises no clarification
objection to handing the request onward. It authorizes nothing downstream: it
does not retrieve, does not admit evidence, does not invoke a provider, and
does not answer.

The engine **decides only**. Every session-level consequence of a decision —
releasing the reservation, withholding the ordinal, returning an outcome — is
performed by `SessionController`, not by the engine. The engine is handed a
`DialogueTurnInput` and nothing else: no session identity, no ordinal, no
history, no retrieval, no evidence, no governance, no model or provider handle,
no renderer, and no persistence.

**Structural absence preserved.** No `DialogueState`, no `DialogueProfile`, no
clarification history, no `WAITING_FOR_USER` persistence, no memory, and no
personalization was introduced. `DialogueTurnInput` still carries exactly one
field.

---

## 4. The one E1 deterministic rule, exactly as implemented

```
RULE        = the question contains no alphanumeric character
PREDICATE   = not any(character.isalnum() for character in turn_input.question)
TRUE        -> CLARIFY / QUESTION_HAS_NO_ANSWERABLE_CONTENT
FALSE       -> PROCEED / NO_RULE_TRIGGERED
REASON CODE = QUESTION_HAS_NO_ANSWERABLE_CONTENT  (new, stable)
POSITIVE    = "???"        -> CLARIFY
NEGATIVE    = "Question"   -> PROCEED
```

The rule is **structural, not interpretive**. It observes only whether the
question string contains any alphanumeric character. It is deliberately not a
semantic-ambiguity threshold, not a length rule, not a question-mark rule, not
a pronoun rule, not a keyword rule, and not domain routing. It never
lowercases, tokenizes, stems, parses, or otherwise interprets the question, and
it never mutates its input.

`DialogueReasonCode` now declares exactly two members. The pairing invariant is
unchanged and still enforced: a `CLARIFY` decision must always name the rule
that actually fired, so it can never be expressed with `NO_RULE_TRIGGERED`.

Widening this rule, or adding a second one, requires its own separate
authorization and its own reason code.

---

## 5. Session-level outcome boundary

`run_turn()` returns `AskResult | SessionClarificationOutcome`. The two
outcomes are distinguishable **by type** at the public boundary — never by a
flag on a fabricated result, and never by an exception.

`SessionClarificationOutcome` is a frozen dataclass with exactly three fields:
`session_id`, `turn_ordinal` (reserved, uncommitted), and `reason_code`. It is
deliberately not an `AskResult`, not an exception, not a `TurnRecord`, and not
a `SessionTurnEntry`. It carries no clarification text, no prompt, no
confidence, no score, no evidence, no turn id, and no minted identifier: it
states that a turn did NOT run, and why, and nothing more.

Clarification text generation remains DEFERRED in full, exactly as the Task 23
contract §8 states.

---

## 6. Surfaces explicitly NOT changed

```
TurnRecord schema              UNCHANGED
TurnClosureState               UNCHANGED
SessionTurnEntry schema        UNCHANGED
Session schema                 UNCHANGED
SessionStatus semantics        UNCHANGED
Core.ask semantics             UNCHANGED
backend/app/modules/session/models.py   NOT MODIFIED
Content Pack / Content Engine / Pack Factory   UNCHANGED
RetrievalPort / Qdrant         UNCHANGED
GovernedEvidenceSet            UNCHANGED
ModelContext / ModelGateway    UNCHANGED
Execution Profile              UNCHANGED
```

---

## 7. Provenance

Authorized under the bounded E1 operator exception to the automation-bootstrap
application-code freeze recorded in `CLAUDE.md`, and materialized under the E1.6
durability authorization. Baseline `4d5a5000da92cc52cf22115b659d5a2138c6512e`,
HEAD unmoved, no commit, no push, no repository movement.

The corresponding closure receipt is
`docs/ION_E1_MINIMAL_ADAPTIVE_DIALOGUE_RUNTIME_CLOSURE_2026-09-03.md`.
