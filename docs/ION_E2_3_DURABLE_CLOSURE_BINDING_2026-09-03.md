# ION E2.3 — Durable Closure Binding

**Date:** 2026-09-03
**Type:** Durable closure binding artifact
**Binds:** the already-established, already-verified E2.3 result

This artifact binds facts established in earlier phases. It establishes no new
fact, repairs nothing, claims nothing beyond E2.3, and rewrites no historical
project-control record.

---

## 1. Phase identity

```
PROJECT-CONTROL PHASE = E2.3 — EXPECTED DERIVED INDEX IDENTITY
E2.3 STATUS           = IMPLEMENTED / VERIFIED / COMMITTED
```

Namespace note: `REPO-HANDOVER:E1` (thin-client compliance, repository-local
historical) and `PROJECT-CONTROL:E1` (Minimal Adaptive Dialogue Runtime Closure,
external) remain distinct and unmodified.

---

## 2. Implementation commit

```
IMPLEMENTATION COMMIT         = dff4b0eb12dbfdeef7cf2e3508767d21cf62fbed
IMPLEMENTATION PARENT         = bbb226ccf10729a8cbdbb2d2456824f67fa100a7
IMPLEMENTATION COMMIT SUBJECT = E2.3: add expected derived index identity
IMPLEMENTATION FILE COUNT     = 7
WORKTREE                      = .../.claude/worktrees/e2-worktree-preflight-f4c803
BRANCH                        = claude/e2-worktree-preflight-f4c803
```

The parent is the E2.2 closure commit `bbb226c…` ("E2.2: bind durable closure"),
carried by the local ref `e2-2-minimal-content-engine-20260903`.

Bound committed paths:

```
backend/app/modules/derived_index/__init__.py
backend/app/modules/derived_index/identity.py
backend/app/modules/derived_index/models.py
backend/tests/test_derived_index_identity_v0_1.py
backend/tests/test_derived_index_models_v0_1.py
docs/ION_E2_3_EXPECTED_DERIVED_INDEX_IDENTITY_CLOSURE_2026-09-03.md
docs/ION_E2_3_EXPECTED_DERIVED_INDEX_IDENTITY_CONTRACT_v1.md
```

---

## 3. Bound committed blob identities

Carried verbatim from the E2.3E verified result. Not regenerated, not
recomputed, not altered.

| Path | Git blob OID | Bytes | Committed-content SHA-256 |
|---|---|---|---|
| `backend/app/modules/derived_index/__init__.py` | `bca7b15dab0371c98347d397b0d1c73f8bbc2c4e` | 3078 | `36ecdafd4c46ced3e0f5ccb63941ebe57ba709dfb6c841d5e6723da41acfe340` |
| `backend/app/modules/derived_index/identity.py` | `501e779061895b02ea87a9e68e3b8628efebd16f` | 12400 | `83b16e17f42fe7ecb82ff3730000bcbea36d774ef1a1bac74c951dc89d6672df` |
| `backend/app/modules/derived_index/models.py` | `1e16163583a2bb48d71b1f264433a6584a55d96b` | 24086 | `35e5794aa1440e51654e5b8074ededc91b15bdce99660e14278c5b7583044393` |
| `backend/tests/test_derived_index_models_v0_1.py` | `141c2ef24641cfedf4ed5bd3b49945ae2dbc56b5` | 19348 | `82b11abeac20eccd5647a8739091308068825bbc73423efd634618dfada184df` |
| `backend/tests/test_derived_index_identity_v0_1.py` | `6b4250cf3b88f6c2d88d7bd71993438d512a64a9` | 23058 | `c420e158b567d44cbfad9911bc8012cf48bbe9cc026517d06b38e051d19ff33f` |
| `docs/ION_E2_3_EXPECTED_DERIVED_INDEX_IDENTITY_CONTRACT_v1.md` | `8a16ed197b2a9ed18b0dd59e03b66d574413145e` | 12610 | `339688675847f39f0d02aac60f3eb58d910a507c0a24a661efa7b2d716ce6284` |
| `docs/ION_E2_3_EXPECTED_DERIVED_INDEX_IDENTITY_CLOSURE_2026-09-03.md` | `c4b38bac748f39ed349eb1f14c88d89ed677ae25` | 12785 | `511e78b945d31164d5d435c3b1abb249e4db2ec4d437529f8894f97b6aa1a794` |

