# ION E3 — Derived-Index Lifecycle Contract (v0.1)

**Contract ID:** `ION_DERIVED_INDEX_LIFECYCLE_V0_1`
**Contract version:** `0.1`
**Package:** `backend/app/modules/derived_index_lifecycle`
**Status:** Implemented and verified (E3D), accepted for closure (E3E). Not yet committed.

This document states the exact final implemented semantics of the E3 derived-index
lifecycle package, as measured from the code, not as reconstructed from the
authorization that requested it.

## 1. What E3 answers that E2.3 does not

`derived_index` (E2.3) declares an **expected** derived index from a Content Pack
build, an embedding profile and a vector schema. It never measures, writes,
verifies or activates anything.

E3 answers the question E2.3 deliberately refuses: what actually happened when an
expected derived index was built, measured, verified, activated or rolled back.

```
ExpectedDerivedIndexDescriptor  (E2.3, reused read-only)
        |
        v
materialize_candidate   -> CandidateMaterializationReceipt   [WRITES]
        |
        v
measure_candidate       -> MeasuredDerivedIndexDescriptor    [READS, read-only]
        |
        v
verify_candidate        -> VerificationReceipt                [PURE]
        |
        v
activate_candidate      -> ActivationReceipt                  [ONE alias cutover]
        |
        v
rollback_activation     -> RollbackReceipt                    [ONE alias cutover back]
```

Preserved boundaries:

```
EXPECTED IDENTITY   != MEASURED STORE STATE
BUILD != MEASURE != VERIFY != ACTIVATE != ROLLBACK
CANDIDATE != ACTIVE
VERIFIED  != ACTIVE
ROLLBACK  != REBUILD
```

## 2. Selected architecture

**Blue/green physical Qdrant collections behind one stable logical alias**
(operator-approved at E3B, experimentally supported at E3C):

- A candidate is built as an independent physical Qdrant collection ("blue" or
  "green"), never in place of the currently active one.
- The **active address** the rest of the system reads through is a stable Qdrant
  **alias**, not a physical collection name.
- **Activation = alias cutover only.** It never builds, embeds, measures,
  verifies, or deletes a collection.
- **Rollback = alias cutover back** to the physical collection an activation
  replaced. It never rebuilds, re-embeds, or deletes anything.

## 3. Module surface — six production files

No seventh production file exists. `measure_candidate` (the read-only Qdrant
observation function, Section 6 below) lives in `materialize.py`, not in a
separate `measure.py`: the authorized six-file surface for E3D contained no
such file, `materialize.py` owns the physical candidate/store boundary end to
end (write side and read side), and `verify.py` is kept as the one
store-independent pure-comparison boundary. This is an **accepted
implementation placement**, not an architecture expansion — the function was
not moved for naming symmetry.

| File | Owns |
|---|---|
| `__init__.py` | Public package surface (re-exports) |
| `identity.py` | Shared canonical byte rule: `t4.jcs.serialize` + SHA-256 |
| `models.py` | Immutable receipt objects, constants, `DerivedIndexLifecycleError` |
| `materialize.py` | `materialize_candidate` (write) and `measure_candidate` (read-only) |
| `verify.py` | `verify_candidate` — pure comparison, zero I/O |
| `activation.py` | `activate_candidate` and `rollback_activation` — bounded alias cutover |

## 4. Contract-level constants (exact values, as implemented)

```
DERIVED_INDEX_LIFECYCLE_CONTRACT_ID       = "ION_DERIVED_INDEX_LIFECYCLE_V0_1"
DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION  = "0.1"

VERIFICATION_SCOPE_STRUCTURAL_V0_1        = "STRUCTURAL_V0_1"
EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY = "DECLARED_ONLY"

VERIFICATION_STATUS_PASS                  = "PASS"
VERIFICATION_STATUS_FAIL                  = "FAIL"

ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE  = "ALIAS_BOOTSTRAP_CREATE"
ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER    = "ALIAS_ATOMIC_CUTOVER"

ROLLBACK_RESULT_ROLLED_BACK               = "ROLLED_BACK"

CANONICALIZATION_PROFILE_ID               = "ION_JCS_V0_1"      (reused from derived_index.identity)
CANONICALIZATION_IMPLEMENTATION           = "t4.jcs.serialize"
FINGERPRINT_ALGORITHM                     = "SHA256"
```

## 5. Exact implemented function signatures

