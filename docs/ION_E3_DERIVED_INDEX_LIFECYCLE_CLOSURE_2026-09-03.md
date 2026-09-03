# ION E3 — Derived-Index Lifecycle Closure Report

**Date:** 2026-09-03
**Phase:** E3 (E3A → E3B → E3C → E3D → E3E)
**Status:** E3E CLOSURE MATERIALIZATION — accepted for exact-commit authorization. Not committed, not pushed.

## 1. Repository identity

| Field | Value |
|---|---|
| Worktree | `C:/Users/murenia/Documents/Projects/ION_ON/ION_MIVE_CLEANROOM_PACK_v1/.claude/worktrees/e3d-derived-index-lifecycle-0be6e5` |
| Branch | `claude/e3d-derived-index-lifecycle-0be6e5` |
| Starting / current HEAD | `e92fa8bc96bf29c659f72c824a88859bd21985d7` |
| `e2-3-expected-derived-index-20260903` resolves to | `e92fa8bc96bf29c659f72c824a88859bd21985d7` |
| Commit | NONE |
| Push | NONE |
| E4 | NOT ENTERED |

### Worktree re-bind (recorded for continuity)

E3D's initial execution header named an older worktree
(`e2-worktree-preflight-f4c803`) that did not match this session's actual
worktree/branch (`e3d-derived-index-lifecycle-0be6e5`) — HEAD matched exactly,
but the path/branch did not. Per that authorization's own gate rule, work
stopped rather than proceeding on an assumption. The operator subsequently
issued an explicit worktree re-bind authorization naming
`e3d-derived-index-lifecycle-0be6e5` / `claude/e3d-derived-index-lifecycle-0be6e5`
as the correct execution surface, which this and all subsequent work used.

## 2. Confirmed facts (prior phases, carried forward — not re-verified here)

- **E3A** — read-only investigation. PASS. No repository commit produced.
- **E3B** — lifecycle/authority architecture decision: blue/green physical
  Qdrant collections behind one stable alias, selected over alternatives. PASS.
  No repository commit produced.
- **E3C** — controlled, disposable Qdrant alias experiment. PASS. Demonstrated
  the alias bootstrap/cutover/rollback mechanism end to end against a
  disposable `qdrant/qdrant:latest` container; proved `QdrantRetrieval` reads
  transparently through an alias with no code change. No repository commit
  produced; no project/live Qdrant touched. Full evidence detail is in
  `ION_E3_DERIVED_INDEX_LIFECYCLE_CONTRACT_v1.md` §18.

**E3 repository commits after E2.3, before E3D: none.** The branch this work
sits on starts directly from `e92fa8bc96bf29c659f72c824a88859bd21985d7` and
carries no committed E3A/E3B/E3C implementation history — E3A–C were
evidence-gathering and decision phases, not implementation phases.

## 3. E3D — implementation surface (ten files)

Exactly ten new, untracked files were created; no existing tracked file was
modified.

**Production (six):**
`backend/app/modules/derived_index_lifecycle/{__init__,models,identity,materialize,verify,activation}.py`

**Tests (four):**
`backend/tests/test_derived_index_lifecycle_{models,materialize,verify,activation}_v0_1.py`

### Accepted module-placement decision

```
measure_candidate = STORE-FACING READ-ONLY MEASUREMENT FUNCTION, LOCATED IN materialize.py
```

Reason: the authorized six-production-file surface contained no separate
`measure.py`; `materialize.py` owns the physical candidate/store boundary
(write side and read side together); `verify.py` remains the one
store-independent pure-comparison boundary. Classification: **accepted
implementation placement, not architecture expansion.** The function was not
relocated for naming symmetry. Full rationale in the contract document §3.

### Candidate / build boundary

`materialize_candidate` builds one fresh candidate physical Qdrant collection
via a separate `QdrantRetrieval` instance's `index()` method — never
`.rebuild()`, never a deletion, never an active-alias mutation. It fails
closed, before any write, on: an already-existing candidate name; a candidate
name colliding with the active alias or the previous active collection; and a
recomputed `ExpectedDerivedIndexDescriptor` fingerprint that does not match the
one supplied. A written-point-count mismatch against the expected count fails
closed with no receipt produced. Full law in the contract document §6.

### Measured-state boundary

