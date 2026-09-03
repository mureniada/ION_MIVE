# ION E3 — Durable Closure Binding

**Date:** 2026-09-03
**Project-control phase:** E3 — Derived Index Materialization / Verify / Activate / Rollback
**E3 status:** IMPLEMENTED / VERIFIED / COMMITTED

## 1. Commit identity

| Field | Value |
|---|---|
| Implementation commit | `5916e9dd85705422e2a8b416b55318fe00848520` |
| Implementation parent | `e92fa8bc96bf29c659f72c824a88859bd21985d7` |
| Implementation commit subject | `E3: add derived index lifecycle` |
| Implementation file count | 12 |

## 2. Exact implementation file set (twelve files)

```
backend/app/modules/derived_index_lifecycle/__init__.py
backend/app/modules/derived_index_lifecycle/activation.py
backend/app/modules/derived_index_lifecycle/identity.py
backend/app/modules/derived_index_lifecycle/materialize.py
backend/app/modules/derived_index_lifecycle/models.py
backend/app/modules/derived_index_lifecycle/verify.py
backend/tests/test_derived_index_lifecycle_activation_v0_1.py
backend/tests/test_derived_index_lifecycle_materialize_v0_1.py
backend/tests/test_derived_index_lifecycle_models_v0_1.py
backend/tests/test_derived_index_lifecycle_verify_v0_1.py
docs/ION_E3_DERIVED_INDEX_LIFECYCLE_CLOSURE_2026-09-03.md
docs/ION_E3_DERIVED_INDEX_LIFECYCLE_CONTRACT_v1.md
```

## 3. Committed blob identities (as measured independently at E3F, not regenerated here)

```
backend/app/modules/derived_index_lifecycle/__init__.py
  blob OID = fdd16da9474c180a3fac0fab0296d3cf75820bcd
  bytes    = 4404
  sha256   = 130fa317de17b04177d77c80d337b992ef8b4cb00503848346386d40c748593d

backend/app/modules/derived_index_lifecycle/activation.py
  blob OID = 1b6e911b66af868c8aa2de2cf9b29c454da45a54
  bytes    = 9489
  sha256   = 591e5ccfa83b5237d8a1c0fa2139f476b575ea6ef38567640a28bdb8d0622459

backend/app/modules/derived_index_lifecycle/identity.py
  blob OID = c9b5572503b002823c541edc8737848efbcb765f
  bytes    = 2474
  sha256   = b38b45266c421405f0143cbb883b569823a278c0bec5211214ca67752924da08

backend/app/modules/derived_index_lifecycle/materialize.py
  blob OID = 9699e65dd726707d1f9f4b5fe39c71d288bf3305
  bytes    = 11456
  sha256   = d62fc52fa90a95046d3ad4047fcc5e5c566d44ef6bfcb0e80aa068429674f171

backend/app/modules/derived_index_lifecycle/models.py
  blob OID = 3e36c93ae6eefc6dfbf11fedc38c1737973ef850
  bytes    = 44849
  sha256   = 9977e64f3df22810b3d158d2cd1d32febd54b1745574869f3d5045dd356b928a

backend/app/modules/derived_index_lifecycle/verify.py
  blob OID = 20fbd88e80b70d7f0931193284730e897daef502
  bytes    = 5442
  sha256   = 86944af473101359e11279adf971ddba0d98cb0ee3a57d849c47f95eb0eb5c49

backend/tests/test_derived_index_lifecycle_activation_v0_1.py
  blob OID = b056cf220051e0ed90326d61ab7cfdb1ece91e0d
  bytes    = 16400
  sha256   = 8cfc68039ad7487530a4fd3c67b7173ee9f46c58c7702f4d08bc99dd29843020

backend/tests/test_derived_index_lifecycle_materialize_v0_1.py
  blob OID = 26bfded9f732ceeac3946ffef2430897528ed394
  bytes    = 19607
  sha256   = ab320938bca57da1d65ea5a7a8c9acacd41d31dcf783874b6c6626f5b66eb63f

backend/tests/test_derived_index_lifecycle_models_v0_1.py
  blob OID = 9c16168dc80ffe55969389566ad8cd515940b7d6
  bytes    = 18532
  sha256   = b1f1f717f989cdb9299bd49f990ba658a466cbb508c09275b56aafd4fe9df9e8

backend/tests/test_derived_index_lifecycle_verify_v0_1.py
  blob OID = 207929893e79ede50cc9944969399a0bbeff1ca2
  bytes    = 11122
  sha256   = 34267f90aa1a653ab94b7690d66bf54eda862402b54534c2df1d71dc24dafc3b

docs/ION_E3_DERIVED_INDEX_LIFECYCLE_CLOSURE_2026-09-03.md
  blob OID = 855a5f9c3f3f5127642f48481dc32899248ec158
  bytes    = 12332
  sha256   = ab64dd6d9b74688e37b42c495e9a4cae1c1232e243c4308dae3c832c324675ee

docs/ION_E3_DERIVED_INDEX_LIFECYCLE_CONTRACT_v1.md
  blob OID = 74139c2e4a1bcec96a87714e72eeed1b964628ec
  bytes    = 26956
  sha256   = 476e3d75d242048db1ef9c3291ab524f5be968695b4bfdd32f07c53e4276cc6f
```