```python
def materialize_candidate(
    *,
    content_build_result: Any,
    expected_derived_index_descriptor: ExpectedDerivedIndexDescriptor,
    embedding_profile: EmbeddingProfile,
    vector_schema: VectorSchema,
    embedder: Any,
    qdrant_url: str,
    candidate_physical_collection: str,
    materialized_at: str,
    materializer_implementation_revision: str,
    active_alias: str | None = None,
    previous_active_collection: str | None = None,
    qdrant_client: Any = None,
    qdrant_models: Any = None,
) -> CandidateMaterializationReceipt: ...

def measure_candidate(
    *,
    candidate_physical_collection: str,
    measured_at: str,
    measurement_implementation_revision: str,
    qdrant_client: Any,
    scroll_page_size: int = 256,
) -> MeasuredDerivedIndexDescriptor: ...

def verify_candidate(
    *,
    expected_derived_index_descriptor: ExpectedDerivedIndexDescriptor,
    candidate_receipt: CandidateMaterializationReceipt,
    measured_descriptor: MeasuredDerivedIndexDescriptor,
    verified_at: str,
    verifier_implementation_revision: str,
) -> VerificationReceipt: ...

def activate_candidate(
    *,
    verification_receipt: VerificationReceipt,
    candidate_physical_collection: str,
    logical_alias: str,
    expected_previous_active_collection: str | None,
    activated_at: str,
    activator_implementation_revision: str,
    qdrant_client: Any,
) -> ActivationReceipt: ...

def rollback_activation(
    *,
    activation_receipt: ActivationReceipt,
    rolled_back_at: str,
    rollback_implementation_revision: str,
    qdrant_client: Any,
) -> RollbackReceipt: ...
```

`qdrant_client` / `qdrant_models` in `materialize_candidate` are an injectable
seam (fakes in tests; omitted in production so `QdrantRetrieval` lazily
constructs the real client) — the same pattern `tests/test_qdrant_batching.py`
already uses against `QdrantRetrieval`. They must be supplied together or not
at all; supplying only one fails closed.

## 6. Candidate materialization — exact law

Before any Qdrant write, `materialize_candidate`:

1. Requires `candidate_physical_collection` to be a non-empty, whitespace-clean
   string, `!= active_alias` (if given) and `!= previous_active_collection` (if
   given).
2. Recomputes `ExpectedDerivedIndexDescriptor.create(content_build_result,
   embedding_profile, vector_schema)` and requires the recomputed
   `derived_index_fingerprint` to equal the one already carried by the supplied
   `expected_derived_index_descriptor`. Mismatch fails closed before any write —
   this is what stops an unrelated build from being materialized under a
   borrowed expected descriptor.
3. Constructs a **separate** `QdrantRetrieval` instance bound to the candidate
   physical collection, checks `collection_exists(candidate_physical_collection)`
   and fails closed if it is already `True` (no delete, no overwrite).
4. Calls `QdrantRetrieval.index(documents)` — **never** `.rebuild()`. No
   collection is ever deleted by this function. No alias is ever touched by
   this function.
5. Requires `written_point_count == expected_record_count`
   (`expected_derived_index_descriptor.record_count`). A mismatch raises
   `DerivedIndexLifecycleError`; **no receipt is ever returned for a build that
   did not write exactly what was expected** — there is no "failed" receipt
   variant.

`CandidateMaterializationReceipt` binds (exact fields, Section 9 dataclass
surface below): `lifecycle_contract_version`, `expected_derived_index_fingerprint`,
`candidate_physical_collection`, `embedding_profile`, `vector_schema`,
`expected_record_count`, `written_point_count`, `materialized_at`,
`materializer_implementation_revision`, `embedding_execution_binding`,
`candidate_receipt_fingerprint`.

`CandidateMaterializationReceipt != ExpectedDerivedIndexDescriptor`: the receipt
fingerprint is an **event/audit identity** and may (and does) bind
`materialized_at` and the candidate physical collection address — it is not,
and never substitutes for, canonical expected derived-index identity.

## 7. Embedding execution binding

```
VERIFICATION SCOPE            = STRUCTURAL_V0_1
EMBEDDING EXECUTION BINDING   = DECLARED_ONLY
```

`materialize_candidate` always sets `embedding_execution_binding =
DECLARED_ONLY`. Passing an embedder object is **not** independent proof that
the declared model revision executed; a declared `implementation_revision` is
**not** a measurement of actual implementation execution. No runtime or model
identity is ever inferred, invented or measured. The repository's current
default local embedding profile remains not canonical-descriptor-eligible
(E2.3), and E3 does not repair that.