Committed bytes and committed SHA-256 were checked against the pre-commit
worktree values and were identical for all seven files; no line-ending
conversion occurred. These blob identities are the durable content identities.

---

## 4. Bound architecture

```
E2.3 = EXPECTED DERIVED INDEX IDENTITY ONLY

ContentBuildResult + EmbeddingProfile + VectorSchema
        -> ExpectedDerivedIndexDescriptor
        -> derived_index_fingerprint

EXPECTED IDENTITY       != MEASURED STORE STATE
MEASURED INDEX IDENTITY  = NOT IMPLEMENTED / E3
QDRANT ACCESS            = NONE
VERIFY                   = NONE / E3
ACTIVATE                 = NONE / E3
ROLLBACK                 = NONE / E3
```

Full semantics: `docs/ION_E2_3_EXPECTED_DERIVED_INDEX_IDENTITY_CONTRACT_v1.md`.

---

## 5. Bound architectural laws

```
CONTENT PACK            != QDRANT
PACK IDENTITY           != INDEX IDENTITY
CONTENT BUILD RESULT    != INDEX IDENTITY
EXPECTED INDEX IDENTITY != MEASURED INDEX IDENTITY
EXPECTED PROFILE        != PROVEN RUNTIME PROFILE
MODEL NAME              != MODEL REVISION
MODEL REVISION          != EMBEDDING IMPLEMENTATION REVISION
DECLARED EXPECTATION    != MEASURED STORE STATE
BUILD                   != VERIFY != ACTIVATE
```

---

## 6. Bound identity payload — eleven top-level fields

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

```
derived_index_fingerprint = NOT INCLUDED IN ITS OWN PAYLOAD
```

---

## 7. Bound record-set identity

```
RecordDescriptor            = document_id + evidence_fingerprint
canonical order             = lexicographic by document_id
duplicate document_id       = FAIL CLOSED
invalid evidence_fingerprint = FAIL CLOSED
record insertion order      = NOT IDENTITY-BEARING
full record payload         = NOT HASHED AS INDEX IDENTITY
```

---

## 8. Bound provenance-time exclusion

```
provenance_created_at = EXCLUDED FROM DERIVED INDEX IDENTITY
changing only provenance_created_at = MUST NOT CHANGE derived_index_fingerprint
```

Reason: provenance-materialization time does not alter retrieval semantics — not
content, not chunk identity, not embedding input or output, not dimension, not
distance semantics, not ranking. `ContentBuildResult` was not modified.

---

## 9. Bound embedding profile

Exact final surface:

```
backend
model_name
model_revision
implementation_revision
dimension
normalization_profile
```

All applicable fields participate in expected index identity.

For model-backed backends (`local`, `openai`):

```
model_name              = REQUIRED
model_revision          = EXPLICIT / IMMUTABLE / REQUIRED
implementation_revision = EXPLICIT / IMMUTABLE / REQUIRED
placeholder revisions   = FAIL CLOSED
```

---

## 10. The `fake` backend

```
FAKE BACKEND MODEL ARTIFACT = NONE
model_name                  = NONE / NOT APPLICABLE
model_revision              = NONE / NOT APPLICABLE
implementation_revision     = EXPLICIT / IMMUTABLE / REQUIRED
```

`implementation_revision` is required for `fake` exactly as for every other
backend. It has no external model artifact and is refused if it claims one, but
its algorithm can change vector output, so its implementation identity stays
explicitly declared. Nothing here makes it optional.

---

## 11. Bound implementation-revision law

