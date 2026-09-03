# ION E2.1 — Canonical Content Pack Identity — Closure Receipt

**Date:** 2026-09-03
**Type:** Bounded-phase closure receipt
**Phase:** E2.1 — Canonical Generic Content Pack Identity
**Contract:** `docs/ION_E2_1_CANONICAL_CONTENT_PACK_IDENTITY_CONTRACT_v1.md`

This receipt records measured facts and operator decisions. It authorizes
nothing, closes no other issue, and rewrites no historical project-control
record.

---

## 1. Namespace note

```
REPO-HANDOVER:E1     = Thin-client compliance          (repository-local historical)
PROJECT-CONTROL:E1   = Minimal Adaptive Dialogue Runtime Closure (external)
PROJECT-CONTROL:E2.1 = Canonical Generic Content Pack Identity
```

These are distinct namespaces. No repository-local historical record was
rewritten to synchronize external project-control vocabulary.

---

## 2. Starting state

```
WORKTREE ROOT = C:/Users/murenia/Documents/Projects/ION_ON/ION_MIVE_CLEANROOM_PACK_v1/.claude/worktrees/e2-worktree-preflight-f4c803
GIT DIR       = .../ION_MIVE_CLEANROOM_PACK_v1/.git/worktrees/e2-worktree-preflight-f4c803
COMMON DIR    = .../ION_MIVE_CLEANROOM_PACK_v1/.git
BRANCH        = claude/e2-worktree-preflight-f4c803   (attached)
STARTING HEAD = 7cf6ba52557dd92c3f4c96a7edbdfbe9ade4d169
HEAD COMMIT   = "E1: bind durable closure", 2026-09-03 09:02:28 +0200
SOURCE REF    = e1-adaptive-dialogue-runtime-20260903 -> 7cf6ba52557dd92c3f4c96a7edbdfbe9ade4d169

STATE AT START:  TRACKED DIFF = NONE   STAGED DIFF = NONE   UNTRACKED = NONE
```

A separately selected empty directory named `ION_MIVE_E2_WORKTREE_20260903` was
established in preflight as **not** a Git worktree; it was left untouched and is
not this phase's surface.

---

## 3. E2.1 file set — five files, all newly created

```
backend/app/modules/content_pack/__init__.py
backend/app/modules/content_pack/models.py
backend/app/modules/content_pack/identity.py
backend/tests/test_content_pack_models_v0_1.py
backend/tests/test_content_pack_identity_v0_1.py
```

No other production or test file was created, modified, moved or deleted. The
exact byte counts and SHA-256 digests of these files, together with this receipt
and the contract document, are recorded in the E2.1C final report.

---

## 4. Precondition — bound serializer verified before use

```
COMMAND (from backend/):
  python -m pytest tests/test_t4_jcs.py tests/test_t4_rfc8785_conformance.py -q

RESULT: 24 passed, exit code 0
```

Ruling applied: the bound serializer passed, therefore `backend/t4/jcs.py` was
reused **unmodified**. No repair was attempted and none was needed.

Observation recorded without action: the docstring of `backend/t4/jcs.py` states
it is not verified against an authoritative RFC 8785 vector. That statement is
stale — `backend/t4/vectors/rfc8785.txt` is pinned by SHA-256 and the
conformance test above exercises the RFC's own vectors against it. Correcting
that docstring would be a protected-file edit and was **not** made.

---

## 5. Targeted E2.1 tests

```
COMMAND (from backend/):
  python -m pytest tests/test_content_pack_models_v0_1.py \
                   tests/test_content_pack_identity_v0_1.py -q --tb=short

RESULT: 30 passed, exit code 0
```

Second runner, since this repository's tests must run under both `pytest` and
the stdlib `run_tests.py`:

```
COMMAND: stdlib-runner-style discovery (importlib over the two modules,
         calling every callable named test_*)
RESULT:  ran 30 test functions, 0 failures, exit code 0
```

Both test modules consist of plain functions, every one decorated with
`netguard`'s `@guarded`: cloud SDK imports denied, outbound sockets denied,
cloud credentials absent for the duration of every test.

---

## 6. Acceptance invariants — 20 of 20 proved