`measure_candidate` is read-only: `get_collection` + full-pagination `scroll`
(`with_payload=True`, `with_vectors=False`), pagination order discarded and
re-canonicalized by sorting on `qdrant_point_id`. Reported and enumerated point
counts are captured and preserved as two distinct fields, never collapsed.
Vector-schema measurement supports the single (unnamed or one named) vector
shape and fails closed on multiple named vectors. `MeasuredPointDescriptor`
can represent a missing `document_id` or `evidence_fingerprint` without
raising — measurement never hides invalid store state; PASS/FAIL
classification belongs entirely to verification. `measured_state_fingerprint`
excludes `measured_at`, so two measurements of the same unchanged store state
at different valid times share one fingerprint. Full law in the contract
document §8.

### `STRUCTURAL_V0_1` verification

`verify_candidate` is a pure function: no Qdrant client, no network, no
filesystem, no embedder, no clock, no mutation anywhere on its call path.
Bindings (expected fingerprint, physical-collection identity, declared
embedding profile, declared vector schema) are checked first and fold into
`bindings_match` without raising. `status = PASS` requires `bindings_match`,
`schema_match`, all four record-count equalities, and empty
missing/unexpected/duplicate/missing-payload/mismatch collections — all such
collections canonically (sorted) ordered. `STRUCTURAL_V0_1` is explicitly
bounded: it is record-set completeness, per-record evidence-fingerprint
equality, vector-schema equality and candidate/expected binding — **not**
universal vector-byte reproduction, remote model-revision attestation,
implementation-execution attestation, or semantic ranking equivalence. Full
law in the contract document §10.

### Blue/green alias activation

`activate_candidate` requires a PASS `VerificationReceipt`, a `hasattr`-checked
alias capability (`get_aliases`, `collection_exists`,
`update_collection_aliases` — never inferred from a version string), candidate
existence, and an exact prestate match between the caller-declared
`expected_previous_active_collection` and the actually-read current alias
target before performing exactly **one** `update_collection_aliases` request —
a single `CreateAliasOperation` for bootstrap (alias absent), or a
`DeleteAliasOperation` + `CreateAliasOperation` pair for a normal cutover, the
exact shape E3C's experiment proved. The prior physical collection is never
deleted. Activation never builds, embeds, measures or verifies. Full law in
the contract document §11.

### Rollback

`rollback_activation` consumes an `ActivationReceipt`, refuses a bootstrap
activation (`previous_active_collection is None`) with `DerivedIndexLifecycleError`,
re-reads the current alias target and requires it to still equal the
activation's `new_active_collection`, requires the previous physical
collection to still exist, then performs exactly **one** reverse alias-update
request. No rebuild, no re-embed, no deletion. Full law in the contract
document §12.

### Exclusive-writer qualification

```
CONCURRENT ALIAS WRITERS = NOT SUPPORTED
EXCLUSIVE LIFECYCLE-WRITER AUTHORITY = REQUIRED during ACTIVATE / ROLLBACK
```

The prestate-equality check reduces stale-operation risk; it is explicitly
**not** a distributed lock and **not** a general transactional
compare-and-swap guarantee. No locking framework was introduced. Full
qualification in the contract document §13.

### Retention deferral

```
E3 v0.1 COLLECTION DELETION      = NONE
COLLECTION RETENTION / GC POLICY = DEFERRED
```

No function in this package calls `delete_collection`. Necessary for rollback
to remain truthful. Full law in the contract document §14.

### Embedding execution binding qualification

```
EMBEDDING EXECUTION BINDING = DECLARED_ONLY
```

Passing an embedder object is not independent proof the declared model
revision executed; a declared `implementation_revision` is not a measurement
of actual implementation execution. No runtime/model identity is inferred or
invented. Full qualification in the contract document §7.

### Qdrant server-version qualification

```
qdrant/qdrant:latest        = IMAGE TAG, not a server semantic-version claim
QDRANT SERVER SEMANTIC VERSION = UNBOUND (not independently measured during E3D/E3E)
```

## 4. Tests and regression