## 8. Measurement — exact law

`measure_candidate` is **read-only**: it calls `qdrant_client.get_collection(...)`
once and `qdrant_client.scroll(...)` in a loop until `next_offset is None`,
with exactly:

```python
qdrant_client.scroll(
    collection_name=candidate_physical_collection,
    with_payload=True,
    with_vectors=False,
    limit=scroll_page_size,   # default 256
    offset=offset,
)
```

No vector bytes are requested — not required for `STRUCTURAL_V0_1`
verification. Pagination is fully consumed; **pagination order is not
identity-bearing** — `MeasuredDerivedIndexDescriptor.create` re-sorts
`measured_points` by `qdrant_point_id` before binding them, and direct
construction with unsorted points fails closed. No Qdrant write of any kind
occurs on this path.

Captured separately (never collapsed into one number):

- `reported_point_count` — from `CollectionInfo.points_count`.
- `enumerated_point_count` — `len(measured_points)` after full pagination.
- the actual `VectorSchema` (Section 9 below).
- the canonical, sorted tuple of `MeasuredPointDescriptor`.

### Vector-schema measurement

From `CollectionInfo.config.params.vectors`:

- A single (unnamed) `VectorParams` → `VectorSchema(dimension=size,
  distance_metric=<distance enum .name>, vector_name=None)`. **Supported.**
- A `dict` with exactly one named entry → same, with `vector_name` set.
  **Supported.**
- A `dict` with more than one entry (multiple named vectors) → fails closed
  with `DerivedIndexLifecycleError`. **No vector is silently chosen.**
- Anything else (`None`, unrecognized shape) → fails closed.

`reported_point_count` is required to be a non-negative `int`; a non-integer
value fails closed.

### MeasuredPointDescriptor — represents invalid store state, does not hide it

Each measured point's `document_id` and `evidence_fingerprint` are `None` when
the stored payload does not carry a well-formed string for that field (missing,
or present but not a `str`). Measurement never raises on this — it must be able
to represent invalid/unverifiable store state. **PASS/FAIL classification
belongs entirely to `verify_candidate`.**

```
MEASUREMENT != VALIDATION SUCCESS
```

### Measured-state identity

`measured_state_fingerprint` is computed over `lifecycle_contract_version`,
`candidate_physical_collection`, `vector_schema`, `reported_point_count`,
`enumerated_point_count`, and the canonical `measured_points` mapping —
**`measured_at` is explicitly excluded.** `measured_at` is audit-event metadata,
not a store-state identity input: two measurements of the same unchanged store
state at different valid times yield the **same** `measured_state_fingerprint`,
even though the measurement *events* differ. This is proven directly by
`test_measured_state_fingerprint_stable_across_measured_at_changes`.

## 9. Receipt object field surfaces (exact, as declared)

```python
@dataclass(frozen=True, kw_only=True)
class CandidateMaterializationReceipt:
    lifecycle_contract_version: str
    expected_derived_index_fingerprint: str
    candidate_physical_collection: str
    embedding_profile: EmbeddingProfile
    vector_schema: VectorSchema
    expected_record_count: int
    written_point_count: int
    materialized_at: str
    materializer_implementation_revision: str
    embedding_execution_binding: str
    candidate_receipt_fingerprint: str

@dataclass(frozen=True, kw_only=True)
class MeasuredPointDescriptor:
    qdrant_point_id: str
    document_id: str | None
    evidence_fingerprint: str | None

@dataclass(frozen=True, kw_only=True)
class MeasuredDerivedIndexDescriptor:
    lifecycle_contract_version: str
    candidate_physical_collection: str
    vector_schema: VectorSchema
    reported_point_count: int
    enumerated_point_count: int
    measured_points: tuple[MeasuredPointDescriptor, ...]
    measured_at: str
    measurement_implementation_revision: str
    measured_state_fingerprint: str

@dataclass(frozen=True, kw_only=True)
class VerificationReceipt:
    lifecycle_contract_version: str
    verification_scope: str
    expected_derived_index_fingerprint: str
    candidate_receipt_fingerprint: str
    measured_state_fingerprint: str
    status: str
    expected_record_count: int
    candidate_expected_record_count: int
    candidate_written_point_count: int
    qdrant_reported_point_count: int
    enumerated_point_count: int
    missing_document_ids: tuple[str, ...]
    unexpected_document_ids: tuple[str, ...]
    duplicate_document_ids: tuple[str, ...]
    missing_required_payload_details: tuple[str, ...]
    evidence_fingerprint_mismatches: tuple[str, ...]
    bindings_match: bool
    schema_match: bool
    embedding_execution_binding: str
    verified_at: str
    verifier_implementation_revision: str
    verification_receipt_fingerprint: str

@dataclass(frozen=True, kw_only=True)
class ActivationReceipt:
    lifecycle_contract_version: str
    logical_alias: str
    previous_active_collection: str | None
    new_active_collection: str
    expected_derived_index_fingerprint: str
    verification_receipt_fingerprint: str
    activation_method: str
    activated_at: str
    activator_implementation_revision: str
    activation_receipt_fingerprint: str

@dataclass(frozen=True, kw_only=True)
class RollbackReceipt:
    lifecycle_contract_version: str
    logical_alias: str
    from_collection: str
    to_collection: str
    activation_receipt_fingerprint: str
    rolled_back_at: str
    rollback_implementation_revision: str
    result: str
    rollback_receipt_fingerprint: str
```

