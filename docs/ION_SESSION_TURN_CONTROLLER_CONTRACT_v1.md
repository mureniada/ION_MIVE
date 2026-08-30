# ION Session / Turn Controller Contract — v1

**Status:** FROZEN
**Task:** TASK 22.2 — Freeze Session / Turn Controller Contract v1
**Predecessor:** TASK 22.1 — Session / Turn Current-Surface Measurement (ACCEPTED AND CLOSED; not revised or rerun here)
**Scope of this document:** a bounded contract artifact only. No production code, no test code, and no wiring exist yet. This document is the authority a future implementation phase must build against; it does not itself implement anything.

---

## 1. Purpose

This document freezes the operator decisions and architecture laws that govern TASK 22 — the Session / Turn Controller — following the read-only measurement performed in TASK 22.1. It fixes:

- the accepted architectural position of the Controller relative to the existing Core/Orchestrator and the Task-21 governed turn pipeline,
- what the Controller owns and what Core continues to own,
- the minimum session state shape,
- the ten operator decisions (OD22-01 through OD22-10) that resolve the open questions TASK 22.1 raised,
- the fourteen acceptance laws (L22-01 through L22-14) any Session/Turn Controller implementation must satisfy, including a correction to the law originally proposed as L22-04 in TASK 22.1,
- what is explicitly out of scope for Task 22.

Nothing in this document authorizes touching the Task-21 governed turn pipeline (retrieval, context pack, governance, governed evidence, model context, model gateway, MIVE, renderer, Turn Record materialization). That pipeline's internal order and contracts remain exactly as TASK 22.1 observed them.

---

## 2. Architectural position

```
SESSION / TURN CONTROLLER
        |
        v
CORE / ORCHESTRATOR   (Core.ask())
        |
        v
EXISTING TASK-21 GOVERNED TURN PIPELINE
  (retrieval -> context pack -> governance -> governed evidence
   -> model context -> model gateway -> [MIVE, not applicable under SINGLE]
   -> renderer -> TurnRecord materialization)
```

The Controller sits strictly **above** Core. It calls `Core.ask()` for each turn's execution and never bypasses, reorders, or duplicates any stage of the governed pipeline beneath it.

### 2.1 Controller owns

- session identity
- session lifecycle
- ordered turn membership
- next turn ordinal
- one-active-turn-per-session enforcement
- preservation of captured TurnRecords

### 2.2 Core owns

- one governed turn execution per `Core.ask()`
- request/turn identity (`request_id`, bound verbatim as `turn_id`)
- retrieval
- governance
- `GovernedEvidenceSet`
- `ModelContext`
- model execution
- rendering
- `TurnRecord` materialization

The Controller never re-implements, re-derives, or duplicates anything in §2.2. It observes and preserves what Core already produces.

---

## 3. Minimum session state

A session carries exactly:

| Field | Description |
|---|---|
| `session_id` | Stable session identity, independent of any one turn. |
| `created_at` | Session creation timestamp. |
| `status` | One of the Session Status v1 values (§4). |
| `next_turn_ordinal` | The ordinal to assign to the next turn admitted into this session. |
| `active_turn` | Identity of the currently in-flight turn for this session, or absent if none is active. |
| `ordered_turns` | The session's append-only, ordered list of captured `SessionTurnEntry` records (§5). |

No other field is part of the minimum session state at v1.

## 4. Session status v1

Exactly two values:

- `ACTIVE`
- `CLOSED`

No `PAUSED`, `SUSPENDED`, or other intermediate status exists at v1.

## 5. Session Turn Entry

A `SessionTurnEntry` is an immutable Controller-owned wrapper, kept **outside** the `TurnRecord` contract (OD22-02):

| Field | Description |
|---|---|
| `session_id` | The session this entry belongs to. |
| `turn_ordinal` | This turn's position within the session's ordered history. |
| `turn_id` | The turn identity, equal to the underlying `TurnRecord.turn_id`. |
| `turn_record` | The captured, immutable `TurnRecord` produced by `Core.ask()` for this turn. |

**Invariant:** `turn_id == turn_record.turn_id`

Session history (`ordered_turns`) is **append-only**: entries are added in ordinal order and are never removed, reordered, or mutated once appended.

