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

## 3. M8.1 — CLOSED WITH ACCEPTED EXCEPTION

**Closed by explicit operator decision on 2026-08-03.** M8.1 is closed as a
milestone. It is **not** closed as an unqualified PASS: one condition was
not met and is carried forward as an accepted exception.

**Passed — persistent embedding-cache scope.** Evidence relied on:
implementation committed as `38b1f62`; persistent `hf_cache` reuse passed on
three fresh-container runs; no Hugging Face downloads occurred during those
runs; Docker test suite TOTAL 66 / PASSED 66 / FAILED 0 / SKIPPED 0. The
compose and Dockerfile contract checks covered by the test suite also passed.

**Not met — historical exact-top-1 condition** recorded in the 2026-07-14
snapshot.

**Accepted exception.** By explicit operator decision, that unresolved
condition is reclassified and transferred out of M8.1 acceptance to open
issue **R-001 — Retrieval Baseline Provenance**, which remains:

OPEN — CAUSE NOT ESTABLISHED — NO CODE CHANGE AUTHORISED.

**This closure does not imply that the retrieval discrepancy passed or was
resolved.** It is neither. This is a documentation-only decision. No code
change was made, proposed, or authorised. The frozen components — corpus,
ingested vectors, embedding model and dimension, Qdrant collection, and the
retrieval contract — remain frozen.

---

## 4. R-001 — Retrieval Baseline Provenance — CLOSED WITH ACCEPTED PROVENANCE EXCEPTION

**Status:** CLOSED WITH ACCEPTED PROVENANCE EXCEPTION.

**Closed by explicit operator decision on 2026-08-03 (Phase E), following the
read-only Phase D audit.** This is a documentation-only closure. It does not
establish a technical cause and does not authorise, propose, or make any
retrieval-code correction, re-ingestion, or configuration change. Tracked
independently of M8.1 and of E1.

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

**Closure basis — an accepted provenance exception, not a proven cause.**
The factual causal mechanism behind the discrepancy remains **NOT
ESTABLISHED**. This index makes no claim that a transcription error
occurred, that a model revision changed, that the retrieved sets are
equal, or that nondeterminism has been completely excluded. Each of those
remains undetermined on the available evidence.

The historical runtime state cannot be deterministically reconstructed
from the preserved provenance, because the required embedding-model,
library, and runtime provenance for the 2026-07-14 observation was not
sufficiently pinned or preserved. **This does not mean historical
`p12::c1` is impossible to reproduce in principle.** It means the
historical baseline is **not deterministically reproducible from the
evidence currently preserved in this repository.**

Existing evidence does not justify or authorise a retrieval-code
correction. Closure is based on an operator-accepted provenance exception,
not on a proven technical cause or a code fix. No retrieval code was
repaired or changed as part of this closure.

---

## 5. E1 — Thin-client compliance — CLOSED / PASS (5/5)

**Status:** CLOSED / PASS (5/5).

**Closed by explicit operator decision on 2026-08-03 (Phase E), following the
read-only Phase D audit.** A Streamlit client exists under `ui/` and was
committed as `11b7056` (2026-07-14). The Phase D audit established, against
the thin-client acceptance criteria:

1. No ION reasoning exists in the frontend — **PASS**.
2. No retrieval logic exists in the frontend — **PASS**.
3. No MIVE comparison or orchestration exists in the frontend — **PASS**.
4. Backend functionality is reached only through REST/SSE interfaces — **PASS**.
5. The frontend has a separate containerized boundary — **PASS**.

**Architectural thin-client compliance: PASS (5/5).**

**Specification-alignment gap (separate, non-blocking).** The historical
expectation of a React/Vite `frontend/` differs from the implemented
Streamlit `ui/` structure. This is a documentation-currency /
specification-alignment gap, **not** an E1 architectural compliance
failure, and it does not block this closure. Any update to ADR-009,
`docs/16_TARGET_FILE_TREE.md`, or related target documentation remains a
separate future task and was not made as part of this closure.

Tracked independently of M8.1 and of R-001.

---

## 6. What this index does not assert

- It does not assert that M8.1 passed without exception. M8.1 is closed
  with an accepted exception (section 3).
- Closing R-001 (section 4) does not resolve the retrieval top-1
  discrepancy or attribute a cause. The cause remains **NOT ESTABLISHED**;
  closure rests on an accepted provenance exception, not a proven
  technical explanation.
