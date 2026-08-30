# ION Adaptive Dialogue Decision Engine Contract — v1

**Status:** FROZEN
**Task:** TASK 23.2 — Freeze Adaptive Dialogue Decision Engine Contract v1
**Predecessor:** TASK 23.1 — Adaptive Dialogue Engine Current-Surface Measurement (classification `TASK23_1_CURRENT_SURFACE_MEASUREMENT_PASS`; not revised or rerun here)
**Scope of this document:** a bounded contract artifact only. No production code, no test code, and no wiring exist yet. This document is the authority a future implementation phase (TASK 23.3+) must build against; it does not itself implement anything.

---

## 1. Purpose

This document freezes the operator decisions (OD23-01 through OD23-08) and authority laws (AD23-L01 through AD23-L16) that govern TASK 23 v0.1 — the Adaptive Dialogue Decision Engine — following the read-only measurement performed in TASK 23.1. It fixes:

- the conceptual architecture of the engine and the hard stop on its output,
- the exact v0.1 decision vocabulary and what each value does and does not mean,
- the minimum type set: `DialogueDecisionType`, `DialogueTurnInput`, `DialogueReasonCode`, `DialogueDecision`, the `AdaptiveDialogueEngine` interface, and the `AdaptiveDialogueError` hierarchy,
- the boundary between decision *vocabulary* (frozen here) and decision *rules* (not authorized here),
- the purity contract the engine must satisfy,
- what remains explicitly deferred, and what is protected and unchanged,
- the proposed (not created) TASK 23.3 implementation surface.

Nothing in this document authorizes touching `SessionController`, `Core.ask()`, the API, the renderer, `ModelContext`, the `ModelGateway`, or any other Task-21/Task-22 contract. Those pipelines' internal order and contracts remain exactly as TASK 23.1 observed them.

---

## 2. Contract position

```
DialogueTurnInput
        |
        v
ADAPTIVE DIALOGUE ENGINE
        |
        v
DialogueDecision

    STOP.
```

**No runtime arrow beyond `DialogueDecision` is authorized by this contract.** `AdaptiveDialogueEngine` is a decision instrument, not an orchestrator: it accepts one `DialogueTurnInput`, returns one `DialogueDecision`, and does nothing else. It does not call `Core.ask()`, does not call `SessionController`, does not call a provider, does not render, and does not persist anything. Whether, and how, some future caller acts on a `DialogueDecision` is explicitly out of scope (OD23-01) — invocation ownership is deferred to a later, separately authorized phase.

---

## 3. Frozen operator decisions

**OD23-01 — Runtime invocation.** Adaptive Dialogue v0.1 is UNWIRED. It does not modify or integrate with `SessionController`, `Core.ask()`, the API, the renderer, `ModelContext`, or the `ModelGateway`. Future invocation ownership is deferred.

**OD23-02 — Decision vocabulary.** Exactly two values exist: `PROCEED` and `CLARIFY`. No third value.

- `PROCEED` means: *the dialogue layer has no clarification objection to handing the current request to the next application/runtime owner.* `PROCEED` does **not** mean: retrieve evidence, authorize retrieval, admit evidence, invoke Core, invoke a provider, or answer the question.
- `CLARIFY` means: *the current dialogue input does not satisfy a frozen deterministic dialogue-clarity rule.* `CLARIFY` does **not** mean: `TurnRecord` closure, session state transition, `WAITING_FOR_USER`, rendering, or sending text to the user.
- `DIRECT_RESPONSE`, `DEEPEN`, and domain routing are DEFERRED — named nowhere in the v0.1 vocabulary, not even as unreachable members (unlike `CLARIFY`, which is a first-class v0.1 value with no authorized rule yet — see §7).

**OD23-03 — Engine strategy.** v0.1 is PURE, DETERMINISTIC, MODEL-FREE, and STATELESS BETWEEN EVALUATIONS. No provider execution.

**OD23-04 — CLARIFY lifecycle.** `CLARIFY` exists only as decision data in v0.1. This contract does not modify, and no implementation of it may modify, `TurnClosureState`, `TurnRecord`, `SessionStatus`, `SessionController`, or the renderer.