Every receipt is frozen (`dataclasses.FrozenInstanceError` on mutation) and
**measured, never trusted**: each `.create(...)` classmethod computes its own
fingerprint from its own already-declared fields, and `__post_init__`
recomputes and requires exact equality on every construction path, direct or
via `.create`. A caller-supplied fingerprint that does not match what the
object's own fields measure fails closed — proven directly by
`test_wrong_candidate_receipt_fingerprint_fails_closed`,
`test_wrong_verification_receipt_fingerprint_fails_closed`, and
`test_wrong_activation_receipt_fingerprint_fails_closed`.

## 10. Structural verification — exact law

`verify_candidate` is **pure**: no Qdrant client, no network, no filesystem, no
embedder, no clock, no mutation anywhere on its call path. It takes an already
-constructed `ExpectedDerivedIndexDescriptor`, `CandidateMaterializationReceipt`
and `MeasuredDerivedIndexDescriptor`, plus a caller-supplied `verified_at` and
`verifier_implementation_revision`.

### Bindings checked first (does not raise on mismatch)

```
candidate_receipt.expected_derived_index_fingerprint == expected.derived_index_fingerprint
candidate_receipt.candidate_physical_collection       == measured.candidate_physical_collection
candidate_receipt.embedding_profile                   == expected.embedding_profile
candidate_receipt.vector_schema                       == expected.vector_schema
```

All four must hold for `bindings_match = True`. A binding mismatch does **not**
raise — it folds into `bindings_match = False`, which alone forces
`status = FAIL`. Only a malformed object contract (wrong type, etc.) raises,
and that already happens inside the receipt models themselves, before
`verify_candidate` is ever reached.

### `STRUCTURAL_V0_1` PASS criteria (`status = PASS` iff ALL of)

- `bindings_match is True`
- `schema_match is True` (`measured.vector_schema == expected.vector_schema`)
- `expected_record_count == candidate_expected_record_count == candidate_written_point_count == qdrant_reported_point_count == enumerated_point_count`
- `missing_document_ids == ()` — no expected `document_id` absent from measured points
- `unexpected_document_ids == ()` — no measured `document_id` outside the expected set
- `duplicate_document_ids == ()` — no `document_id` measured more than once
- `missing_required_payload_details == ()` — no measured point missing `document_id` or `evidence_fingerprint`
- `evidence_fingerprint_mismatches == ()` — for every comparable `document_id`, expected `evidence_fingerprint == measured evidence_fingerprint`

Any failure of any one of these produces `status = FAIL`. The four
id/mismatch collections and `missing_required_payload_details` are always
**canonically ordered** (`tuple(sorted(...))`); an unsorted tuple fails
closed on direct construction (`_canonical_text_tuple`).

### Vector-proof boundary

```
STRUCTURAL_V0_1 != UNIVERSAL VECTOR-BYTE VERIFICATION
```

`STRUCTURAL_V0_1` does **not** claim: exact remote embedding reproducibility,
actual remote model-revision attestation, actual implementation-execution
attestation, semantic ranking equivalence, or full cryptographic vector
equality. These would be separate, stronger verification profiles this
implementation does not provide.

## 11. Alias activation — exact law

`activate_candidate` requires, in order:

1. `verification_receipt.status == VERIFICATION_STATUS_PASS` — else fails closed.
2. Alias capability on `qdrant_client`, checked **directly by `hasattr`**, never
   inferred from a version string:
   ```python
   _REQUIRED_ALIAS_CAPABILITIES = ("get_aliases", "collection_exists", "update_collection_aliases")
   ```
   Any missing method fails closed.