| # | Invariant | Proving test |
|---|---|---|
| 1 | empty `pack_id` rejected | `test_i1_empty_pack_id_is_rejected` |
| 2 | empty `pack_version` rejected | `test_i2_empty_pack_version_is_rejected` |
| 3 | unsupported `contract_version` rejected | `test_i3_unsupported_contract_version_is_rejected` |
| 4 | empty source inventory rejected | `test_i4_empty_source_inventory_is_rejected` |
| 5 | duplicate `source_id` rejected | `test_i5_duplicate_source_id_is_rejected` |
| 6 | invalid / empty `source_id` rejected | `test_i6_invalid_or_empty_source_id_is_rejected` |
| 7 | `source_id = "unknown"` rejected | `test_i7_source_id_unknown_is_rejected` |
| 8 | empty `source_version` rejected | `test_i8_empty_source_version_is_rejected` |
| 9 | `source_sha256` must be exact valid SHA-256 hex | `test_i9_source_sha256_must_be_exact_valid_sha256_hex` |
| 10 | input ordering does not alter the fingerprint | `test_i10_input_source_ordering_does_not_alter_the_fingerprint` |
| 11 | canonical source ordering is stable | `test_i11_canonical_source_ordering_is_stable_and_lexicographic_by_source_id` |
| 12 | any `source_sha256` change alters the fingerprint | `test_i12_any_source_sha256_change_alters_the_fingerprint` |
| 13 | `source_id` change alters the fingerprint | `test_i13_source_id_change_alters_the_fingerprint` |
| 14 | `source_version` change alters the fingerprint | `test_i14_source_version_change_alters_the_fingerprint` |
| 15 | `pack_id` change alters the fingerprint | `test_i15_pack_id_change_alters_the_fingerprint` |
| 16 | `pack_version` change alters the fingerprint | `test_i16_pack_version_change_alters_the_fingerprint` |
| 17 | fingerprint recomputation is deterministic | `test_i17_canonical_fingerprint_recomputation_is_deterministic` |
| 18 | supplied fingerprint mismatch fails closed | `test_i18_supplied_fingerprint_mismatch_fails_closed` |
| 19 | no Qdrant import or runtime dependency | `test_i19_no_qdrant_or_cloud_sdk_is_imported_or_required` + `test_i19_the_package_source_reaches_no_store_network_or_product_module` |
| 20 | no filesystem or network access during identity calculation | `test_i20_no_filesystem_access_occurs_during_identity_calculation` (under `@guarded`) |

Supporting evidence beyond the required twenty: payload closure asserted over
the serialized bytes (twelve foreign terms asserted absent); the `t4.jcs`
binding asserted byte-for-byte; declared field sets asserted exhaustive; both
objects asserted frozen; `create` asserted to expose no `canonical_fingerprint`
parameter; one `pack_id` + `pack_version` asserted unable to stand over two
different contents.

Invariant 10 is proved over all six permutations of a three-source inventory,
through both the identity function and the contract object. Invariant 17 is
proved over 25 recomputations plus independent re-derivation of the digest from
the canonical bytes alone.

---

## 7. Bounded regression

All runs from `backend/`, with `ION_REPO_ROOT` set to the worktree root
identically in every run (see Q3).

```
BASELINE (captured before any file was created)
  python -m pytest -q --tb=line \
    --ignore=tests/test_production_canonical_materialization_wiring_v0_1.py
  -> 1189 passed, 33 failed, 7 skipped

POST-E2.1
  python -m pytest -q --tb=no \
    --ignore=tests/test_production_canonical_materialization_wiring_v0_1.py
  -> 1219 passed, 33 failed, 7 skipped

DELTA = +30 passed, +/-0 failed, +/-0 skipped
```

Failure-set identity was established by name, not by count alone: the baseline
was re-derived after implementation by additionally ignoring the two new test
modules, both `FAILED` line sets were sorted and compared, and the comparison
returned no differences.

```
FAILURE SET DELTA    = NONE (33 vs 33, identical by name)
NEW E2.1 REGRESSION  = NOT SUPPORTED
```

---

## 8. Qualified pre-existing conditions — recorded, not repaired

### Q1 — overlay-dependent collection blocker

`backend/tests/test_production_canonical_materialization_wiring_v0_1.py:28`
imports `app.modules.retrieval.source_provenance_manifest`, which is absent from
this worktree — it exists only as pre-existing untracked overlay in the main
checkout. Collection of the full suite fails without excluding that module.

```
PRE-EXISTING          = YES
NON-E2.1              = YES
E2.1 CAUSATION        = NOT SUPPORTED
REPAIR                = NOT AUTHORIZED
```

### Q2 — CRLF byte-identity failures

33 regression failures are present both before and after E2.1. Measured cause:
`core.autocrlf=true` in this checkout while `.gitattributes` pins `eol=lf` only
for `/.gitattributes`, `/backend/t4/**` and `/rfc8785.txt`. Example:
`backend/app/modules/retrieval/qdrant_store.py` is 7,106 bytes on disk against a
6,918-byte blob, carrying 188 CRLF pairs. Every failure in the set is a
byte-identity or file-SHA-256 assertion.