## 4. E3 lifecycle architecture

```
ExpectedDerivedIndexDescriptor
        |
        v
CANDIDATE MATERIALIZATION
        |
        v
CandidateMaterializationReceipt
        |
        v
STORE MEASUREMENT
        |
        v
MeasuredDerivedIndexDescriptor
        |
        v
STRUCTURAL VERIFY
        |
        v
VerificationReceipt
        |
        v
ALIAS ACTIVATE
        |
        v
ActivationReceipt
        |
        v
ALIAS ROLLBACK
        |
        v
RollbackReceipt
```

Preserved:

```
EXPECTED IDENTITY != MEASURED STORE STATE
BUILD != MEASURE != VERIFY != ACTIVATE != ROLLBACK
CANDIDATE != ACTIVE
VERIFIED  != ACTIVE
ROLLBACK  != REBUILD
```

## 5. Selected physical lifecycle

```
SELECTED ARCHITECTURE = BLUE / GREEN PHYSICAL COLLECTIONS + STABLE QDRANT LOGICAL ALIAS

Candidate materialization                = OUT-OF-BAND PHYSICAL COLLECTION
Active state                             = LOGICAL ALIAS TARGET
Activation                               = ALIAS CUTOVER
Rollback                                 = ALIAS CUTOVER BACK
Previous active physical collection      = PRESERVED
Collection deletion during activation    = NONE
Collection deletion during rollback      = NONE
```

## 6. Candidate materialization

- Candidate physical collection must not already exist.
- Candidate physical collection `!=` active logical alias.
- Candidate physical collection `!=` previous active physical collection.
- `ExpectedDerivedIndexDescriptor` is recomputed from `ContentBuildResult` +
  `EmbeddingProfile` + `VectorSchema`; exact expected-fingerprint equality is
  required before any write.
- Candidate write uses `QdrantRetrieval.index()`. It does **not** use
  `QdrantRetrieval.rebuild()`.
- Candidate materialization does not: delete existing collections, change the
  active alias, activate the candidate, or verify the candidate.

## 7. Candidate receipt boundary

`CandidateMaterializationReceipt` = a **build event / candidate binding**. It
binds the candidate physical collection to the expected derived-index
declaration and the build execution declaration.

```
CANDIDATE RECEIPT IDENTITY != EXPECTED DERIVED INDEX IDENTITY
BUILD RECEIPT               != VERIFICATION RECEIPT
```

## 8. Measurement

`measure_candidate` = **read-only, store-facing measurement**, located in
`backend/app/modules/derived_index_lifecycle/materialize.py`. This placement
is accepted: the authorized six-file production surface carried no separate
`measure.py`; `materialize.py` owns the physical candidate/store boundary
(write and read together); `verify.py` remains the one store-independent pure
boundary.

Measurement uses `get_collection` + `scroll`. It does not write, activate,
verify, or embed. Captured separately: the Qdrant-reported point count, the
enumerated point count, the actual `VectorSchema`, the
`MeasuredPointDescriptor` collection, and the measured-state fingerprint.

## 9. Measurement / verification separation

```
MEASURE != VERIFY
```

`MeasuredPointDescriptor` may represent invalid store state — a missing
`document_id` or a missing `evidence_fingerprint` — without raising, so the
measurement layer never hides a defect. Verification owns PASS/FAIL
classification exclusively.

## 10. Measured store identity

`MeasuredDerivedIndexDescriptor` = the actual observed store description.
`measured_state_fingerprint` is the deterministic store-state identity.
`measured_at` is audit metadata and is **excluded** from
`measured_state_fingerprint`. Therefore the same measured store state
measured at a different valid `measured_at` yields the **same**
`measured_state_fingerprint`.

