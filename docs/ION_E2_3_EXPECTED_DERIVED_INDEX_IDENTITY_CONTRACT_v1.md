# ION E2.3 — Expected Derived Index Identity Contract v1

**Date:** 2026-09-03
**Type:** Implemented contract record
**Status:** BOUND TO THE IMPLEMENTATION CREATED UNDER E2.3
**Scope:** Expected (declared) derived-index identity only. This document states
what the E2.3 code actually does. It authorizes nothing further.

Every constant, field name, signature and literal below was read out of the
final implementation, not composed for this document.

---

## 1. What this is, and is not

E2.3 answers:

> "What derived retrieval/index state do we EXPECT to result from this exact
> Content Pack, build, embedding profile and vector schema?"

It does not answer:

> "What is actually stored in Qdrant right now?"

```
E2.3 = EXPECTED DERIVED INDEX IDENTITY ONLY
E3   = MEASURED MATERIALIZED INDEX IDENTITY + VERIFY + ACTIVATE + ROLLBACK
```

Boundaries kept:

```
EXPECTED IDENTITY    != MEASURED STORE STATE
DECLARED EXPECTATION != MEASURED STORE STATE
EXPECTED IDENTITY    != VERIFICATION RECEIPT
CONTENT BUILD RESULT != INDEX IDENTITY
PACK IDENTITY        != INDEX IDENTITY
COLLECTION NAME      != CANONICAL DERIVED INDEX IDENTITY
EXPECTED PROFILE     != PROVEN RUNTIME PROFILE
BUILD                != VERIFY != ACTIVATE
```

Flow:

```
ContentBuildResult + EmbeddingProfile + VectorSchema
        -> ExpectedDerivedIndexDescriptor
        -> derived_index_fingerprint
        -> STOP
```

---

## 2. Implemented constants

```
DERIVED_INDEX_CONTRACT_ID       = "ION_DERIVED_INDEX_V0_1"
DERIVED_INDEX_CONTRACT_VERSION  = "0.1"
SUPPORTED_CONTRACT_VERSIONS     = ("0.1",)

CANONICALIZATION_PROFILE        = "ION_DERIVED_INDEX_CANONICALIZATION_PROFILE_V0_1"
CANONICALIZATION_PROFILE_ID     = "ION_JCS_V0_1"
CANONICALIZATION_IMPLEMENTATION = "t4.jcs.serialize"
FINGERPRINT_ALGORITHM           = "SHA256"

SUPPORTED_BACKENDS              = ("fake", "local", "openai")
MODEL_BACKED_BACKENDS           = {"local", "openai"}
FORBIDDEN_REVISION_PLACEHOLDERS = {"current", "default", "latest", "none", "null",
                                   "unknown", "unpinned", "unresolved"}
SUPPORTED_NORMALIZATION_PROFILES = ("L2_NORMALIZED_BY_ADAPTER",
                                    "PROVIDER_SUPPLIED_UNVERIFIED")
SUPPORTED_DISTANCE_METRICS      = ("COSINE",)
```

Errors are module-local: `DerivedIndexError(ValueError)` (models) and
`DerivedIndexIdentityError(ValueError)` (identity). Neither introduces a
transport stage nor maps onto the core error taxonomy.

---

## 3. Implemented API

```
ExpectedDerivedIndexDescriptor.create(
    content_build_result,
    embedding_profile,
    vector_schema,
    *,
    derived_index_contract_version: str = "0.1",
) -> ExpectedDerivedIndexDescriptor
```

`pack_id`, `pack_version`, `pack_canonical_fingerprint`,
`content_engine_contract_version`, `content_engine_version`, `chunk_chars` and
`overlap` are read from `content_build_result`. There is no parameter through
which a caller could restate a conflicting pack, engine or chunk identity, and
no `derived_index_fingerprint` parameter at all.

Supporting identity functions: `canonical_record_set`, `canonical_payload`,
`canonical_bytes`, `compute_derived_index_fingerprint`.

---

## 4. Canonical identity payload — exactly eleven top-level fields

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

`derived_index_fingerprint` is **not** included in its own payload. No twelfth
top-level field was added for `implementation_revision`: it lives inside the
`embedding_profile` projection.

---

## 5. Pack and engine identity

Carried verbatim from `ContentBuildResult`, never recomputed:
`pack_id`, `pack_version`, `pack_canonical_fingerprint`,
`content_engine_contract_version`, `content_engine_version`, `chunk_chars`,
`overlap`. All participate in the fingerprint.

