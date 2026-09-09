"""VOE Dialogue Profile identity vocabulary (Gate 1 — inert identity/data
shape only).

The export list below is deliberately closed. It carries no loader, no
filesystem path, no hashing function, no environment name and no bundle-file
list, because this package implements none of them at Gate 1: it depends on
the standard library only.

`VOEProfileBinding` is a plain, immutable identity value — `profile_id`,
`profile_version`, `runtime_behavioral_fingerprint_sha256` — and nothing
else. `VOERuntimeProfile` (Gate 2A) pairs one such binding with the actual
verified behavioral text a composer needs. Neither type contains filesystem
loading, hashing computation, bundle-file enumeration, configuration
reading, or activation logic; constructing either from real, verified files
is `loader.py`'s job.

Gate 2 + Gate 2A (`loader.py`) implement the fixed, pinned, four-file
runtime behavioral payload for VOE-DIALOGUE-PROFILE v0.2 — read exactly by
name, never by directory listing, each file read exactly once — fail-closed
byte/hash/identity/fingerprint/UTF-8 validation, and the `VOE_PROFILE_ENABLED`
on/off law. It does not wire a `VOERuntimeProfile` into `Core.ask()`,
`app.container`, `ModelContextAssembly`, or any response composition path —
that remains later, separately authorized work.
"""

from .loader import (
    RUNTIME_BEHAVIORAL_FILES,
    VOE_PROFILE_LOADER_ID,
    VOE_PROFILE_LOADER_VERSION,
    EXPECTED_PROFILE_ID,
    EXPECTED_PROFILE_VERSION,
    EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256,
    VOEProfileLoadError,
    load_voe_profile_binding,
    load_voe_runtime_profile,
    resolve_voe_profile,
)
from .models import (
    VOE_PROFILE_BINDING_CONTRACT_ID,
    VOE_PROFILE_BINDING_VERSION,
    VOEProfileBinding,
    VOEProfileBindingError,
    VOERuntimeProfile,
)

__all__ = [
    "EXPECTED_PROFILE_ID",
    "EXPECTED_PROFILE_VERSION",
    "EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256",
    "RUNTIME_BEHAVIORAL_FILES",
    "VOE_PROFILE_BINDING_CONTRACT_ID",
    "VOE_PROFILE_BINDING_VERSION",
    "VOE_PROFILE_LOADER_ID",
    "VOE_PROFILE_LOADER_VERSION",
    "VOEProfileBinding",
    "VOEProfileBindingError",
    "VOEProfileLoadError",
    "VOERuntimeProfile",
    "load_voe_profile_binding",
    "load_voe_runtime_profile",
    "resolve_voe_profile",
]
