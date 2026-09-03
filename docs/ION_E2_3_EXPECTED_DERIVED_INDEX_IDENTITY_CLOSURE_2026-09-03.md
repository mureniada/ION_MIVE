# ION E2.3 — Expected Derived Index Identity — Closure Receipt

**Date:** 2026-09-03
**Type:** Bounded-phase closure receipt
**Phase:** E2.3 — Expected Derived Index Identity
**Contract:** `docs/ION_E2_3_EXPECTED_DERIVED_INDEX_IDENTITY_CONTRACT_v1.md`

This receipt records measured facts and operator decisions. It authorizes
nothing, closes no other issue, and rewrites no historical project-control
record.

---

## 1. Starting state

```
WORKTREE ROOT = .../ION_MIVE_CLEANROOM_PACK_v1/.claude/worktrees/e2-worktree-preflight-f4c803
BRANCH        = claude/e2-worktree-preflight-f4c803
STARTING HEAD = bbb226ccf10729a8cbdbb2d2456824f67fa100a7   ("E2.2: bind durable closure")
LOCAL REF     = e2-2-minimal-content-engine-20260903 -> bbb226c...

STATE AT START:  TRACKED DIFF = NONE   STAGED = NONE   UNTRACKED = NONE
```

Ancestry:

```
7cf6ba5 (E1 closure) -> 1aad954 (E2.1 impl) -> a640dfa (E2.1 closure)
  -> 3f7926d (E2.2 impl) -> bbb226c (E2.2 closure)
```

---

## 2. E2.3 file set — five files, all newly created

```
backend/app/modules/derived_index/__init__.py
backend/app/modules/derived_index/identity.py
backend/app/modules/derived_index/models.py
backend/tests/test_derived_index_models_v0_1.py
backend/tests/test_derived_index_identity_v0_1.py
```

No other production or test file was created, modified, moved or deleted. Exact
byte counts and SHA-256 digests for these five, together with this receipt and
the contract document, are recorded in the E2.3D final report.

No fourth production file was needed: `identity.py` operates on plain mappings,
so `models` imports `identity` one-way with no cycle and no purity blocker.

---

## 3. E2.3A findings material to this boundary

The read-only reality check established, and this phase did not repair:

```
PACK IDENTITY IN QDRANT PAYLOAD    = ABSENT at every stage
                                     (record, payload, point, collection, Evidence)
COLLECTION NAME                    = CONFIGURATION, encoding nothing
POINT ID                           = uuid5(fixed namespace, document_id);
                                     independent of collection and embedding
CURRENT QDRANT REBUILD             = DESTRUCTIVE (drop + recreate the live collection)
BUILD / ACTIVATION SEPARATION      = NONE (writing is activating)
CURRENT WRITE TARGET               = configured ACTIVE collection
EMBEDDING MODEL VERSION DURABLY BOUND = NO
                                     (no lock file; model name carries no revision)
EMBEDDING CONFIGURATION EXPLICITLY IDENTIFIABLE = PARTIAL
INDEX COMPLETENESS SUPPORT         = PARTIAL at best; stale-point and
                                     unexpected-point detection = NO
NO index / collection / embedding / build fingerprint exists anywhere
```

The lexical `LexicalIndex.fingerprint()` was NOT promoted; the repository's own
`test_d4_t21_lexical_index_fingerprint_not_silently_promoted` forbids exactly
that, and this phase respected it.

---

## 4. Architecture decision

```
OPTION C INPUTS  + OPTION E LONG-TERM SHAPE
EXPECTED HALF ONLY implemented in E2.3
```

```
ContentBuildResult + EmbeddingProfile + VectorSchema
  -> ExpectedDerivedIndexDescriptor -> derived_index_fingerprint -> STOP
```

Option A (identity over the build result alone) was rejected on evidence: it
omits embedding and schema, and `provenance_created_at` would move the identity
for a reason that cannot affect retrieval. Option D (identity measured from
materialized points) was deferred to E3 because it requires a live store.

```
E2.3 = EXPECTED DERIVED INDEX IDENTITY ONLY
E3   = MEASURED MATERIALIZED INDEX IDENTITY + VERIFY + ACTIVATE + ROLLBACK
```

---

## 5. Exact identity payload — eleven top-level fields

```
derived_index_contract_version
pack_id
pack_version
pack_canonical_fingerprint
content_engine_contract_version
content_engine_version
chunk_chars
overlap
record_set
embedding_profile
vector_schema
```

`derived_index_fingerprint` is not inside its own payload. No twelfth top-level
field was added for `implementation_revision`.

Record set: exactly `document_id` + `evidence_fingerprint` per record,
canonically ordered by `document_id`, duplicates fail closed, insertion order not
identity-bearing.