**OD23-05 — Input authority.** `DialogueTurnInput` may contain only primitive, explicitly supplied dialogue-control facts. It must not contain or reference: `Session`, `SessionTurnEntry`, `TurnRecord`, session history, evidence identity, evidence content, retrieved candidates, `GovernedEvidenceSet`, `ModelContext`, prior assistant output, conversation transcript, prior model output, provider output, `DialogueProfile`, or Content Pack content. The candidate fields `session_id` and `turn_ordinal` were evaluated against this constraint and against the smallest-input-surface principle; see §6 for the resulting decision (both OMITTED from v0.1).

**OD23-06 — Dialogue state.** No separate `DialogueState` is created in v0.1. This contract found no capability that `DialogueTurnInput` alone cannot represent (§6, §7). `DialogueState = DEFERRED`. No conversation memory.

**OD23-07 — Model context.** `DIALOGUE_INSTRUCTION` wiring is DEFERRED. This document does not modify `ModelContext`, and no field is added to `ModelContextAssembly` or any related type.

**OD23-08 — Dialogue Profile.** Dialogue Profile is entirely outside TASK 23 v0.1. No object in this contract stands in for it, extends it, or anticipates its shape.

---

## 4. Minimum types

Five types constitute the complete v0.1 vocabulary. No sixth type (in particular, no `DialogueState`) is authorized by this contract.

### 4.1 `DialogueDecisionType`

A closed enum, exactly two members:

```
PROCEED
CLARIFY
```

**Invariants:** membership is closed; no third value can be constructed. **Immutability:** enum members are immutable by construction (Python `Enum`). **Authority meaning:** names which of the two v0.1 decisions was reached; carries no other semantics. **Forbidden content:** no numeric confidence, no ordering, no additional members — an unsupported or unknown value fails closed rather than being coerced to either member.

### 4.2 `DialogueTurnInput`

```
question: str
```

That is the complete field set. `session_id` and `turn_ordinal` were both evaluated (§6) and OMITTED.

**Invariants (§8 restates and expands these as normalization rules):**
- `question` must be a non-empty string.
- `question` must already satisfy STRIP normalization — no leading or trailing whitespace — the same convention `model_context` and `turn_record` already use (`QUESTION_NORMALIZATION_STRIP`). This type verifies the convention; it never applies it, and never rewrites the question.
- A whitespace-only string is invalid: after the STRIP check above, a string that stripped to empty would already have been rejected as not-STRIP-normalized (a whitespace-only string is never equal to its own strip result unless both are empty, which is separately rejected by the non-empty rule). Both failure modes are named explicitly in §8 so the invariant is not left to be inferred from interaction between two other rules.

**Immutability:** frozen (no field may be reassigned after construction).

**Authority meaning:** the complete, verbatim statement of what the engine was asked to evaluate for one dialogue turn. It is input data only — never evidence, never a source of truth for anything beyond this one evaluation.

**Forbidden content:** every item listed in OD23-05 — no reference to `Session`, `SessionTurnEntry`, `TurnRecord`, session history, evidence (identity or content), retrieved candidates, `GovernedEvidenceSet`, `ModelContext`, prior assistant output, conversation transcript, prior model output, provider output, `DialogueProfile`, or Content Pack content has any field to enter through, on the same "structural absence, not nullable absence" principle every other Product contract in this repository already uses (`turn_record/models.py`, `model_context/models.py`).

### 4.3 `DialogueReasonCode`

A closed enum. v0.1 declares exactly one member:

```
NO_RULE_TRIGGERED
```

