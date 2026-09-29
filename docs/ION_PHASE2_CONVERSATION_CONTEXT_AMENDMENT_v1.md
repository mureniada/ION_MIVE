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