Canonicalization: `t4.jcs.serialize` reused under E2.1's bounded precedent
(`CANONICALIZATION_PROFILE_ID = "ION_JCS_V0_1"`), digest SHA-256 over exactly
those bytes. No new canonicalizer, no new conformance claim.

Construction: `create(...)` measures the fingerprint and exposes no fingerprint
parameter; `__post_init__` recomputes and requires exact equality on every path.

---

## 6. Exact EmbeddingProfile and VectorSchema surfaces

```
EmbeddingProfile: backend, model_name, model_revision, implementation_revision,
                  dimension, normalization_profile
VectorSchema:     dimension, distance_metric, vector_name

SUPPORTED_BACKENDS               = ("fake", "local", "openai")
MODEL_BACKED_BACKENDS            = {"local", "openai"}
SUPPORTED_NORMALIZATION_PROFILES = ("L2_NORMALIZED_BY_ADAPTER",
                                    "PROVIDER_SUPPLIED_UNVERIFIED")
SUPPORTED_DISTANCE_METRICS       = ("COSINE",)
FORBIDDEN_REVISION_PLACEHOLDERS  = {"current", "default", "latest", "none",
                                    "null", "unknown", "unpinned", "unresolved"}
```

`EmbeddingProfile.dimension == VectorSchema.dimension` is required; mismatch
fails closed. `vector_name = None` explicitly represents the unnamed
single-vector state Qdrant is configured with today; named and unnamed produce
different identities.

The normalization vocabulary reflects only observed adapter behaviour:
`HashingEmbedder` and `LocalEmbedder` normalize in the adapter; the OpenAI
adapter returns provider vectors untouched and this repository proves nothing
about their normalization.

---

## 7. Provenance-time exclusion

```
provenance_created_at = EXCLUDED FROM DERIVED INDEX IDENTITY
```

Operator ruling accepted and implemented: it changes provenance-materialization
metadata but not content, chunk identity, embedding input or output, dimension,
distance semantics or ranking. Proved: identical index-relevant inputs differing
only in `provenance_created_at` produce the same fingerprint, and the string does
not appear in the canonical bytes. `ContentBuildResult` was not modified.

---

## 8. Implementation-revision correction (E2.3C)

One field was added after the first implementation, on operator ruling:

```
EmbeddingProfile.implementation_revision = REQUIRED FOR ALL BACKENDS
                                           explicit / immutable / non-placeholder
                                           no default, never inferred
```

```
EMBEDDING BACKEND != EMBEDDING IMPLEMENTATION REVISION
MODEL REVISION    != EMBEDDING IMPLEMENTATION REVISION
MODEL IDENTITY    != ADAPTER / ALGORITHM IDENTITY
```

It sits inside the `embedding_profile` projection, not as a twelfth top-level
field. Nothing infers it — no Git, filesystem, package-manager or environment
lookup exists in the package, asserted structurally.

The `fake` backend, stated unambiguously:

```
FAKE BACKEND MODEL ARTIFACT          = NONE
FAKE BACKEND model_name              = NONE / NOT APPLICABLE
FAKE BACKEND model_revision          = NONE / NOT APPLICABLE
FAKE BACKEND implementation_revision = EXPLICIT / IMMUTABLE / REQUIRED
```

It has no external model artifact and is refused if it claims one, but its
algorithm can change vector output, so its implementation identity stays
explicit. This closed the gap where a changed `HashingEmbedder` could otherwise
have retained the same expected index identity.

---

## 9. Default-local eligibility qualification

```
CURRENT DEFAULT LOCAL EMBEDDING CONFIGURATION = NOT YET CANONICAL-DESCRIPTOR-ELIGIBLE
```

The model name exists; no immutable `model_revision` is durably bound by current
repository configuration (no lock file, no revision in `EMBEDDING_MODEL`, no
`revision=` at load), and an explicit `implementation_revision` is additionally
required.

```
CLASSIFICATION = QUALIFICATION / FAIL-CLOSED ELIGIBILITY CONDITION
NOT            = E2.3 implementation failure
```

Nothing about the embedding runtime, dependencies, lock files, Dockerfile,
configuration or provider behaviour was modified. This is the same unpinned-model
gap R-001 recorded; no identity scheme can close it alone.

---

## 10. Expected versus measured boundary

```
ExpectedDerivedIndexDescriptor = DECLARED EXPECTED INDEX IDENTITY
```

It does not prove that Qdrant exists, that the collection exists, that all
records were embedded, that all points were written, that no stale points exist,
that the point count matches, that the live schema matches, that the declared
model revision was loaded, that the declared implementation revision was
executed, that the vectors correspond to the declarations, that the index is
verified, or that the index is active.