```
implementation_revision = REQUIRED FOR ALL BACKENDS
                          DECLARED / EXPLICIT / IMMUTABLE / NON-PLACEHOLDER
```

No runtime inference, no Git lookup, no environment lookup, no filesystem
lookup, no provider lookup. E2.3 does not prove that the declared implementation
actually executed.

---

## 12. Current default local qualification

```
CURRENT DEFAULT LOCAL EMBEDDING PROFILE = NOT CANONICAL-DESCRIPTOR-ELIGIBLE
  immutable model_revision  = NOT DURABLY BOUND
  implementation_revision   = ALSO REQUIRED

CLASSIFICATION = FAIL-CLOSED ELIGIBILITY QUALIFICATION
NOT            = E2.3 implementation failure
```

No repair authority was exercised over the embedding runtime, dependencies, lock
files, Dockerfile, configuration or provider behaviour.

---

## 13. Bound vector schema

```
dimension
distance_metric
vector_name

EmbeddingProfile.dimension == VectorSchema.dimension   required, mismatch fails closed
current supported distance metric        = COSINE
current unnamed vector representation    = vector_name = NONE
named vs unnamed state                   = IDENTITY-BEARING
Qdrant collection name                   = ABSENT FROM E2.3 IDENTITY
```

---

## 14. Bound canonicalization and fingerprint

```
canonical payload -> t4.jcs.serialize -> canonical bytes -> SHA256
  -> derived_index_fingerprint

CANONICALIZATION_PROFILE        = "ION_DERIVED_INDEX_CANONICALIZATION_PROFILE_V0_1"
CANONICALIZATION_PROFILE_ID     = "ION_JCS_V0_1"
CANONICALIZATION_IMPLEMENTATION = "t4.jcs.serialize"
FINGERPRINT_ALGORITHM           = "SHA256"
DERIVED_INDEX_CONTRACT_ID       = "ION_DERIVED_INDEX_V0_1"
DERIVED_INDEX_CONTRACT_VERSION  = "0.1"
```

No new canonicalizer and no broad RFC 8785 claim beyond E2.1's internal profile
binding. An unchecked caller-supplied fingerprint is NOT ACCEPTED;
recompute-and-match is FAIL CLOSED.

---

## 15. Bound MUST-AFFECT inputs

```
pack_id · pack_version · pack_canonical_fingerprint
content_engine_contract_version · content_engine_version
chunk_chars · overlap
record document_id · record evidence_fingerprint
embedding backend · model_name (where applicable) · model_revision (where applicable)
embedding implementation_revision · dimension · normalization_profile
vector dimension · distance_metric · vector_name / unnamed state

changing embedding implementation_revision alone = MUST CHANGE fingerprint
```

---

## 16. Bound MUST-NOT-AFFECT and ABSENT

```
provenance_created_at      MUST NOT AFFECT
record insertion order     MUST NOT AFFECT

source_root                ABSENT
absolute machine path      ABSENT
source binding path        ABSENT
Qdrant collection          ABSENT
Qdrant point id            ABSENT
actual point count         ABSENT
verification state         ABSENT
activation state           ABSENT
rollback identity          ABSENT
measured index fingerprint ABSENT
```

---

## 17. Bound purity boundary

```
NO QDRANT · NO EMBEDDER CONSTRUCTION · NO PROVIDER · NO NETWORK
NO FILESYSTEM · NO CLOCK · NO UUID · NO RANDOMNESS

ExpectedDerivedIndexDescriptor = PURE DECLARED EXPECTATION
```

It is not a store attestation. It does not prove that Qdrant exists, that the
collection exists, that records were embedded, that points were written, that no
stale points remain, that counts or schema match, that the declared model or
implementation revision was actually used, that the vectors correspond to the
declarations, that the index is verified, or that it is active.

---

## 18. Preserved store findings — E3 boundary context