```
PRE-EXISTING          = YES
NON-E2.1              = YES
FAILURE SET DELTA     = NONE
E2.1 CAUSATION        = NOT SUPPORTED
REPAIR                = NOT AUTHORIZED
```

The E2.1 files are structurally immune to this condition: they digest strings
constructed in memory, never file bytes.

### Q3 — ION_REPO_ROOT

`backend/tests/test_orchestrator_admission_gate.py:31` requires the environment
variable `ION_REPO_ROOT`. It was supplied identically in the baseline and
post-change runs.

```
REPOSITORY MUTATION = NONE
```

---

## 9. T4 dependency ruling

```
app.modules.content_pack.identity -> t4.jcs.serialize
  = ACCEPTED, BOUNDED CANONICALIZATION DEPENDENCY ONLY

t4 -> app = PROHIBITED / UNCHANGED
GENERAL app -> t4 COUPLING = NOT AUTHORIZED
```

Content Pack gains no authority over and no dependency on `t4.manifest`,
`t4.identity`, `t4.emitter`, T4 run records, T4 execution semantics or T4
artifact roles. `backend/t4/*` was not modified.

Supporting facts measured during the phase: before E2.1 only `backend/tests/`
imported `t4`, so this is the first `app -> t4` import in the repository;
`backend/tests/test_t4_isolation.py` constrains only the reverse direction
(`t4` importing `app`) and continues to pass; and `backend/Dockerfile:14`
(`COPY backend/ ./` with `WORKDIR /app`) places `t4` in the runtime image, so
the import resolves in production as well as under test.

---

## 10. Protected surfaces

```
TRACKED DIFF = NONE
STAGED DIFF  = NONE
```

A tracked diff of NONE is the proof of non-mutation for every protected surface:

```
backend/t4/*                      UNCHANGED
backend/app/modules/local_layer/* UNCHANGED
backend/app/modules/retrieval/*   UNCHANGED
backend/app/modules/evidence_provenance/*  UNCHANGED
Core.ask()                        UNCHANGED
RetrievalPort                     UNCHANGED
Qdrant / qdrant_store             UNCHANGED
GovernedEvidenceSet               UNCHANGED
ModelContext / ModelGateway       UNCHANGED
Execution Profile                 UNCHANGED
Session / SessionTurnEntry        UNCHANGED
TurnRecord                        UNCHANGED
Adaptive Dialogue                 UNCHANGED
Context Pack / schemas/           UNCHANGED

PROTECTED SURFACE CHANGE REQUIRED = NONE
```

Existing protected modules were read as precedent only. No schema file, CLI,
ingestion path, persistence layer, adapter or scanner was created or changed.

---

## 11. Pre-existing main-worktree overlay

The four files existing only as pre-existing untracked overlay in the main
checkout remain absent here and were not read as implementation inputs, not
copied, and not promoted:

```
backend/app/modules/admission/receipts.py
backend/app/modules/retrieval/source_provenance_manifest.py
backend/t4/contract/STATUS.md
schemas/ion_evidence_record_v0.1.schema.json

PRE-EXISTING NON-E2 OVERLAY
NOT ADMITTED INTO E2
NOT AUTHORITATIVE FOR E2 IMPLEMENTATION
```

---

## 12. Non-goals honoured

```
Content Engine            NOT CREATED
Registry adapter          NOT CREATED
Directory scanner         NOT CREATED
Ingest CLI change         NONE
Source emitter            NOT CREATED
Schema file               NOT CREATED
Persistence               NOT CREATED
Qdrant coupling           NONE
Chunk lineage             NOT ESTABLISHED
Derived-index identity    NOT ESTABLISHED
Activation                NOT CREATED
Cassette implementation   NOT CREATED
Dialogue Profile          NOT CREATED
```

The ION Cassette Standard remains an architecture horizon only. No Cassette
code, contract or field was created, named or reserved.

---

## 13. Repository movement

```
FILES MODIFIED (tracked)  = NONE
FILES CREATED (untracked) = SEVEN (five implementation/test + two documents)
STAGED                    = NONE
COMMIT                    = NONE
PUSH                      = NONE
BRANCH MOVEMENT           = NONE
HEAD                      = 7cf6ba52557dd92c3f4c96a7edbdfbe9ade4d169 (unchanged)
```

---

## 14. Status

```
E2.1 IMPLEMENTATION = PASS
E2.1 VERIFICATION   = PASS
E2.1                = READY FOR EXACT COMMIT AUTHORIZATION

E2.2 = NOT STARTED / NOT AUTHORIZED
E2.3 = NOT STARTED / NOT AUTHORIZED
```

E2.2 was not entered. No derived lineage — source to chunk to embedding to
Qdrant point — was designed, implemented, stubbed or reserved during this phase.
