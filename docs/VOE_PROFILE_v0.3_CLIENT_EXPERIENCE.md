# VOE Dialogue Profile v0.3 — client-experience refinement

- **Status:** operator-approved 2026-09-29 for the staging refinement cycle (OP-DEC-20260929-09 content scope).
- **Production:** not authorized.
- **Principle:** strict inside, natural outside. This is a presentation-only change.

## What changed

- **Profile v0.3** is a new version beside v0.2 in `backend/app/modules/voe_profile/assets/`. The v0.2 files are kept byte-identical.
  - `01-VOE-DIALOGUE-PROFILE-v0.3.md` is v0.2 §1–§24 with four recorded edits: the title, the version, the status, and one §12 example that loses the word "evidence". It adds four new sections:
    - §25 voice and presence;
    - §26 qualifications and uncertainty in conversation;
    - §27 the two meanings of "layer" (D3), plus the metaphor and conditional-idea cautions;
    - §28 default length.
  - `02-VOE-STYLE-PARAMETERS-v0.2.json` sets profile version 0.3, concise-by-default, and additional prohibited drift.
  - 03 and 04 are unchanged.
  - The loader pins the four v0.3 files. Runtime fingerprint: `e9966bd07fe723b68e6d10112ffa8651983649c255859fd95d55abd9a90fbbee`. v0.2's was `432dd52a…70f5`.
  - Composer system instruction SHA-256: `46a5cd85…d5de` (under v0.2 it was `0524cf8c…f7de`). The composer's own preamble, schema and payload are unchanged.
- **Suggested-question filter:** it also blocks held Works material ("nature banking", the pending closing-block wording).
- **VOE client (`voe/`):**
  - The main answer bubble now shows the natural answer only.
  - **Sources (n)** and **About this answer** are both collapsed by default.
  - About this answer holds the presentation label, the disclaimer, the open points (uncertainty, verbatim) and how the sources connect (claim linkage). Nothing is deleted.
  - On non-composed answers, stated uncertainty stays visible as a compact "Still open:" line.
  - The loading text is "One moment…".
  - There are three authorized Works opening questions (Q12, Q13, Q23). After an answer, bounded Works navigation comes from `voe/works_navigation.json`, generated from the register and bound to the 14 OP-DEC-20260929-09 objects. Blocked items: Q9, Q16, Q17, Q27, weak Q1 and all held material.
  - `voe/source_labels.json` holds readable source names.

## `response_depth`: deliberately left out

`response_depth` (BRIEF / STANDARD / DEEP) remains validated metadata on `ComposerInput`. It is still not sent to the composer, for three reasons:

- **Length:** the approved length behaviour is a default of the profile (§28), not a per-request switch.
- **No transport:** the pilot API exposes no depth control.
- **Contract:** sending it would change the composer payload contract and the instruction-hash lineage for no user-facing gain in this cycle.

No second composer or model call exists.

## Not changed

Retrieval, root anchor, Qdrant, content packs, governed objects, admission, runtime evidence bridge, Model Context, IVE prompt, renderer, orchestrator flow, TurnRecord, ConversationContext, session controller, API fields, providers, Railway, production.