```
TARGETED E3D TESTS = 76 PASS / 0 FAIL

  models                    31 PASS
  materialize / measurement 15 PASS
  verify                    13 PASS
  activation / rollback     17 PASS

BOUNDED PYTEST REGRESSION BASELINE   = 1305 PASS / 33 FAIL / 7 SKIP
BOUNDED PYTEST REGRESSION POST-E3D   = 1381 PASS / 33 FAIL / 7 SKIP

DELTA               = +76 PASS / ±0 FAIL / ±0 SKIP
FAILURE SET DELTA   = NONE
NEW E3 REGRESSION   = NOT SUPPORTED
```

The 76 targeted E3D tests were re-run fresh at E3E and confirmed 76 PASS / 0
FAIL again, independent of the E3D-time measurement.

```
FULL STDLIB RUNNER = BLOCKED BY PRE-EXISTING COLLECTION-SURFACE CONDITIONS
```

Observed blockers are associated with already-preserved qualification
surfaces: an `ION_REPO_ROOT` environment-variable requirement in one unrelated
test module, and a missing `source_provenance_manifest` module referenced by
another unrelated test module in this isolated worktree. Neither import path
touches `derived_index_lifecycle`. Classification: **pre-existing / non-E3D.**
No claim of "stdlib full suite pass" is made. No claim that E3D caused either
blocker is made. The E3D targeted pytest surface itself is 76 PASS, measured
independently of the stdlib runner's condition.

## 5. Q1 / Q2 / Q3 — preserved, not repaired

```
Q1 = Overlay-dependent collection blocker.        Pre-existing / non-E3.
Q2 = 33 pre-existing CRLF byte-identity failures.  Failure set delta = NONE. Non-E3.
Q3 = ION_REPO_ROOT environment requirement.
```

Four main-worktree overlay files remain **not admitted, not read, untouched,
non-E3.** No repair of Q1/Q2/Q3 was performed or attempted.

## 6. Protected surfaces

```
QDRANT_STORE MODIFICATION = NONE   (backend/app/modules/retrieval/qdrant_store.py unchanged)
RETRIEVALPORT              = UNCHANGED
CORE                        = UNCHANGED
container.py                = UNCHANGED
config.py                    = UNCHANGED
E2.1 (content_pack)          = UNCHANGED
E2.2 (content_engine)        = UNCHANGED
E2.3 (derived_index)         = UNCHANGED
```

## 7. Final E3 file set — exactly twelve files

| # | Path |
|---|---|
| 1 | `backend/app/modules/derived_index_lifecycle/__init__.py` |
| 2 | `backend/app/modules/derived_index_lifecycle/models.py` |
| 3 | `backend/app/modules/derived_index_lifecycle/identity.py` |
| 4 | `backend/app/modules/derived_index_lifecycle/materialize.py` |
| 5 | `backend/app/modules/derived_index_lifecycle/verify.py` |
| 6 | `backend/app/modules/derived_index_lifecycle/activation.py` |
| 7 | `backend/tests/test_derived_index_lifecycle_models_v0_1.py` |
| 8 | `backend/tests/test_derived_index_lifecycle_materialize_v0_1.py` |
| 9 | `backend/tests/test_derived_index_lifecycle_verify_v0_1.py` |
| 10 | `backend/tests/test_derived_index_lifecycle_activation_v0_1.py` |
| 11 | `docs/ION_E3_DERIVED_INDEX_LIFECYCLE_CONTRACT_v1.md` |
| 12 | `docs/ION_E3_DERIVED_INDEX_LIFECYCLE_CLOSURE_2026-09-03.md` |

Exact path / byte-count / SHA-256 for each of these twelve files is recorded
in the E3E final materialization report (measured after this document was
written, since this file's own bytes are part of the twelve).

## 8. Final repository state

```
HEAD                       = e92fa8bc96bf29c659f72c824a88859bd21985d7
TRACKED DIFF                = NONE
STAGED                       = NONE
UNTRACKED NON-IGNORED         = exactly the twelve files listed in §7
PROTECTED EXISTING FILES       = UNCHANGED
REAL QDRANT MUTATION             = NONE during E3D or E3E
COMMIT                             = NONE
PUSH                                 = NONE
E4                                     = NOT ENTERED
```

## 9. Disposition

```
E3E CLOSURE MATERIALIZATION = PASS
E3 IMPLEMENTATION           = PASS
E3 VERIFICATION             = PASS
E3                          = READY FOR EXACT COMMIT AUTHORIZATION
```

No staging, commit, or push was performed as part of E3D or E3E. E4 was not
entered.