```
EVENT RECEIPT IDENTITY != STORE-STATE IDENTITY != EXPECTED DERIVED INDEX IDENTITY
```

## 11. Structural verify

```
VERIFICATION SCOPE = STRUCTURAL_V0_1
```

Verification is a **pure expected-vs-measured comparison**: no Qdrant, no
network, no filesystem, no embedder, no clock, no store mutation.

PASS requires:

- expected record count == candidate expected count
- expected record count == candidate written count
- expected record count == Qdrant reported count
- expected record count == enumerated count
- no missing `document_id`
- no missing `evidence_fingerprint`
- no duplicate logical `document_id`
- no missing expected `document_id`
- no unexpected `document_id`
- expected `evidence_fingerprint` == measured `evidence_fingerprint`, for every `document_id`
- expected `VectorSchema` == measured `VectorSchema`

## 12. Verify scope limit

```
STRUCTURAL_V0_1 != UNIVERSAL VECTOR-BYTE VERIFICATION
```

E3 does not claim generic proof of: exact vector-byte reproduction, remote
provider determinism, actual remote model revision, actual embedding
implementation execution, semantic ranking equivalence, or full cryptographic
vector attestation.

## 13. Embedding execution qualification

```
EMBEDDING EXECUTION BINDING = DECLARED_ONLY
EXPECTED PROFILE != PROVEN RUNTIME PROFILE
```

The repository's current default local embedding profile remains **not
canonical-descriptor-eligible**. No repair was performed under E3. No
`model_revision` or `implementation_revision` was ever invented or inferred.

## 14. Activation

`activate_candidate` requires: `VerificationReceipt.status == PASS`; the
candidate physical collection exists; the required alias APIs are available;
and the actual current alias state equals the caller's explicit
`expected_previous_active_collection`. A prestate mismatch fails closed with
no cutover performed.

**Normal cutover:** alias moves from physical A to physical B through **one**
alias-update request, using the operation shape the E3C experiment
validated. A remains physically present. Activation does not build, measure,
verify, or delete A.

## 15. Bootstrap activation

If the alias is absent, a PASS-verified candidate may become the initial
active state: the logical alias is created pointing at the candidate
physical collection, `previous_active_collection = None`, and an
`ActivationReceipt` is still required. A bootstrap activation with
`previous_active_collection = None` does not imply rollback is available.

## 16. Rollback

`rollback_activation` consumes an `ActivationReceipt` and requires:
`previous_active_collection != None`; the current logical alias target
equals `ActivationReceipt.new_active_collection`; and the previous active
physical collection still exists. The alias then switches back to the
previous physical collection. No rebuild, no re-embed, no deletion.

```
ROLLBACK WITHOUT REBUILD = IMPLEMENTED / VERIFIED
```

## 17. Retention

```
E3 v0.1 COLLECTION DELETION      = NONE
PREVIOUS ACTIVE COLLECTION       = PRESERVED
FAILED CANDIDATE                 = NOT AUTOMATICALLY DELETED
COLLECTION RETENTION / GC POLICY = DEFERRED
```

Required for truthful rollback.

## 18. Concurrency qualification

```
CONCURRENT ALIAS WRITERS             = NOT SUPPORTED
EXCLUSIVE LIFECYCLE-WRITER AUTHORITY = REQUIRED during ACTIVATE / ROLLBACK
```

The alias prestate equality check reduces stale-operation risk. It is **not**
distributed locking, **not** a general compare-and-swap guarantee, and
**not** multi-writer concurrency control.

## 19. Alias capability handling

Required alias/client capabilities are checked directly (`hasattr`), never
inferred from a client version string. As committed, the exact methods
checked are: `get_aliases`, `collection_exists`, `update_collection_aliases`
(`backend/app/modules/derived_index_lifecycle/activation.py`,
`_REQUIRED_ALIAS_CAPABILITIES`). A missing capability fails closed.

## 20. E3C experiment (carried forward)

```
E3C CONTROLLED ALIAS EXPERIMENT = PASS

Observed installed qdrant-client    = 1.18.0
Repository dependency constraint    = qdrant-client >= 1.7
OBSERVED CLIENT VERSION != DURABLY PINNED CLIENT VERSION

Disposable server image tag = qdrant/qdrant:latest
  qdrant/qdrant:latest = IMAGE TAG, NOT a semantic server version
  QDRANT SERVER SEMANTIC VERSION = UNBOUND
```

