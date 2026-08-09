"""Build the four integrity-boundary artifacts and register them (§6, G2).

    python -m t4.build_artifacts

The emitter is source spread across several modules, so "the executable emitter
artifact" needs its bytes defined explicitly (§6.3). It is defined here as a
**source artifact**: a canonically serialized document listing every module of the
`t4` package with that module's SHA-256. The manifest's `emitter_sha256` covers
that document's canonical bytes, and the document in turn covers every module by
digest — so changing `jcs.py` changes the emitter's registered hash, which is the
property a one-file hash over `emitter.py` alone would silently lack.

Chosen over concatenating the sources into one file, which would have required
defining a concatenation order and separator — a new serialization to specify and
get wrong — where JCS is already specified and already tested.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import jcs, manifest
from .build_schemas import (
    CONTRACT_SCHEMA_FILENAME,
    RUN_RECORD_SCHEMA_FILENAME,
    schemas_dir,
    write_all,
)
from .emitter import EMITTER_NAME, EMITTER_VERSION

EMITTER_ARTIFACT_RELPATH = "backend/t4/dist/ion_t4_emitter.artifact.json"
CONTRACT_RELPATH = "backend/t4/contract/ion_t4_identity_contract_v1.json"
CONTRACT_NAME = "ion_t4_identity_contract_v1.json"


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def emitter_source_artifact() -> dict:
    """Every module of the emitter package, by repository-relative path and digest."""
    root = manifest.repository_root()
    modules = sorted(_package_dir().glob("*.py"))
    return {
        "artifact_kind": "ion-t4-emitter-source",
        "emitter_name": EMITTER_NAME,
        "emitter_version": EMITTER_VERSION,
        "modules": [
            {"path": path.relative_to(root).as_posix(),
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in modules
        ],
    }


def write_emitter_artifact() -> tuple[Path, bytes]:
    root = manifest.repository_root()
    target = root / EMITTER_ARTIFACT_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = jcs.serialize(emitter_source_artifact())
    target.write_bytes(raw)
    return target, raw


def contract_version(path: Path) -> str:
    return jcs.parse(path.read_bytes())["contract_version"]


def build_and_register(manifest_path: Path | None = None) -> list[dict]:
    """Write the artifacts, then register exactly four entries. Returns the entries."""
    manifest_path = manifest_path or manifest.default_path()
    root = manifest_path.parent

    schema_digests = write_all()
    _emitter_path, emitter_raw = write_emitter_artifact()
    contract_path = root / CONTRACT_RELPATH

    schemas = schemas_dir().relative_to(root).as_posix()
    entries = [
        {
            "bytes_covered": "the UTF-8 bytes of the RFC 8785 canonical serialization "
                             "of the identity contract, no BOM, no trailing newline",
            "name": CONTRACT_NAME,
            "path": CONTRACT_RELPATH,
            "role": manifest.ROLE_CONTRACT,
            "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
            "version": contract_version(contract_path),
        },
        {
            "bytes_covered": "the UTF-8 bytes of the RFC 8785 canonical serialization "
                             "of the meta-schema, no BOM, no trailing newline",
            "name": CONTRACT_SCHEMA_FILENAME,
            "path": f"{schemas}/{CONTRACT_SCHEMA_FILENAME}",
            "role": manifest.ROLE_CONTRACT_SCHEMA,
            "sha256": schema_digests[CONTRACT_SCHEMA_FILENAME],
            "version": "1.0.0",
        },
        {
            "bytes_covered": "the UTF-8 bytes of the RFC 8785 canonical serialization "
                             "of the emitter source artifact, which lists every module "
                             "of the t4 package with that module's SHA-256",
            "name": "ion_t4_emitter.artifact.json",
            "path": EMITTER_ARTIFACT_RELPATH,
            "role": manifest.ROLE_EMITTER,
            "sha256": hashlib.sha256(emitter_raw).hexdigest(),
            "version": EMITTER_VERSION,
        },
        {
            "bytes_covered": "the UTF-8 bytes of the RFC 8785 canonical serialization "
                             "of the run-record schema, no BOM, no trailing newline",
            "name": RUN_RECORD_SCHEMA_FILENAME,
            "path": f"{schemas}/{RUN_RECORD_SCHEMA_FILENAME}",
            "role": manifest.ROLE_RUN_RECORD_SCHEMA,
            "sha256": schema_digests[RUN_RECORD_SCHEMA_FILENAME],
            "version": "1.0.0",
        },
    ]
    manifest.register(entries, manifest_path)
    return entries


if __name__ == "__main__":  # pragma: no cover
    for entry in build_and_register():
        print(f"{entry['sha256']}  {entry['role']:<32} {entry['path']}")
