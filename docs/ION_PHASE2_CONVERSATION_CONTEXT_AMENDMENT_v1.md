# ION Phase 2 — Bounded Conversation Context: Contract Amendment v1

Status: IMPLEMENTED on local branch `phase2-conversation-context-20260929`
(base `aa6733e`). Not committed, pushed or deployed at the time of writing.

Operator decisions: D1–D6 approved 2026-09-29 (04:27Z). Guard scope decided
2026-09-29 (04:34Z). Implementation authorized 2026-09-29 (04:37Z).

This document records narrow, versioned amendments to decisions that were
previously frozen. It does not rewrite those decisions. The original texts in
`ION_SESSION_TURN_CONTROLLER_CONTRACT_v1.md` and
`ION_E4_INTEGRATED_GOVERNED_PILOT_CONTRACT_v1.md` stay unchanged, with only an
appended pointer to this file.

## Purpose

A follow-up question such as "tell me more", "how does that work in practice?",
"what do you mean by that?" or "and what about the risks?" needs to know what
was just discussed. Phase 2 provides that through a bounded, structured,
in-session context. It does not weaken any evidence boundary:

    PRIOR CONVERSATION != EVIDENCE
    PRIOR INTERPRETATION != SOURCE AUTHORITY
    RETRIEVAL AND ADMISSION REMAIN AUTHORITATIVE

## Amendments

### OD22-08-A1 (amends OD22-08: session state)

Session runtime state may additionally hold one private, bounded
`context_window` of at most **2** `PriorTurnContext` values. Each holds
exactly four things:

- the prior COMPLETED turn's `turn_id`;
- its normalized user question;
- its IVE report `abstract` (the verified interpretation, never the
  VOE-composed or rendered text);
- its IVE report `uncertainty` items.

All of these are capped per D6. The following have no field at all:

- evidence identities or evidence content;
- claims or relations;
- composed or rendered text;
- dialogue instructions;
- persistence.

The public `Session` snapshot is unchanged. FAILED captures and CLARIFY
outcomes never enter the window. The window is per session, in memory only,
and gone when the session ends or the backend restarts.

### TR-A1 (amends the Turn Record contract, v0.1 → v0.2)

- `TURN_RECORD_CONTRACT_ID` changes to `ION_TURN_RECORD_V0_2` and
  `TURN_RECORD_VERSION` to `0.2`.
- `TurnRecord` gains one optional field,
  `conversation_context: ConversationContextBinding | None`.
  - It is present exactly when the turn ran with a non-empty context, on
    COMPLETED and FAILED records alike.
  - It carries the bounded context verbatim (`prior_turns`), its canonical
    `context_sha256`, and the exact `retrieval_query` (D4).
- It is an input record, not evidence and not authority.
- All other structural absences remain: no `session_id`, no turn ordinal, no
  parent-turn link, no rendered answer, no evidence content.
- The canonical hash is recomputed and verified when the `ConversationContext`
  is constructed.
  - The Turn Record package carries the hash verbatim and keeps its fixed
    import boundary (no hashing or serialization import).
  - Tests prove the recorded hash recomputes from the recorded turns.

### MC-A1 (amends the Model Context contract, v0.1 → v0.2)

- `MODEL_CONTEXT_CONTRACT_ID` changes to `ION_MODEL_CONTEXT_ASSEMBLY_V0_2` and
  `MODEL_CONTEXT_VERSION` to `0.2`.
- `CONVERSATION_MEMORY` moves from deferred to implemented, for this bounded use
  only. It is carried as
  `ModelContextAssembly.conversation_memory: ConversationMemorySegment | None`:
  one to two `ConversationMemoryTurn(question, interpretation, uncertainty)`
  values plus the context hash.
  - It holds no identity, citation or document field.
- `DIALOGUE_INSTRUCTION` and `MODEL_OUTPUT` stay deferred.
- Prior-turn IVE text enters only as `CONVERSATION_MEMORY`. It never enters as
  `EVIDENCE`, and never as same-turn `MODEL_OUTPUT`.
- With no context, the assembly is exactly the v0.1 shape and the prompt is
  byte-identical to the v0.1 prompt.

Prompt block, used only when context exists, placed between QUESTION and
CONTEXT DOCUMENTS, with no square brackets:

```
PRIOR CONVERSATION (NOT EVIDENCE):
These are earlier turns of this conversation, shown only so you can understand what the QUESTION refers to. They are not context documents and not evidence. Do not cite them, do not treat their content as established fact, and do not repeat a claim from them unless a CONTEXT DOCUMENT below supports it.
Prior turn 1:
User question: …
Interpretation given: …
Uncertainty noted: …   (items joined by "; ", or "none")
```