3. `qdrant_client.collection_exists(candidate_physical_collection)` — else fails
   closed.
4. Reads current alias state via `get_aliases()`, resolving `logical_alias` to
   `None` (absent) or exactly one target collection; more than one match, or an
   alias name colliding with an existing physical collection of the same name,
   fails closed rather than being reinterpreted.
5. Requires the **actual** current alias target to equal the caller-supplied
   `expected_previous_active_collection` exactly. Mismatch fails closed — this
   is the prestate precondition check (Section 13).
6. Requires `candidate_physical_collection != actual_target` (no meaningless
   no-op cutover).

**Bootstrap** (`actual_target is None`): one `update_collection_aliases` call
containing a single `CreateAliasOperation`. `activation_method =
ALIAS_BOOTSTRAP_CREATE`, `previous_active_collection = None`.

**Normal cutover** (`actual_target` = physical A, candidate = physical B, A !=
B): **one** `update_collection_aliases` call containing both a
`DeleteAliasOperation` (removing the alias from A) and a `CreateAliasOperation`
(pointing it at B) — the exact operation shape E3C's controlled experiment
proved. `activation_method = ALIAS_ATOMIC_CUTOVER`. **A is never deleted.**

`activate_candidate` never builds, embeds, measures, verifies, or deletes a
collection — it only reads and writes alias state.

`ActivationReceipt` binds: `logical_alias`, `previous_active_collection` (or
`None`), `new_active_collection`, `expected_derived_index_fingerprint` (carried
from the verification receipt), `verification_receipt_fingerprint`,
`activation_method`, `activated_at`, `activator_implementation_revision`,
`activation_receipt_fingerprint`.

```
VERIFICATION RECEIPT != ACTIVATION RECEIPT
```

## 12. Rollback — exact law

`rollback_activation` consumes an `ActivationReceipt` and requires, in order:

1. `activation_receipt.previous_active_collection is not None` — a bootstrap
   activation has nothing to roll back to and is refused
   (`DerivedIndexLifecycleError`).
2. The same alias-capability `hasattr` check as activation.
3. The **current** alias target (re-read via `get_aliases()`) equals
   `activation_receipt.new_active_collection` exactly — refuses a stale
   rollback otherwise.
4. `qdrant_client.collection_exists(activation_receipt.previous_active_collection)`
   — else fails closed.
5. **One** `update_collection_aliases` call: delete the alias from
   `new_active_collection`, create it pointing at `previous_active_collection`.

No rebuild, no re-embed, no deletion of either collection.

`RollbackReceipt` binds: `logical_alias`, `from_collection`, `to_collection`,
`activation_receipt_fingerprint` (the activation being reversed),
`rolled_back_at`, `rollback_implementation_revision`, `result` (`"ROLLED_BACK"`),
`rollback_receipt_fingerprint`.

```
ROLLBACK RECEIPT != NEW BUILD RECEIPT
ROLLBACK != REBUILD
```

## 13. Concurrency qualification (binding)

```
CONCURRENT ALIAS WRITERS = NOT SUPPORTED
```

This package provides **no transactional compare-and-swap lock** against
multiple concurrent lifecycle writers. The `expected_previous_active_collection`
prestate check (Section 11.5) reduces stale-operator/race risk by refusing to
act on a target that has already moved — it is a **precondition check**, not a
distributed lock and not a general transactional CAS guarantee. E3 v0.1
requires **exclusive lifecycle-writer authority** during `activate_candidate`
and `rollback_activation`. No locking framework is introduced.

## 14. Retention law

```
E3 v0.1 COLLECTION DELETION           = NONE
PREVIOUS ACTIVE PHYSICAL COLLECTION   = PRESERVED after cutover
FAILED CANDIDATE COLLECTION           = NOT AUTOMATICALLY DELETED
COLLECTION RETENTION / GC POLICY      = DEFERRED
```

No function in this package ever calls `delete_collection`. This is necessary
for rollback to remain truthful: the collection a rollback switches back to
must still exist, and nothing in E3 v0.1 can have removed it.

## 15. Canonicalization / receipt identity

Every receipt fingerprint reuses the existing `t4.jcs.serialize` + SHA-256 byte
rule (`derived_index_lifecycle/identity.py`) — **no new canonicalizer is
introduced.** `CANONICALIZATION_PROFILE_ID = "ION_JCS_V0_1"` is the same
internal deterministic-profile identity `derived_index.identity` already
established, reused rather than reinvented.