The experiment demonstrated: BLUE built; ACTIVE alias pointed at BLUE; an
unmodified `QdrantRetrieval` reading through the alias; GREEN independently
built while ACTIVE remained BLUE; one bounded cutover moving ACTIVE from BLUE
to GREEN; BLUE remaining present; one bounded rollback moving ACTIVE from
GREEN back to BLUE; GREEN remaining present; rollback requiring no rebuild;
disposable state cleanup passing.

```
ATOMIC CUTOVER MECHANISM = SUPPORTED BY CONTROLLED EXPERIMENT
```

Bounded to the mechanism the experiment exercised — not a broader
distributed-systems guarantee.

## 21. Existing retrieval / core non-change

```
QDRANT_STORE MODIFICATION = NONE
QdrantRetrieval            = REUSED UNMODIFIED
RetrievalPort               = UNCHANGED
Core                         = UNCHANGED
container.py                 = UNCHANGED
config.py                     = UNCHANGED
Deployment alias wiring       = NOT IMPLEMENTED / LATER INTEGRATION CONCERN
E2.1                           = UNCHANGED
E2.2                           = UNCHANGED
E2.3                           = UNCHANGED
```

## 22. Verification record

```
TARGETED E3D TESTS = 76 PASS / 0 FAIL

  models                    31 PASS
  materialize / measurement 15 PASS
  verify                    13 PASS
  activation / rollback     17 PASS

BOUNDED REGRESSION BASELINE = 1305 PASS / 33 FAIL / 7 SKIP
POST-E3                     = 1381 PASS / 33 FAIL / 7 SKIP

DELTA             = +76 PASS / +-0 FAIL / +-0 SKIP
FAILURE SET DELTA = NONE
NEW E3 REGRESSION = NOT SUPPORTED

FULL STDLIB RUNNER = BLOCKED BY PRE-EXISTING COLLECTION-SURFACE CONDITIONS
```

No claim of full stdlib-suite PASS is made.

## 23. Q1 / Q2 / Q3 — preserved, unrepaired

```
Q1 = Overlay-dependent collection blocker. Pre-existing / non-E3. Unrepaired.
Q2 = 33 pre-existing CRLF byte-identity failures. Failure set delta = NONE. Pre-existing / non-E3. Unrepaired.
Q3 = ION_REPO_ROOT environment requirement.
```

Four main-worktree overlay files remain: not admitted, not read, untouched,
non-E3. No repair.

## 24. E3C/E3D real-store qualification

```
E3C   = disposable real Qdrant experiment
E3D/E3E = no real project Qdrant mutation
E3 implementation tests = fake / injected clients
```

No project/live collection was activated by the E3 implementation. Therefore:

```
GENERIC LIFECYCLE PRIMITIVES  = IMPLEMENTED / VERIFIED
LIVE PROJECT CONTENT ACTIVATION = NOT CLAIMED
```

## 25. E3 boundary

```
E2.1 = Canonical Content Pack identity / CLOSED
E2.2 = Minimal Content Engine / CLOSED
E2.3 = Expected Derived Index identity / CLOSED
E3   = Derived Index Lifecycle / IMPLEMENTED

E4   = Integrated ION pilot / NOT STARTED / NOT AUTHORIZED
```

No first genuine client/domain Content Pack is claimed. "The Works" is not
selected, not authorized. The cassette is not entered.

## 26. Ancestry chain bound by this closure

```
e92fa8bc96bf29c659f72c824a88859bd21985d7   (E2.3 / pre-E3 starting HEAD)
        -> 5916e9dd85705422e2a8b416b55318fe00848520   (E3 implementation commit)
                -> <this closure commit>                (E3 durable closure binding)
```

Prior durable anchors (recorded, not re-verified by content in this document;
ancestry is verified independently in the E3G execution report):

```
bbb226ccf10729a8cbdbb2d2456824f67fa100a7
a640dfa810b00044e472980bb8602ded0b2a0c6c
7cf6ba52557dd92c3f4c96a7edbdfbe9ade4d169
```

## 27. Disposition

```
PROJECT-CONTROL:E3       = CLOSED / DURABLE / LOCALLY REFERENCED
DERIVED INDEX LIFECYCLE  = CLOSED / VERIFIED / DURABLE
CONTENT LIFECYCLE        = E2.1 + E2.2 + E2.3 + E3 CLOSED
OPERATIONAL CONTENT PLANE = CLOSED
```

No push was performed. E4 was not entered.
