"""E3 derived-index lifecycle (v0.1) — public package surface.

Owns the question `derived_index` (E2.3) deliberately never answers: what
actually happened when an EXPECTED derived index was built, measured,
verified, activated or rolled back.

    ExpectedDerivedIndexDescriptor (E2.3, reused read-only)
            |
            v
    materialize_candidate  -> CandidateMaterializationReceipt   [WRITES]
            |
            v
    measure_candidate      -> MeasuredDerivedIndexDescriptor    [READS]
            |
            v
    verify_candidate       -> VerificationReceipt                [PURE]
            |
            v
    activate_candidate     -> ActivationReceipt                  [ONE alias cutover]
            |
            v
    rollback_activation    -> RollbackReceipt                    [ONE alias cutover back]

Selected architecture (operator-approved, E3B/E3C): blue/green physical
Qdrant collections behind one stable alias.

    EXPECTED IDENTITY != MEASURED STORE STATE
    BUILD != MEASURE != VERIFY != ACTIVATE != ROLLBACK
    CANDIDATE != ACTIVE
    VERIFIED != ACTIVE
    ROLLBACK != REBUILD

Verification scope is `STRUCTURAL_V0_1`: record-set completeness, per-record
evidence-fingerprint equality, vector-schema equality, and candidate/expected
identity binding — never a claim of universal vector-byte reproduction,
remote provider execution, or that a declared model/implementation revision
was actually loaded or executed (`embedding_execution_binding` is always
`DECLARED_ONLY` at this version).

This package provides no transactional compare-and-swap lock against
concurrent lifecycle writers; `activate_candidate` / `rollback_activation`
require exclusive lifecycle-writer authority. It performs no garbage
collection: a superseded physical collection is left in place so rollback
stays truthful. Retention policy is deferred.

See `models.py` for the receipt objects, `identity.py` for the shared
canonical byte rule, `materialize.py` for build + read-only measurement,
`verify.py` for the pure comparison, and `activation.py` for the bounded
alias cutover and its reverse.
"""

from __future__ import annotations

from .activation import activate_candidate, rollback_activation
from .identity import (
    CANONICALIZATION_IMPLEMENTATION,
    CANONICALIZATION_PROFILE,
    CANONICALIZATION_PROFILE_ID,
    FINGERPRINT_ALGORITHM,
)
from .materialize import materialize_candidate, measure_candidate
from .models import (
    ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER,
    ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE,
    DERIVED_INDEX_LIFECYCLE_CONTRACT_ID,
    DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION,
    EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY,
    ROLLBACK_RESULT_ROLLED_BACK,
    SUPPORTED_ACTIVATION_METHODS,
    SUPPORTED_EMBEDDING_EXECUTION_BINDINGS,
    SUPPORTED_LIFECYCLE_CONTRACT_VERSIONS,
    SUPPORTED_ROLLBACK_RESULTS,
    SUPPORTED_VERIFICATION_SCOPES,
    SUPPORTED_VERIFICATION_STATUSES,
    VERIFICATION_SCOPE_STRUCTURAL_V0_1,
    VERIFICATION_STATUS_FAIL,
    VERIFICATION_STATUS_PASS,
    ActivationReceipt,
    CandidateMaterializationReceipt,
    DerivedIndexLifecycleError,
    MeasuredDerivedIndexDescriptor,
    MeasuredPointDescriptor,
    RollbackReceipt,
    VerificationReceipt,
)
from .verify import verify_candidate

__all__ = [
    "ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER",
    "ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE",
    "ActivationReceipt",
    "CANONICALIZATION_IMPLEMENTATION",
    "CANONICALIZATION_PROFILE",
    "CANONICALIZATION_PROFILE_ID",
    "CandidateMaterializationReceipt",
    "DERIVED_INDEX_LIFECYCLE_CONTRACT_ID",
    "DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION",
    "DerivedIndexLifecycleError",
    "EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY",
    "FINGERPRINT_ALGORITHM",
    "MeasuredDerivedIndexDescriptor",
    "MeasuredPointDescriptor",
    "ROLLBACK_RESULT_ROLLED_BACK",
    "RollbackReceipt",
    "SUPPORTED_ACTIVATION_METHODS",
    "SUPPORTED_EMBEDDING_EXECUTION_BINDINGS",
    "SUPPORTED_LIFECYCLE_CONTRACT_VERSIONS",
    "SUPPORTED_ROLLBACK_RESULTS",
    "SUPPORTED_VERIFICATION_SCOPES",
    "SUPPORTED_VERIFICATION_STATUSES",
    "VERIFICATION_SCOPE_STRUCTURAL_V0_1",
    "VERIFICATION_STATUS_FAIL",
    "VERIFICATION_STATUS_PASS",
    "VerificationReceipt",
    "activate_candidate",
    "materialize_candidate",
    "measure_candidate",
    "rollback_activation",
    "verify_candidate",
]