```
EXPECTED IDENTITY != MEASURED STORE STATE
EXPECTED PROFILE  != PROVEN RUNTIME PROFILE
DECLARED PROVIDER IDENTITY != MEASURED PROVIDER EXECUTION
```

E3 owns every one of those.

---

## 11. Verification record

```
TARGETED E2.3 TESTS           = 39 PASS / 0 FAIL
STDLIB-RUNNER STYLE           = 39 RUN  / 0 FAIL
BOUNDED REGRESSION BASELINE   = 1266 PASS / 33 FAIL / 7 SKIP
BOUNDED REGRESSION POST-E2.3C = 1305 PASS / 33 FAIL / 7 SKIP
DELTA                         = +39 PASS / +/-0 FAIL / +/-0 SKIP
FAILURE SET DELTA             = NONE
NEW E2.3 REGRESSION           = NOT SUPPORTED
PROTECTED SURFACE CHANGE      = NONE
```

Commands, run from `backend/` with `ION_REPO_ROOT` set identically in baseline
and post-change runs:

```
python -m pytest tests/test_derived_index_models_v0_1.py \
                 tests/test_derived_index_identity_v0_1.py -q --tb=short

python -m pytest -q --tb=no \
  --ignore=tests/test_production_canonical_materialization_wiring_v0_1.py
```

Failure-set identity was established by name, not by count: both `FAILED` line
sets were sorted and compared, and the comparison returned no differences.

Proof coverage: nineteen model proofs, nineteen identity proofs, and the E2.3C
correction proofs. Purity is proved by mechanism — an import allowlist and source
scan over the package (no store, embedder, `os`/`io`/`pathlib`, socket, clock,
UUID or randomness), plus `builtins.open` and `io.open` replaced by a raiser
during computation. The entire E2.3 test surface touches no filesystem, which is
itself evidence that expected identity is computable from declarations alone.

Two tests were corrected during implementation and the reason is recorded: they
originally tried to feed invalid pack and engine identity through a real
`ContentBuildResult`, which already refuses it — E2.2 doing its job. Both now
prove the descriptor's own refusal against direct construction.

---

## 12. Preserved qualifications — recorded, not repaired

```
Q1 = OVERLAY-DEPENDENT COLLECTION BLOCKER
     PRE-EXISTING / NON-E2.3 / REPAIR NOT AUTHORIZED

Q2 = 33 CRLF BYTE-IDENTITY FAILURES
     PRE-EXISTING / NON-E2.3 / FAILURE SET DELTA = NONE / REPAIR NOT AUTHORIZED

Q3 = ION_REPO_ROOT ENVIRONMENT REQUIREMENT
     REPOSITORY MUTATION = NONE
```

The four pre-existing main-worktree overlay files —
`backend/app/modules/admission/receipts.py`,
`backend/app/modules/retrieval/source_provenance_manifest.py`,
`backend/t4/contract/STATUS.md`, `schemas/ion_evidence_record_v0.1.schema.json` —
remain **NOT ADMITTED / NOT READ / UNTOUCHED / NON-E2.3**.

---

## 13. Protected surfaces

```
TRACKED DIFF = NONE      STAGED = NONE
```

A tracked diff of NONE is the proof of non-mutation:

```
backend/app/modules/content_pack/*          backend/t4/*
backend/app/modules/content_engine/*        backend/app/ingest_cli.py
backend/app/modules/retrieval/*             Core / RetrievalPort
backend/app/modules/local_layer/*           Session / TurnRecord / Adaptive Dialogue
backend/app/modules/evidence_provenance/*   GovernedEvidenceSet
ModelContext / ModelGateway                 Execution Profile
Qdrant semantics                            schemas/*

PROTECTED SURFACE CHANGE REQUIRED = NONE
QDRANT ACCESS                     = NONE
ACTIVATION                        = NONE
```

Every reuse was a read-only import.

---

## 14. Repository movement

```
FILES MODIFIED (tracked)  = NONE
FILES CREATED (untracked) = SEVEN (five implementation/test + two documents)
STAGED                    = NONE
COMMIT                    = NONE
PUSH                      = NONE
BRANCH MOVEMENT           = NONE
HEAD                      = bbb226ccf10729a8cbdbb2d2456824f67fa100a7 (unchanged)
```

---

## 15. Status

```
E2.3 IMPLEMENTATION = PASS
E2.3 VERIFICATION   = PASS
E2.3                = READY FOR EXACT COMMIT AUTHORIZATION

E3 = NOT STARTED / NOT AUTHORIZED
```