```
CURRENT QDRANT REBUILD                  = DESTRUCTIVE
CURRENT BUILD / ACTIVATION SEPARATION   = NONE
CURRENT WRITE TARGET                    = CONFIGURED ACTIVE COLLECTION
PACK IDENTITY IN CURRENT QDRANT PAYLOAD = ABSENT
```

No repair in E2.3. These findings explain why E3 is required.

---

## 19. Bound verification

```
TARGETED E2.3 TESTS         = 39 PASS / 0 FAIL
STDLIB-RUNNER STYLE         = 39 RUN  / 0 FAIL
BOUNDED REGRESSION BASELINE = 1266 PASS / 33 FAIL / 7 SKIP
POST-E2.3                   = 1305 PASS / 33 FAIL / 7 SKIP
DELTA                       = +39 PASS / +/-0 FAIL / +/-0 SKIP
FAILURE SET DELTA           = NONE
NEW E2.3 REGRESSION         = NOT SUPPORTED
PROTECTED SURFACE CHANGE    = NONE
```

Failure-set identity was established by name, not by count: both `FAILED` line
sets were sorted and compared, and the comparison returned no differences.

---

## 20. Preserved qualifications

```
Q1 = OVERLAY-DEPENDENT COLLECTION BLOCKER
     PRE-EXISTING / NON-E2.3 / UNREPAIRED

Q2 = 33 CRLF BYTE-IDENTITY FAILURES
     PRE-EXISTING / NON-E2.3 / FAILURE SET DELTA = NONE / UNREPAIRED

Q3 = ION_REPO_ROOT ENVIRONMENT REQUIREMENT
     REPOSITORY MUTATION = NONE
```

The four pre-existing main-worktree overlay files —
`backend/app/modules/admission/receipts.py`,
`backend/app/modules/retrieval/source_provenance_manifest.py`,
`backend/t4/contract/STATUS.md`, `schemas/ion_evidence_record_v0.1.schema.json` —
remain **NOT ADMITTED / NOT READ / UNTOUCHED / NON-E2.3**.

---

## 21. E2.3 boundary

```
CONTENT PACK IDENTITY           = E2.1 / CLOSED
MINIMAL CONTENT ENGINE          = E2.2 / CLOSED
EXPECTED DERIVED INDEX IDENTITY = E2.3 / IMPLEMENTED
MEASURED DERIVED INDEX          = NOT IMPLEMENTED
INDEX VERIFICATION              = NOT IMPLEMENTED
ACTIVATION                      = NOT IMPLEMENTED
ROLLBACK                        = NOT IMPLEMENTED

E3 = NOT STARTED / NOT AUTHORIZED
```

No claim beyond E2.3 is made by this artifact.

---

## 22. Binding status

```
PROJECT-CONTROL:E2.3            = CLOSED / DURABLE / LOCALLY REFERENCED
EXPECTED DERIVED INDEX IDENTITY = CLOSED / VERIFIED / DURABLE
CONTENT PLANE STATE             = E2.1 + E2.2 + E2.3 CLOSED
DECLARATIVE CONTENT PLANE       = CLOSED
PUSH                            = NONE
```

The local named ref `e2-3-expected-derived-index-20260903` points at the commit
that carries this artifact. Ancestry:

```
7cf6ba52557dd92c3f4c96a7edbdfbe9ade4d169   (E1 closure)
  -> 1aad954af565b7a5b4bdb40e65edcc07b87b583a   (E2.1 implementation)
    -> a640dfa810b00044e472980bb8602ded0b2a0c6c   (E2.1 closure)
      -> 3f7926d07970b28c60ac4f1c071574803ea1deec   (E2.2 implementation)
        -> bbb226ccf10729a8cbdbb2d2456824f67fa100a7   (E2.2 closure)
          -> dff4b0eb12dbfdeef7cf2e3508767d21cf62fbed   (E2.3 implementation)
            -> this closure-binding commit
```

No remote operation was performed at any point in E2.1, E2.2 or E2.3.
