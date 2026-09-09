"""VOE Dialogue Profile identity and runtime-payload vocabulary (v0.1,
Gate 1 + Gate 2A).

A `VOEProfileBinding` is a PRODUCT IDENTITY object. It states WHICH VOE
Dialogue Profile bundle a composer ran under. It states nothing about what
that bundle contains and nothing about how it was loaded or verified.

A `VOERuntimeProfile` (Gate 2A) pairs one `VOEProfileBinding` with the actual
verified behavioral text a composer needs. The two are kept as separate
types on purpose:

    IDENTITY BINDING != RUNTIME BEHAVIORAL PAYLOAD

    PROFILE != KNOWLEDGE
    PROFILE != EVIDENCE
    PROFILE != ADAPTIVE DIALOGUE ENGINE
    EXECUTION PROFILE != DIALOGUE PROFILE

This module holds no loading, no filesystem access, no hashing computation,
no environment read, and no bundle-file enumeration:
`runtime_behavioral_fingerprint_sha256` is carried verbatim as a value the
caller already computed elsewhere, exactly as
`ExecutionProfileBinding.mode` is carried as a plain string its own caller
already resolved (turn_record/models.py). Deciding WHICH files compose the
bundle this fingerprint covers, and HOW that fingerprint is computed, is
Gate 2's question — after `90-BUNDLE-MANIFEST.json` and
`91-PAYLOAD-SHA256SUMS.txt` are read — not this Gate 1 contract's.

This module imports the standard library only. No Core, container, config,
retrieval, provider, response_composer, or transport entry point is reachable
from here, so this identity object cannot be mistaken for, or carry, anything
beyond a bare profile identity.

No value in this module is derived from a wall clock, a UUID or a random
source, and no instance identifier is minted: every field is a value the
caller supplies verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass

VOE_PROFILE_BINDING_CONTRACT_ID = "ION_VOE_PROFILE_BINDING_V0_1"
VOE_PROFILE_BINDING_VERSION = "0.1"


class VOEProfileBindingError(ValueError):
    """Raised whenever a VOEProfileBinding or VOERuntimeProfile cannot be
    constructed as contracted.

    A missing, empty, or whitespace-padded identity field, a missing
    `binding`, or a missing/empty behavioral text field raises here; none is
    ever silently trimmed, defaulted, or coerced into a legal-looking value.

    This is a module-local error on purpose. This module introduces no
    transport stage, no mapping onto the core error taxonomy, and no
    readiness/activation behaviour — that is later, separately authorized
    work, not this contract's business.
    """


def _shape_checked_text(value: object, what: str) -> str:
    """Require a non-empty string carrying no leading/trailing whitespace.

    Taken verbatim otherwise: nothing is trimmed, cased or rewritten. Mirrors
    the identical check `execution_profile/models.py` already applies to its
    own identity fields, so a VOE profile identity fails exactly the same way
    an execution profile identity does.
    """
    if not isinstance(value, str) or not value:
        raise VOEProfileBindingError(f"{what} must be a non-empty string, found {value!r}")
    if value != value.strip():
        raise VOEProfileBindingError(
            f"{what} must carry no leading/trailing whitespace, found {value!r}"
        )
    return value


@dataclass(frozen=True, kw_only=True)
class VOEProfileBinding:
    """The identity of one VOE Dialogue Profile bundle a composer ran under.

    Minimum field set only: `profile_id`, `profile_version`, and
    `runtime_behavioral_fingerprint_sha256` — a single fingerprint standing
    for the complete effective RUNTIME behavioral payload (profile + style +
    ethics + illustrative reasoning), so validating this one value validates
    the whole runtime-loaded set, never just the canonical profile file in
    isolation. Deliberately named for what it actually covers, distinct from
    — and never satisfied by — either of the source preparation pack's own
    wider identity values: its whole fourteen-file preparation-payload
    fingerprint (which also covers calibration, checklist and audit-brief
    content this binding's bundle never loads) or its whole-archive/zip
    hash. See `modules/voe_profile/loader.py` for the fixed four-file set
    and the exact canonicalization rule this fingerprint is computed under.

    Deliberately absent, with no field to carry them: the profile text
    itself, the style parameters, the ethical policy text, the illustrative
    reasoning policy text, a file path, an enable/require flag, a load
    timestamp, and any provider or execution detail. This object states
    IDENTITY only — WHICH runtime bundle ran — never its content and never
    how it was obtained.

    Structural validation only: each field must be a non-empty string
    carrying no leading/trailing whitespace. Whether
    `runtime_behavioral_fingerprint_sha256` actually matches a real,
    currently-configured bundle is not checked here — this binding records
    identity, not verification authority over it; verification is
    `loader.py`'s job, performed before a binding is ever constructed.
    """

    profile_id: str
    profile_version: str
    runtime_behavioral_fingerprint_sha256: str

    def __post_init__(self) -> None:
        for name in ("profile_id", "profile_version", "runtime_behavioral_fingerprint_sha256"):
            _shape_checked_text(getattr(self, name), name)


@dataclass(frozen=True, kw_only=True)
class VOERuntimeProfile:
    """The complete, immutable, verified runtime behavioral payload for one
    VOE Dialogue Profile bundle — identity plus the actual text a composer
    reads.

    `binding` identifies exactly the behavioral payload materialized in the
    SAME verified load operation that produced this object's text fields —
    never a binding from a different load, and never text from a different
    binding. `loader.py` is the only place that may lawfully construct one
    from real, hash-verified files; this dataclass itself enforces only
    shape, not provenance.

    The four text fields are the UTF-8-decoded content of the four runtime
    behavioral files, verbatim: no normalization, no whitespace stripping, no
    line-ending change, no re-serialization. Each is the exact text decoded
    from the exact bytes `loader.py` already hash-verified — see its own
    docstring for the read/verify/decode sequence this guarantee depends on.

    Deliberately absent, with no field to carry them: retrieval or evidence
    content of any kind, `ModelContextAssembly`, `GovernedEvidenceSet`,
    `Settings`, a filesystem path, provider or model configuration, session
    state, conversation memory, a mutable container, or an open-ended
    metadata dict. This object states one versioned bundle's identity and
    text — nothing else — and is not a general profile schema or registry:
    it has exactly the four fields this one pinned VOE-DIALOGUE-PROFILE v0.2
    bundle defines, no more.

    `style_parameters_text` is kept as raw verified text in this contract,
    deliberately not parsed into a mapping or typed structure: the only
    required consumer at this stage is prompt construction, for which the
    exact verified text is sufficient. A parsed view may be added later, only
    once an actual authorized deterministic consumer needs one.
    """

    binding: VOEProfileBinding
    dialogue_profile_text: str
    style_parameters_text: str
    ethical_policy_text: str
    illustrative_reasoning_policy_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.binding, VOEProfileBinding):
            raise VOEProfileBindingError(
                "binding must be a VOEProfileBinding, found "
                f"{type(self.binding).__name__}"
            )
        for name in (
            "dialogue_profile_text",
            "style_parameters_text",
            "ethical_policy_text",
            "illustrative_reasoning_policy_text",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise VOEProfileBindingError(
                    f"{name} must be a non-empty string, found {value!r}"
                )