**Invariants:** membership is closed for this contract version; an unrecognized value fails closed. **Immutability:** enum member, immutable by construction. **Authority meaning:** states *why* a `DialogueDecision` reached its `decision_type` — a stable, machine-readable code, never free text. `NO_RULE_TRIGGERED` is the truthful code for every v0.1 evaluation, because v0.1 authorizes no `CLARIFY` rule (§7): the engine reaches `PROCEED` by the *absence* of any triggered rule, not by evaluating and passing one. **Forbidden content:** no natural-language rationale, no per-instance interpolated string, no confidence value — this is a closed enum precisely so that a caller can switch on it exhaustively. A future, separately authorized CLARIFY rule mints its own new closed member here (the same amendment discipline `model_context`'s `IMPLEMENTED_SEGMENT_CLASSES` / `DEFERRED_SEGMENT_CLASSES` split already demonstrates) — this contract does not pre-declare placeholder codes for rules that do not yet exist.

### 4.4 `DialogueDecision`

```
decision_type: DialogueDecisionType
reason_code: DialogueReasonCode
```

**Invariants:** `decision_type` must be a genuine `DialogueDecisionType` member; `reason_code` must be a genuine `DialogueReasonCode` member. Construction with any other value fails closed (§9). Beyond per-field membership, exactly one cross-field pairing invariant is enforced: `decision_type = CLARIFY` may never pair with `reason_code = NO_RULE_TRIGGERED`. `NO_RULE_TRIGGERED` is definitionally the code for the no-rule-fired default (§4.3) — it states that no deterministic clarification rule fired, which only `PROCEED` can truthfully carry. Construction with that combination fails closed with `DialogueDecisionError` (§10). This is the sole v0.1 cross-field pairing invariant required, and it is what makes CLARIFY's vocabulary-valid/implementation-unreachable status (§7) a structural property of `DialogueDecision` validation, rather than a fact that merely happens to hold because no caller has constructed the invalid pair. No other pairing rule is stated: with exactly one reason code declared, there is nothing else yet to pair against. Documenting which reason codes are valid under which decision type, beyond this one prohibition, is the responsibility of whichever future authorization introduces a second reason code.

**Immutability:** frozen; a `DialogueDecision`, once constructed, cannot be mutated.

**Authority meaning:** the complete, closed statement of one engine evaluation's outcome. Nothing beyond `decision_type` and `reason_code` is part of the v0.1 result.

**Forbidden content, explicitly:** no `confidence`, no `score`, no evidence ids, no provider metadata, no model reasoning, no chain-of-thought, no free-form rationale required for correctness, and no `clarification_prompt` — clarification text generation is deferred in full (§8).

### 4.5 `AdaptiveDialogueEngine` (interface)

A single-method interface/protocol:

```
evaluate(turn_input: DialogueTurnInput) -> DialogueDecision
```

**Invariants:** exactly one public method; no constructor dependency on any runtime object (no `Core`, no `SessionController`, no provider client, no store handle — the purity contract, §9, forbids all of them). **Immutability:** the interface itself carries no mutable state; a conforming implementation must not accumulate state between calls (OD23-03: "stateless between evaluations"). **Authority meaning:** the sole crossing point between `DialogueTurnInput` and `DialogueDecision` — the entire engine surface. **Forbidden content:** no second public method, no attribute exposing internal rule state, no callback or observer seam (unlike `Core.ask()`'s `on_turn_record`, nothing here is meant to be captured or observed — there is no side effect to capture).

### 4.6 `AdaptiveDialogueError` hierarchy

```
AdaptiveDialogueError(Exception)          # base
    DialogueInputError                    # invalid DialogueTurnInput construction
    DialogueDecisionError                 # invalid DialogueDecision construction
```

Both subclasses are required (§10): `DialogueInputError` and `DialogueDecisionError` validate two structurally different objects at two different points in the evaluation, exactly the way `SessionModelError` and `SessionControllerError` stay separate in TASK 22 — a caller catching one must not be assumed to have also guarded against the other. Neither subclass introduces a new transport stage or error-code mapping; this module is unwired (OD23-01), so no such mapping exists yet.

---

## 5. `DialogueDecisionType` (§C of the mission brief)

Restated for clarity as its own section per the requested contract shape: exactly `PROCEED` and `CLARIFY`. An unknown or unsupported value — whether from a malformed construction call or a future caller attempting to pass a string outside this vocabulary — fails closed with `DialogueDecisionError`. No coercion, no default, no "closest match."

---

## 6. `DialogueTurnInput` — field decision (§D of the mission brief)

**Evaluated fields:** `question: str`, `session_id: str | None`, `turn_ordinal: int | None`.

**Decision: `session_id` and `turn_ordinal` are OMITTED from v0.1.** `DialogueTurnInput` carries `question` only.

**Justification.** The rule boundary this contract freezes (§7) authorizes no rule that varies by session or by turn position — v0.1's only reachable behavior is a single, input-question-only validation followed by an unconditional `PROCEED`. A field with no consumer is speculative surface: CLAUDE.md's governing mandate ("prefer the smallest implementation that is testable, observable, and replaceable"; "don't design for hypothetical future requirements") forbids adding it in advance of an actual rule that needs it. This also keeps `DialogueTurnInput` trivially compliant with OD23-05's stateless-input requirement and OD23-06's "no `DialogueState` unless strictly justified" — a `session_id` field would be the first thread pulling the engine toward session-awareness, and no rule in this contract pulls that thread. Should a future, separately authorized CLARIFY rule need to vary by session or turn position, that rule's own authorization is the correct place to add the field it actually needs — not this contract, in advance, on spec.

**Normalization rules, specified exactly:**

- `question` must be a non-empty string. An empty string (`""`) is invalid; construction raises `DialogueInputError`.
- `question` must already satisfy STRIP normalization: `question == question.strip()`. A string with leading or trailing whitespace is invalid; construction raises `DialogueInputError`. This type verifies the convention already declared by `model_context`/`turn_record` (`QUESTION_NORMALIZATION_STRIP`) — it never applies a strip itself, and never rewrites the caller's input.
- A whitespace-only string (e.g. `"   "`) is invalid under the STRIP rule above: `"   ".strip() == ""`, so `"   " != "   ".strip()`, which already fails the STRIP check. It is listed as its own named case in §10 so the failure mode is explicit rather than left to be inferred from the interaction of two other rules.
- `question` is immutable input data: once a `DialogueTurnInput` is constructed, `question` cannot be reassigned (frozen dataclass), and the engine's `evaluate()` must not mutate it (§9).
- `session_id`, `turn_ordinal`: not present in v0.1. Should either be reintroduced by a future contract amendment, this section records the standing constraint that applies at that time: if present, `session_id` is control identity only (an opaque string, never a `Session` reference, never a lookup key into any store this engine can reach), and `turn_ordinal`, if present, must be a positive integer.

No higher-authority object reference (§4.2, OD23-05) has any field to enter through.

---

## 7. Rule boundary (§G of the mission brief)

This contract freezes a hard distinction between two things that must never be conflated:

**DECISION VOCABULARY** — the closed set of values a `DialogueDecision` may state (`PROCEED`, `CLARIFY`; `DialogueReasonCode.NO_RULE_TRIGGERED`). This is frozen by this document, now, in full.

**DECISION RULES** — the actual conditions under which a real evaluation reaches `CLARIFY` rather than `PROCEED`. **No such rule is authorized by this document.** This contract does not invent, imply, or gesture at a semantic-ambiguity threshold, a completeness heuristic, a length check, or any other condition that could produce `CLARIFY`.

Because no CLARIFY rule is authorized, the first lawful engine implementation (TASK 23.3) MAY return `PROCEED` (with `reason_code = NO_RULE_TRIGGERED`) for every structurally valid `DialogueTurnInput`, unconditionally. `CLARIFY` remains contract-valid — it is a real member of `DialogueDecisionType`, and any future implementation must remain capable of returning it — but it is **unreachable** until a deterministic rule is separately authorized and, at that time, given its own `DialogueReasonCode` member(s) under a contract amendment. This is the explicit, preferred alternative to fabricating a heuristic now: an honest "vocabulary exists, no rule produces it yet" is a lawful v0.1 shape, matching the same discipline `model_context`'s `DEFERRED_SEGMENT_CLASSES` already uses for `DIALOGUE_INSTRUCTION`, `CONVERSATION_MEMORY`, and `MODEL_OUTPUT`.

This unreachability is now a **structural** property, not merely a procedural convention. §4.4's pairing invariant forbids constructing `DialogueDecision(decision_type=CLARIFY, reason_code=NO_RULE_TRIGGERED)`, and `NO_RULE_TRIGGERED` is the only reason code v0.1 declares — so no valid `DialogueDecision` value can express `CLARIFY` at all until a second reason code is separately authorized. CLARIFY is therefore vocabulary-valid but implementation-unreachable by construction, not by omission. Nothing about `CLARIFY`'s lifecycle scope changes: it still does not mean `TurnRecord` closure, a session transition, `WAITING_FOR_USER`, rendering, or user-facing clarification text (OD23-02, OD23-04, §8).

---

## 8. Clarification text (§F of the mission brief)

Clarification text generation is DEFERRED in full for v0.1. The engine returns `CLARIFY` plus a stable `reason_code` only — it does not generate, template, render, or send any user-facing clarification text. There is no `clarification_prompt` field on `DialogueDecision` (§4.4), and no such field may be added to it under this contract. Producing user-facing text from a `CLARIFY` decision, should that ever be authorized, is a later phase's responsibility and will require its own contract — this document does not anticipate its shape.

---

## 9. Purity contract (§I of the mission brief)

`AdaptiveDialogueEngine.evaluate()`, and every v0.1 implementation of it, MUST NOT:

- perform network I/O
- perform filesystem I/O
- read environment variables
- call a provider
- call retrieval
- call `Core.ask()`
- mutate session state
- persist state
- use global mutable state
- render output
- mutate its input

**Determinism.** Identical valid inputs must produce semantically identical decisions. No timestamp is read or recorded. No UUID or other identifier is minted. No randomness of any kind is used. This mirrors the same purity discipline `model_context/builder.py` already states of itself ("Pure: no I/O, no clock, no randomness... no dataclass in this module has a field for any deferred class") and extends it to the dialogue layer.

---

## 10. Error model (§J of the mission brief)

Hierarchy: `AdaptiveDialogueError` (base) → `DialogueInputError`, `DialogueDecisionError` (§4.6).

Fail-closed behavior, specified exactly:

| Condition | Raises |
|---|---|
| Empty question (`""`) | `DialogueInputError` |
| Whitespace-only question (e.g. `"   "`) | `DialogueInputError` (fails the STRIP-normalization check, §6) |
| Question not STRIP-normalized (leading/trailing whitespace present, non-whitespace-only) | `DialogueInputError` |
| Invalid `session_id` | Not applicable in v0.1 — the field does not exist (§6) |
| Invalid `turn_ordinal` | Not applicable in v0.1 — the field does not exist (§6) |
| `decision_type` not a genuine `DialogueDecisionType` member | `DialogueDecisionError` |
| `reason_code` not a genuine `DialogueReasonCode` member | `DialogueDecisionError` |
| `decision_type = CLARIFY` paired with `reason_code = NO_RULE_TRIGGERED` | `DialogueDecisionError` |
| Any other invariant violation on either type | The corresponding error (`DialogueInputError` for `DialogueTurnInput`, `DialogueDecisionError` for `DialogueDecision`) |

No violation is ever downgraded into a partially populated object, a default value, or a silently coerced one — the same convention `SessionModelError`, `ModelContextBuildError`, and `TurnRecordMaterializationError` already establish throughout this repository.

---

## 11. Authority laws (frozen)

**AD23-L01** DIALOGUE DECISION != EVIDENCE

**AD23-L02** DIALOGUE INPUT != EVIDENCE

**AD23-L03** PROCEED != AUTHORIZATION TO RETRIEVE

**AD23-L04** PROCEED != AUTHORIZATION TO ADMIT EVIDENCE

**AD23-L05** CLARIFY != TURN CLOSURE

**AD23-L06** ADAPTIVE DIALOGUE DOES NOT OWN PROVIDER EXECUTION

**AD23-L07** ADAPTIVE DIALOGUE DOES NOT OWN RENDERING

**AD23-L08** ADAPTIVE DIALOGUE DOES NOT MUTATE SESSION STATE

**AD23-L09** ADAPTIVE DIALOGUE DOES NOT MUTATE TURN RECORD

**AD23-L10** MODEL OUTPUT CANNOT BECOME DIALOGUE EVIDENCE

**AD23-L11** SESSION HISTORY != DIALOGUE MEMORY

**AD23-L12** DIALOGUE PROFILE != DIALOGUE ENGINE

**AD23-L13** CONTENT != DIALOGUE ENGINE

**AD23-L14** ADAPTIVE DIALOGUE DOES NOT OWN RETRIEVAL

**AD23-L15** ADAPTIVE DIALOGUE DOES NOT OWN EVIDENCE ADMISSION

**AD23-L16** ADAPTIVE DIALOGUE DOES NOT FABRICATE PROVENANCE

---

## 12. Out of scope for Task 23 v0.1

- CLARIFY decision rules (any deterministic, model-assisted, or hybrid rule that could actually produce `CLARIFY`)
- Clarification text generation or rendering
- `DialogueState` (any form)
- `DialogueProfile`
- Conversation memory / cross-turn dialogue history
- `DIALOGUE_INSTRUCTION` → `ModelContext` wiring
- Invocation ownership (where in the call graph the engine is invoked from)
- `DIRECT_RESPONSE`, `DEEPEN`, domain routing
- Any modification to `SessionController`, `Core.ask()`, `TurnRecord`, `SessionStatus`, `TurnClosureState`, the renderer, `ModelContext`, `ModelGateway`, retrieval, `CoreAdapter`, or `GovernedEvidenceSet`
- REST/API exposure

---

## 13. Proposed TASK 23.3 implementation surface (not created)

```
backend/app/modules/adaptive_dialogue/__init__.py
backend/app/modules/adaptive_dialogue/models.py
backend/app/modules/adaptive_dialogue/engine.py

backend/tests/test_adaptive_dialogue_models_v0_1.py
backend/tests/test_adaptive_dialogue_engine_v0_1.py
```

None of these paths exist as of this contract. Their creation is a later, separately authorized phase.

**Protected and unchanged by this document and by the proposed surface above:**

```
backend/app/modules/session/*
backend/app/core/orchestrator.py
backend/app/modules/turn_record/*
backend/app/modules/model_context/*
backend/app/modules/model_gateway/*
backend/app/modules/renderer/*
backend/app/modules/retrieval/*
backend/app/modules/core_adapter/*
backend/app/modules/governed_evidence/*
backend/app/container.py
backend/app/main.py
backend/app/api/*
```

---

## 14. Contract acceptance (answered)

1. **What is the engine?** A pure function from one `DialogueTurnInput` to one `DialogueDecision`.
2. **What may it inspect?** Only the fields of `DialogueTurnInput` — v0.1: `question` alone.
3. **What may it return?** Only a `DialogueDecision`: a `DialogueDecisionType` (`PROCEED` or `CLARIFY`) paired with a `DialogueReasonCode` (`NO_RULE_TRIGGERED` in v0.1).
4. **What exactly does PROCEED mean?** No clarification objection to handing the request to the next application/runtime owner. Nothing more.
5. **What exactly does CLARIFY mean?** The input did not satisfy a frozen deterministic dialogue-clarity rule. Nothing more.
6. **What does the engine explicitly NOT own?** Retrieval, evidence admission, provider execution, rendering, session mutation, `TurnRecord` mutation, provenance, `DialogueProfile`, Content Pack content — the complete list in §11.
7. **Does it mutate session state?** NO.
8. **Does it own evidence?** NO.
9. **Does it call providers?** NO.
10. **Is it wired into runtime?** NO.
11. **Does it generate clarification text?** NO in v0.1 (§8).
12. **Is Dialogue Profile part of Task 23?** NO (OD23-08).
13. **Is conversation memory included?** NO (OD23-06).
14. **Is ModelContext wiring included?** NO (OD23-07).
15. **Are CLARIFY decision rules implemented by this contract?** NO (§7) — vocabulary only.

---

## 15. Provenance

This contract freezes findings from TASK 23.1 (Adaptive Dialogue Engine Current-Surface Measurement, classification `TASK23_1_CURRENT_SURFACE_MEASUREMENT_PASS`), which measured, from actual code, that: no `AdaptiveDialogueEngine`, `DialogueDecision`, `DialogueState`, or `DialogueProfile` exists anywhere in the repository; the only Adaptive Dialogue material present is a registered draft, unapproved, unwired content document (`local_materials/documents/adaptive_dialogue_intro.md`); the `ModelContext` contract already declares `DIALOGUE_INSTRUCTION` and `CONVERSATION_MEMORY` as permanently structurally absent, deferred segment classes with no field anywhere to carry them; `TurnRecord`'s `TurnClosureState` has exactly two members (`COMPLETED`, `FAILED`) with no `CLARIFY` or `WAITING_FOR_USER` member and no code path that branches before retrieval; and the Task 22 Session/Turn Controller (`SessionController` → `Core.ask()`) is fully proven and closed but carries no session-to-dialogue or dialogue-to-session wiring of any kind. Those findings, and the operator decisions and authority laws in §3 and §11 above, are the fixed basis for any subsequent Task 23 implementation phase.