The `TurnRecord` contract itself (`backend/app/modules/turn_record/models.py`) **remains unchanged** by Task 22. No field is added to it, and none of its existing invariants are relaxed.

---

## 6. Operator decisions (frozen)

**OD22-01** — Expose the already-materialized `TurnRecord` from `Core.ask()` only through a minimal optional observer/capture seam. Do **NOT** add `TurnRecord` to `AskResult` or the HTTP response.

**OD22-02** — Session identity and turn ordering remain outside `TurnRecord`. Use a Controller-owned immutable `SessionTurnEntry` wrapper (§5).

**OD22-03** — Task 22 v0.1 storage is in-memory only. Durable persistence is deferred.

**OD22-04** — REST/API session exposure is deferred.

**OD22-05** — At most one active turn per session. Different sessions are not globally serialized.

**OD22-06** — Controller is execution-profile agnostic. Task 22 proof may use STANDARD_GEMINI / 0.1 / SINGLE.

**OD22-07** — If Core fails and no `TurnRecord` is successfully captured, the Controller MUST NOT fabricate one.

**OD22-08** — Session state may contain lifecycle/identity metadata and immutable `TurnRecord` references only. No evidence content, model-output text, rendered answer, conversation memory, or dialogue instructions.

**OD22-09** — No automatic cross-turn evidence reuse.

**OD22-10** — Adaptive Dialogue is outside Task 22.

---

## 7. Acceptance laws (frozen)

**L22-01** SESSION STATE != EVIDENCE

**L22-02** PREVIOUS MODEL OUTPUT != SOURCE EVIDENCE

**L22-03** TURN RECORD != SOURCE EVIDENCE

**L22-04** AT MOST ONE Core TurnRecord materialization attempt per `Core.ask()`; every successfully captured TurnRecord is preserved exactly once.

> Correction to TASK 22.1: this law is **not** frozen as "ONE TURN -> ONE TURN RECORD." A `TurnRecord` is not guaranteed to exist under every possible failure path, because failed-record materialization is best-effort (`Core.ask()`'s failure handler suppresses a secondary materialization fault rather than retrying it). The Controller must not assume every turn — including every failed turn — yields a capturable `TurnRecord`.

**L22-05** CLOSED TURN RECORD IS IMMUTABLE

**L22-06** ONE SESSION MAY CONTAIN ORDERED MULTIPLE TURNS

**L22-07** CONTROLLER OWNS SESSION LIFECYCLE; ORCHESTRATOR OWNS ONE GOVERNED TURN

**L22-08** FAILURE MUST NOT ERASE PRIOR CLOSED TURNS

**L22-09** NO CROSS-TURN EVIDENCE REUSE

**L22-10** NO ADAPTIVE DIALOGUE IN TASK 22

**L22-11** ONE ACTIVE TURN PER SESSION

**L22-12** DIFFERENT SESSIONS ARE NOT GLOBALLY SERIALIZED

**L22-13** TURN RECORD CONTRACT REMAINS UNCHANGED

**L22-14** TASK-21 GOVERNED PIPELINE ORDER REMAINS UNCHANGED

---

## 8. Out of scope for Task 22

- Adaptive Dialogue
- Dialogue Profile
- conversation memory
- semantic memory
- REST session API
- durable database persistence
- multi-user authorization
- multi-tenant session isolation
- DUAL/MIVE implementation
- cross-turn evidence carry-forward

---

## 9. Provenance

This contract freezes findings from TASK 22.1 (Session / Turn Current-Surface Measurement, `TASK22_1_MEASUREMENT_PASS`), which measured, from actual code, that: no session abstraction exists anywhere in the repository; `Core.ask()` is the single, stateless, one-turn-per-call entry point (`backend/app/core/orchestrator.py`); the `TurnRecord` contract (`backend/app/modules/turn_record/models.py`) is immutable and materialized at most once per `Core.ask()` call but is currently ephemeral — discarded before `ask()` returns; and no field for session, conversation, ordering, or dialogue identity exists on `TurnRecord`, `ModelContextAssembly`, or `ExecutionProfile`, by explicit, tested design. Those findings, and the operator decisions and laws in §6-§7 above, are the fixed basis for any subsequent Task 22 implementation phase.
