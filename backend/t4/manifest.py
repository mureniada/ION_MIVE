"""The canonical artifact manifest — registration and resolution (D2, §13.5).

One manifest, one resolution path: **manifest -> file -> canonical bytes -> hash**.
A filename match is not resolution, and a manifest entry whose file hashes to
something else does not resolve. Nothing reads a hash *out of* the manifest and
treats it as established: every resolution recomputes (I5, T37).

Entry format. No manifest existed when this was written and no entry convention
existed to follow, so this one is defined here and stated rather than implied:

    {"bytes_covered": <what the digest covers, in words>,
     "name": <canonical artifact name>,
     "path": <repository-relative path, forward slashes>,
     "role": <one of the four roles below>,
     "sha256": <64 lowercase hex>,
     "version": <artifact version>}

The manifest itself is a container, not a fifth artifact, and does not register
itself (§3A.0).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import jcs

__all__ = [
    "ARTIFACT_ROLES",
    "ManifestError",
    "Unresolved",
    "default_path",
    "load",
    "register",
    "repository_root",
    "resolve",
]

ROLE_EMITTER = "emitter"
ROLE_RUN_RECORD_SCHEMA = "run_record_schema"
ROLE_CONTRACT_SCHEMA = "identity_contract_meta_schema"
ROLE_CONTRACT = "identity_contract"

#: The four artifacts of the integrity boundary (§6). Exactly four, gated by G2.
ARTIFACT_ROLES = (ROLE_CONTRACT, ROLE_CONTRACT_SCHEMA, ROLE_EMITTER, ROLE_RUN_RECORD_SCHEMA)

ENTRY_FIELDS = ("bytes_covered", "name", "path", "role", "sha256", "version")


class ManifestError(Exception):
    """The manifest is missing, malformed, or asked to hold something it must not."""


class Unresolved(ManifestError):
    """An artifact did not resolve: absent entry, absent file, or a hash mismatch."""


def repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "artifact_manifest.json").exists() or (parent / ".git").exists():
            return parent
    raise ManifestError("could not locate the repository root")


def default_path() -> Path:
    return repository_root() / "artifact_manifest.json"


def load(path: Path | None = None) -> dict:
    path = path or default_path()
    if not path.is_file():
        raise ManifestError(f"no manifest at {path}")
    document = jcs.parse(path.read_bytes())
    if not isinstance(document, dict) or "artifacts" not in document:
        raise ManifestError("manifest does not carry an artifacts array")
    return document


def register(entries: list[dict], path: Path | None = None) -> bytes:
    """Replace the manifest's artifact list with ``entries``, canonically serialized.

    Rejects an entry whose role is not one of the four, a duplicate role, an entry
    with an unknown or missing field, and any path that resolves outside the
    repository. Returns the bytes written.
    """
    path = path or default_path()
    root = path.parent

    seen = set()
    for entry in entries:
        if set(entry) != set(ENTRY_FIELDS):
            raise ManifestError(f"entry fields must be exactly {ENTRY_FIELDS}: {entry}")
        if entry["role"] not in ARTIFACT_ROLES:
            raise ManifestError(f"unknown artifact role {entry['role']!r}")
        if entry["role"] in seen:
            raise ManifestError(f"duplicate role {entry['role']!r}")
        seen.add(entry["role"])
        target = (root / entry["path"]).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            raise ManifestError(f"entry path escapes the repository: {entry['path']}")
        if not target.is_file():
            raise ManifestError(f"entry path does not exist: {entry['path']}")
        computed = hashlib.sha256(target.read_bytes()).hexdigest()
        if computed != entry["sha256"]:
            raise ManifestError(
                f"{entry['role']}: declared {entry['sha256']}, file hashes to {computed}"
            )

    document = {"artifacts": sorted(entries, key=lambda e: e["role"])}
    raw = jcs.serialize(document)
    path.write_bytes(raw)
    return raw


def resolve(role: str, path: Path | None = None) -> tuple[Path, bytes, str]:
    """Resolve one artifact. Returns ``(file, bytes, sha256)``; the hash is recomputed.

    Raises :class:`Unresolved` if the role has no entry, the file is absent, or the
    file's bytes do not hash to the registered digest. There is no other path to an
    artifact: no filename convention, no search, no side-channel (§13.5).
    """
    path = path or default_path()
    document = load(path)
    matches = [e for e in document["artifacts"] if e.get("role") == role]
    if len(matches) != 1:
        raise Unresolved(f"{role}: expected exactly one manifest entry, found {len(matches)}")
    entry = matches[0]
    target = path.parent / entry["path"]
    if not target.is_file():
        raise Unresolved(f"{role}: registered file is absent: {entry['path']}")
    raw = target.read_bytes()
    computed = hashlib.sha256(raw).hexdigest()
    if computed != entry["sha256"]:
        raise Unresolved(
            f"{role}: registered {entry['sha256']}, file hashes to {computed}"
        )
    return target, raw, computed