```
provenance_created_at = NOT AN INDEX IDENTITY INPUT
```

---

## 6. Record-set identity

Each record contributes exactly two fields:

```
document_id
evidence_fingerprint
```

Canonically ordered by `document_id`. A duplicate `document_id` fails closed; an
`evidence_fingerprint` that is not 64 lowercase hexadecimal characters fails
closed; record insertion order is not identity-bearing.

The full `ContentBuildResult` record payload is **not** hashed merely because it
exists — the evidence fingerprint already binds the identity-bearing content
projection.

---

## 7. Provenance-time exclusion

```
provenance_created_at = EXCLUDED FROM DERIVED INDEX IDENTITY
```

It changes provenance-materialization metadata and nothing else: not content,
not chunk identity, not embedding input or output, not dimension, not distance
semantics, not ranking. Proved law: identical index-relevant inputs differing
only in `provenance_created_at` produce the **same** `derived_index_fingerprint`.
`ContentBuildResult` itself is unmodified — E2.3 merely excludes the field from
its identity projection.

```
BUILD PROVENANCE TIME != DERIVED INDEX IDENTITY INPUT
```

---

## 8. EmbeddingProfile

Exact implemented field set:

```
backend
model_name
model_revision
implementation_revision
dimension
normalization_profile
```

Every field is represented in the canonical embedding-profile projection and
therefore participates in expected derived-index identity. The profile is
DECLARED configuration: nothing here reads the environment, instantiates an
embedder, loads a model, or calls a provider.

---

## 9. Model-revision law

For a model-backed backend (`local`, `openai`):

```
model_name              = EXPLICIT
model_revision          = EXPLICIT / IMMUTABLE / NON-PLACEHOLDER
implementation_revision = EXPLICIT / IMMUTABLE / NON-PLACEHOLDER
```

```
MODEL NAME     != MODEL REVISION
MODEL REVISION != EMBEDDING IMPLEMENTATION REVISION
MODEL IDENTITY != ADAPTER / ALGORITHM IDENTITY
EMBEDDING BACKEND != EMBEDDING IMPLEMENTATION REVISION
```

Placeholder revisions remain fail-closed, compared case-insensitively against
`FORBIDDEN_REVISION_PLACEHOLDERS`. No revision value is ever fabricated.

For `openai`, a declared descriptor does not prove the remote provider actually
executed that model or runtime:

```
DECLARED PROVIDER IDENTITY != MEASURED PROVIDER EXECUTION
```

No provider call exists in this package.

---

## 10. The `fake` backend

```
FAKE BACKEND MODEL ARTIFACT          = NONE
FAKE BACKEND model_name              = NONE / NOT APPLICABLE
FAKE BACKEND model_revision          = NONE / NOT APPLICABLE
FAKE BACKEND implementation_revision = EXPLICIT / IMMUTABLE / REQUIRED
```

`fake` is the repository's dependency-free `HashingEmbedder`. It has no external
model artifact, so `model_name` and `model_revision` must both be `None` —
declaring absence truthfully rather than carrying an invented value, and it is
refused if it claims either. Its algorithm can nonetheless change vector output,
so its `implementation_revision` remains explicitly required.

---

## 11. Implementation-revision law

```
implementation_revision = REQUIRED FOR ALL EMBEDDING BACKENDS
```

Non-empty, whitespace-clean, explicit, immutable, non-placeholder. No default.
No Git lookup, filesystem lookup, package-manager lookup, environment lookup,
runtime inference or provider lookup: the caller declares it.

```
E2.3 ACCEPTS A DECLARATION. IT DOES NOT MEASURE RUNTIME TRUTH.
EXPECTED PROFILE != PROVEN RUNTIME PROFILE
```

---

## 12. Current default local configuration — eligibility qualification

```
CURRENT DEFAULT LOCAL EMBEDDING CONFIGURATION = NOT YET CANONICAL-DESCRIPTOR-ELIGIBLE
```

The model name exists (`sentence-transformers/all-MiniLM-L6-v2`), but no
immutable `model_revision` is durably bound by current repository configuration,
and an explicit `implementation_revision` is additionally required.

```
CLASSIFICATION = QUALIFICATION / FAIL-CLOSED ELIGIBILITY CONDITION
NOT            = E2.3 implementation failure
```

Nothing about the embedding runtime, dependencies, lock files, Dockerfile,
configuration or provider behaviour was modified.

---

## 13. VectorSchema

Exact implemented field set and values:

