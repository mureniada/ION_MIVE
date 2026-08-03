# ION MIVE — Handover Routing and Status Index

**Date:** 2026-08-03
**Type:** Current handover routing and status index
**Scope:** Routing only. This index does not contain operational
instructions and does not supersede the epistemic invariants recorded in
`CLAUDE.md` and `docs/`.

This is the entry point for determining which handover document applies and
what the confirmed status is. The two handover documents it routes to are
preserved byte-for-byte and are not modified by this index.

---

## 1. Document routing

| Document | Classification | How to use |
|---|---|---|
| `ION_MIVE_HANDOVER_INDEX.md` (this file) | **CURRENT** — routing and status index, 2026-08-03 | Read first |
| `ION_MIVE_SESSION_HANDOVER_2026-07-14.md` | **HISTORICAL OPERATIONAL SNAPSHOT** — valid for the 2026-07-14 state | Read for context, provenance, frozen-component list, and prohibitions. **Not current executable instructions.** Its task order reflects 2026-07-14; several tasks have since been completed |
| `CLAUDE_HANDOVER_ION_MIVE_CLEANROOM_v1.md` | **HISTORICAL / SUPERSEDED** | Provenance only. **Its operational instructions must not be executed.** Its build order predates the delivered system. Its epistemic and scope sections remain informative |

This index does not modify either handover document. Both are preserved
byte-for-byte.

---

## 2. Confirmed current status — verified 2026-08-03

- **Credential rotation and revocation completed.** The previously exposed
  credentials have been revoked. No key values are recorded in this index.
- **Provider-level checks passed** for the rotated credentials
  (OpenAI and Gemini).
- **Backend recreation completed**, and `GET /health` returned **HTTP 200**.
- **One live MIVE call passed** end-to-end on the two-provider path, with
  `status: success` and `error_stage: null`. Observed on that call:
  total estimated cost $0.008714; retrieval 52,288.211 ms;
  comparison 21.261 ms; total 80,361.252 ms.
- **M8.1 code was already committed as `38b1f62`** (2026-07-14), covering
  `backend/Dockerfile`, `backend/tests/test_embedding_cache.py`, and
  `docker-compose.yml`.
- **No additional M8.1 code commit is pending.**
- **Persistent `hf_cache` reuse showed no Hugging Face downloads** on three
  fresh-container runs.
- **Docker tests: TOTAL 66 / PASSED 66 / FAILED 0 / SKIPPED 0.**

---

## 3. M8.1 status — ACCEPTANCE OPEN

- **Passed:** the compose and Dockerfile contract checks (covered by the
  test suite) and the cache-reuse check (no Hugging Face downloads on three
  fresh-container runs).
- **Not met:** the historical exact-top-1 condition recorded in the
  2026-07-14 snapshot.
- **M8.1 acceptance therefore remains open.**
- **Closure requires an explicit owner decision.** It must not be closed by
  an automatic code change, and no code change is proposed. The frozen
  components — corpus, ingested vectors, embedding model and dimension,
  Qdrant collection, and the retrieval contract — remain frozen.

---

## 4. Retrieval top-1 discrepancy — UNRESOLVED

**Historical expected top-1** (recorded in the 2026-07-14 snapshot):
`sacred_economics_book_text::p12::c1`

**Current observed top-1** (three fresh-container runs, 2026-08-03):
`sacred_economics_book_text::p111::c1`

**`p12::c1` currently appeared at list index 1 — the second result.**

Current observed top-5, 2026-08-03:

```
0  sacred_economics_book_text::p111::c1   0.621074
1  sacred_economics_book_text::p12::c1    0.612067
2  sacred_economics_book_text::p23::c1    0.606155
3  sacred_economics_book_text::p303::c0   0.595590
4  sacred_economics_book_text::p35::c1    0.590348
```

Constraints on what can be concluded:

- **No historical top-5 baseline exists.** Only the single expected top-1
  value was ever recorded. There is nothing to compare the current list
  against.
- **Equal `context_characters` does not prove set equality.** The value
  5965 appears in both the 2026-07-14 record and the 2026-08-03 run. Equal
  character counts are consistent with an unchanged set but do not
  establish one.
- **Three identical runs show observed stability across those runs.** They
  do not strictly exclude nondeterminism under other conditions.
- **No embedding-model revision is pinned** in code, configuration, the
  Dockerfile, or dependency declarations, and no dependency lock file
  exists. No pre-M8.1 model revision was recorded. The model cache
  currently holds a single snapshot,
  revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`.
- **Within the file types searched during the 2026-08-03 diagnosis,
  `p12::c1` was found only in the 2026-07-14 handover snapshot.**

**The cause of the discrepancy remains unresolved.** This index makes no
claim that a transcription error occurred, that a model revision changed,
that the retrieved sets are equal, or that nondeterminism has been
completely excluded. Each of those remains undetermined on the available
evidence.

---

## 5. Open issue E1 — frontend thin-client compliance

A Streamlit client exists under `ui/` and was committed as `11b7056`
(2026-07-14). **Whether it satisfies the thin-client constraints — no
intelligence, retrieval, or comparison logic; backend reached only through
the REST and SSE API — has not been verified.** E1 remains open and is
tracked independently of M8.1.

---

## 6. What this index does not assert

- It does not close M8.1.
- It does not resolve the retrieval top-1 discrepancy or attribute a cause.
- It does not verify E1.
- It does not modify, correct, or reinterpret either handover document.
- It does not authorise any code change, re-ingestion, or scope expansion.