- Closing E1 (section 5) certifies architectural thin-client compliance
  only. It does not certify frontend/directory specification alignment
  with the historical React/Vite expectation, which remains a separate,
  non-blocking documentation gap.
- Reaching 47/47 technical acceptance (section 7) does not itself
  constitute a commit, push, tag, release, or deployment. Those remain
  separate, explicitly authorised operator decisions, not yet taken.
- It does not modify, correct, or reinterpret either handover document.
- It does not authorise any code change, re-ingestion, or scope expansion.

---

## 7. Technical acceptance — 47/47 VERIFIED (2026-08-04)

**Status:** all 47 mandatory criteria in `docs/10_ACCEPTANCE_CRITERIA.md` are
now evidence-backed as PASS. This is a **technical verification record
only** — it does not itself constitute a commit, push, tag, release, or
deployment decision. Those remain separate, explicitly authorised operator
actions, not yet taken.

- **R-001 — Retrieval Baseline Provenance:** CLOSED WITH ACCEPTED PROVENANCE
  EXCEPTION (section 4). Cause remains NOT ESTABLISHED; historical baseline
  not deterministically reproducible from preserved evidence.
- **E1 — Thin-client compliance:** CLOSED / PASS (5/5) (section 5).
  Architectural compliance proven; frontend/directory specification
  alignment with the historical React/Vite expectation remains a separate,
  non-blocking documentation gap.
- **A1 — Clean-environment corpus ingestion:** PASS — PROVEN. Isolated,
  ephemeral ingestion (no persistent Qdrant volume attached, `hf_cache`
  mounted read-only, no external network reachable) completed with exit
  code `0`: `files processed: 9  files failed: 0`; `chunks created: 6063`;
  `unique chunk_ids: 6063`; `qdrant vectors: 6063` — all three counts equal.
  All 9 distinct source files independently confirmed present via a full
  payload scroll of the temporary collection (`next_page_offset: null`).
- **I2 — Real HTTP transport for `POST /ask`:** PASS — PROVEN. Targeted test
  `backend/tests/test_transport_api.py::test_post_ask_returns_complete_rendered_result_for_real_question`:
  `1 passed`, exit code `0`. Full backend suite: `65 passed, 7 skipped`,
  exit code `0` — all 7 skips identified as `test_embedding_cache.py`'s
  `docker-compose.yml`-presence checks, an artifact of mounting the current
  workspace `backend/` directory over the container's `/app` (shadowing the
  image's baked-in copy of that file); unrelated to I2, and the I2 test
  itself is not among the skipped tests. Test execution occurred only after
  the container's Docker network attachments were removed (confirmed empty
  network map before either pytest command ran).
- **I3 — DEBUG-gated SSE:** PASS — PROVEN. Isolated container run (existing
  backend image, no rebuild): `TOTAL 71 / PASSED 71 / FAILED 0 / SKIPPED 0`,
  including the three tests proving the 404 gate fires when `DEBUG` is
  false/unset, fires before readiness/core initialisation, and that the
  route remains available when `DEBUG=true`.
- **I6 — Three-service Compose startup:** PASS — PROVEN. `docker compose up
  -d` (existing images, no build) started `qdrant`, `backend`, and `ui`
  together; each independently health-checked over HTTP 200; the running
  `ui` container's filesystem confirmed to contain no backend application
  code; the persistent `qdrant_storage` volume's identity confirmed
  unchanged before and after; shut down via `docker compose stop` (not
  `down -v`).

**Documentation reconciled alongside this record:** `docs/15_API_CONTRACT.md`
corrected to match the implemented `POST /ask` contract exactly (no
`/api/v1` prefix; a flat rendered-result response, not an envelope). The
broader envelope shape is retained there only as an explicitly labelled
future proposal, not the current contract.

**Not yet done, and not claimed here:** no commit, push, tag, release, or
deployment has occurred as part of reaching 47/47. The validated
implementation exists only as uncommitted working-tree changes at HEAD
`29c7d9e2b7dac3faff31194e9087e317b8c80c11`, across exactly four paths:
`backend/app/main.py`, `backend/tests/test_transport_api.py`,
`ui/client.py`, `ui/tests/test_client.py`.