```
dimension        positive integer
distance_metric  one of ("COSINE",)   — the only metric this repository configures
vector_name      str | None           — None is the unnamed single-vector state
```

```
EmbeddingProfile.dimension == VectorSchema.dimension    required
mismatch = FAIL CLOSED
```

`vector_name = None` is represented explicitly and canonically as JSON `null`.
Named and unnamed are different schemas and produce different identities, as do
two different names. The distance metric participates in identity.

---

## 14. Collection name

```
QDRANT COLLECTION NAME = NOT PART OF E2.3 EXPECTED IDENTITY
COLLECTION NAME        = RUNTIME / DEPLOYMENT CONFIGURATION
COLLECTION NAME       != CANONICAL DERIVED INDEX IDENTITY
```

No collection field exists on `ExpectedDerivedIndexDescriptor`.

---

## 15. Point identity

```
QDRANT point_id = NOT AN E2.3 EXPECTED IDENTITY INPUT (v0.1)
```

Point-id generation remains a materialization concern. No call to
`point_id_for`, to Qdrant, or to the embedding runtime is part of E2.3 identity
computation.

---

## 16. Canonicalization

```
canonical payload -> t4.jcs.serialize -> canonical bytes -> SHA256 -> derived_index_fingerprint
```

`t4.jcs.serialize` is REUSED under the bounded dependency precedent E2.1
established. No new canonicalizer, and no new RFC 8785 conformance claim beyond
that existing internal profile binding (`ION_JCS_V0_1`).

---

## 17. Measure, recompute, match

```
caller-supplied unchecked fingerprint = NOT ACCEPTED
```

`create` computes the fingerprint; `__post_init__` recomputes and requires exact
equality on every construction path, including direct construction. A wrong
fingerprint fails closed. This preserves the E2.1 identity pattern:

```
MEASURED IDENTITY != UNVERIFIED DECLARATION
```

---

## 18. MUST-AFFECT identity inputs

Each of these moves `derived_index_fingerprint`, proved by test:

```
pack_id · pack_version · pack_canonical_fingerprint
content_engine_contract_version · content_engine_version
chunk_chars · overlap
record document_id · record evidence_fingerprint
embedding backend · model_name · model_revision · implementation_revision
embedding dimension · normalization_profile
vector dimension · distance_metric · vector_name (named vs unnamed, and name vs name)
```

A change to `implementation_revision` MUST move the fingerprint — proved for a
model-backed profile and separately for the model-free `fake` backend.

---

## 19. MUST-NOT-AFFECT and ABSENT

```
provenance_created_at      MUST NOT AFFECT
record insertion order     MUST NOT AFFECT

source_root                ABSENT
machine absolute path      ABSENT
source binding path        ABSENT
Qdrant collection          ABSENT
point count                ABSENT
verification state         ABSENT
activation state           ABSENT
rollback identity          ABSENT
measured index fingerprint ABSENT
```

Enforced against the descriptor field set, every model's field set, and the
serialized canonical bytes.

---

## 20. Purity and determinism

```
NO QDRANT · NO EMBEDDER CONSTRUCTION · NO PROVIDER · NO NETWORK
NO FILESYSTEM · NO CLOCK · NO UUID · NO RANDOMNESS
```

For equal identity-bearing declarations, `derived_index_fingerprint` is
deterministic. Purity is proved structurally (import allowlist, source scan, no
`open()` call) and at runtime (`builtins.open` and `io.open` replaced by a raiser
during computation, under the repository's `netguard` guard).

---

## 21. What a descriptor does NOT prove

```
ExpectedDerivedIndexDescriptor = DECLARED EXPECTED INDEX IDENTITY
```

It does not prove that Qdrant exists; that the collection exists; that all
records were embedded; that all points were written; that no stale points exist;
that the point count matches; that the live schema matches; that the declared
model revision was loaded; that the declared implementation revision was
executed; that the vectors correspond to the declarations; that the index is
verified; or that the index is active.

Those are E3 questions.

---

## 22. Store findings preserved as boundary context

Recorded by the E2.3A read-only inspection, unrepaired:

```
CURRENT QDRANT REBUILD              = DESTRUCTIVE
CURRENT BUILD / ACTIVATION SEPARATION = NONE
CURRENT WRITE TARGET                = CONFIGURED ACTIVE COLLECTION
PACK IDENTITY IN CURRENT QDRANT PAYLOAD = ABSENT
```

These explain why E3 is required. None of them was repaired under E2.3.