### E4-A1 (amends the E4 pilot exclusion)

- The E4 exclusion "conversation memory" now reads "conversation memory beyond
  OD22-08-A1".
- Still excluded: persistent session storage, `DialogueState`, persistent
  personalization, and cross-session memory.

### RQ-A1 (retrieval query, D3)

- **With context:** `retrieval_query = <most recent prior user question> + "\n" + <current question>`.
  The prior question used is the stored, capped value.
- **Without context:** retrieval receives the current question, the same object as
  before Phase 2.
- Prior assistant or model text never enters retrieval.
- The Context Pack, governance `question_id`, Model Context `question`, Turn
  Record `question` and composer input all keep the current question.

#### RQ-A1-R1 (revision of RQ-A1, operator decision CHANGE_TO_ROOT_ANCHOR, 2026-09-29)

This revision supersedes the "with context" line of RQ-A1 above. The original text
is kept for history.

**Why.** An offline probe used the production MiniLM path, pinned revision
`1110a243…`, with CP-0003 vector parity at a maximum difference of 1.6e-7, over pack TW-CP-0005.
- The original rule lost the ION topic entirely on chained vague follow-ups (turns 3 and 4).
- A root-anchored query kept it at 5 of 5.

**Rule.**
- **With context:** `retrieval_query = <session root question> + "\n" + <current question>`.
- **Root question:** the normalized user question of the session's **first COMPLETED**
  turn, capped at 500 characters (the D6 question cap).
  - It is set once and never replaced.
  - CLARIFY outcomes and FAILED turns neither establish nor replace it.
  - It is held privately in the session's runtime state. It is never persisted, never
    shared across sessions, and cleared with the session (close, or a new session).
  - It is carried on `ConversationContext.root_question`, which is not part of
    `context_sha256` and is not shown to the model.
  - Because this adds a required structural field, the Conversation Context contract
    moves from `ION_CONVERSATION_CONTEXT_V0_1` / `0.1` to
    **`ION_CONVERSATION_CONTEXT_V0_2` / `0.2`** (operator decision, 2026-09-29).
    `context_sha256` semantics are unchanged: it hashes `prior_turns` only.
    No other contract version changes; the Turn Record and Model Context stay at v0.2.
  - It remains available after the root turn has left the 2-turn window.
- **Unchanged:**
  - no context means the current question, byte-identical to before;
  - no prior assistant or model text in retrieval;
  - the root never enters evidence, the Model Context or the prompt;
  - the 2-turn window, the D6 caps and no summarization;
  - the exact `retrieval_query` is still recorded in the Turn Record's
    `conversation_context` binding.

### CG-A1 (citation-subset guard, D5, scoped)

The guard runs **only on turns that carry a non-empty conversation context**.
It is the compensating boundary for the new PRIOR CONVERSATION input.

**On a context turn:**
- Every `evidence_document_id` cited in the IVE report's claims or relations
  must be an evidence item of this turn's model context.
- A violation raises a normalization-stage error. The existing stage map
  returns HTTP 422 for it.
- The turn is recorded as FAILED, with its model execution and context binding
  kept.
- Nothing is stripped or repaired.

**On a no-context turn** (turn 1, a new session, legacy `/ask`), behaviour is
unchanged: the renderer silently excludes a stray citation (D20-20).

**OPEN (not implemented in Phase 2):** evaluate making the citation-subset guard
global for all ION turns, including legacy `/ask` and turn 1.

### Restated as unchanged

- **OD23-05 / OD23-06:** the Adaptive Dialogue engine receives only
  `DialogueTurnInput(question=<current normalized question>)`. It has no
  session, history, context or prior output input, and no `DialogueState`.

## D6 limits (fixed)

| Limit | Value |
|---|---|
| Prior turns | last 2 COMPLETED turns |
| Question | ≤ 500 characters |
| Interpretation (IVE abstract) | ≤ 1,200 characters |
| Uncertainty | ≤ 3 items × 300 characters |
| Total (all text fields) | ≤ 4,000 characters; the oldest turn is dropped while over |
| Truncation | strip, then cut to exactly N code points ending in "…" (U+2026) |
| Summarization | none |
| FAILED / CLARIFY turns | never enter the window |

## Unchanged components

- `adaptive_dialogue/*`
- `main.py` routes and `api/service.py`
- retrieval implementation, Context Pack builder, governance and admission
- renderer and response composer
- VOE profile assets and the `voe/` client