```
EVENT RECEIPT IDENTITY != STORE-STATE IDENTITY != EXPECTED DERIVED-INDEX IDENTITY
```

- `CandidateMaterializationReceipt`, `VerificationReceipt`, `ActivationReceipt`
  and `RollbackReceipt` fingerprints are **event/audit identities**: they may,
  and do, include their own event timestamp (`materialized_at`, `verified_at`,
  `activated_at`, `rolled_back_at` respectively) as part of the canonical
  payload.
- `MeasuredDerivedIndexDescriptor.measured_state_fingerprint` is the one
  exception: it **excludes** `measured_at`, because it represents store-state
  identity, not an event (Section 8).
- None of the five ever substitutes for
  `ExpectedDerivedIndexDescriptor.derived_index_fingerprint` (E2.3), which
  remains the sole canonical expected-index identity.

## 16. Explicit time law

Every lifecycle timestamp (`materialized_at`, `measured_at`, `verified_at`,
`activated_at`, `rolled_back_at`) must be an **explicit, caller-supplied
RFC3339 UTC string**. Validated by `models._rfc3339_utc`: a regex shape check
(`YYYY-MM-DDTHH:MM:SS[.ffffff](Z|+00:00)`) followed by `datetime.fromisoformat`
parsing and a UTC-offset check. No parameter defaults to a clock value — every
`create(...)` classmethod requires the timestamp as a mandatory keyword
argument (proven by `test_timestamp_is_never_defaulted`, which asserts the
`inspect.Parameter.empty` default on `materialized_at`). No `datetime.now()`,
`time.time()`, or system clock read appears anywhere in this package.

## 17. Qdrant / retrieval boundary

```
QDRANT_STORE MODIFICATION = NONE
QdrantRetrieval           = REUSED, UNMODIFIED
RetrievalPort              = UNCHANGED
Core                        = UNCHANGED
container.py                = UNCHANGED
config.py                    = UNCHANGED
```

`materialize_candidate` constructs its own `QdrantRetrieval` instance bound to
the candidate physical collection and calls its existing, unmodified `index()`
method (batched upsert, unchanged). Deployment alias wiring (making the
product's `RetrievalPort` adapter read through the logical alias rather than a
fixed collection name) is explicitly **not part of E3D** — `QdrantRetrieval`
was independently demonstrated at E3C to resolve a Qdrant collection alias
transparently, with no code change required, but wiring that into the running
product is deferred.

## 18. E3C experimental evidence (carried forward, not re-verified here)

```
E3C CONTROLLED ALIAS EXPERIMENT = PASS
```

Observed `qdrant-client` version: `1.18.0`. Repository dependency constraint:
`qdrant-client >= 1.7`. **Observed client version != durably pinned client
version** — E3D's alias-capability check (Section 11.2) is deliberately
`hasattr`-based rather than version-string-based for exactly this reason.

Disposable Qdrant server image used in the E3C experiment: `qdrant/qdrant:latest`.
This is an **image tag**, not a server semantic version claim.
`QDRANT SERVER SEMANTIC VERSION = UNBOUND` unless independently measured
read-only from a running server; no measurement of that kind was performed as
part of E3D or E3E, and none is claimed.

The experiment demonstrated: a BLUE physical collection built; an ACTIVE alias
pointed at BLUE; an unmodified `QdrantRetrieval` reading through the alias
transparently; a GREEN collection independently built while ACTIVE remained
BLUE; one alias-update call cutting ACTIVE from BLUE to GREEN; BLUE preserved
afterward; one reverse alias-update call rolling ACTIVE back from GREEN to
BLUE; GREEN preserved afterward; rollback requiring no rebuild. Repository
mutation: none. Project/live Qdrant mutation: none. Disposable experiment
cleanup: pass.

```
ATOMIC CUTOVER MECHANISM = SUPPORTED BY CONTROLLED EXPERIMENT
```

This is bounded to the mechanism the experiment actually exercised (a single
`update_collection_aliases` request containing a delete+create pair) — it is
not a broader distributed-systems atomicity or consistency guarantee.

## 19. E2 assets — closed, not reopened

No file under `content_pack/*`, `content_engine/*`, or `derived_index/*` was
modified by E3D or E3E. `ExpectedDerivedIndexDescriptor`, `EmbeddingProfile`,
`RecordDescriptor` and `VectorSchema` are consumed by E3 read-only.

```
EXPECTED INDEX CONTRACT = INPUT TO E3, NOT REOPENED BY E3
```
