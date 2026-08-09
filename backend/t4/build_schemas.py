"""Write the two T4 schema artifacts to `schemas/` as canonical bytes.

Idempotent: running it twice writes identical bytes. A test re-derives the bytes
from `t4.schema_sources` and compares them to the files, so the artifact and its
source cannot drift apart unnoticed.

    python -m t4.build_schemas
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import jcs
from .schema_sources import IDENTITY_CONTRACT_META_SCHEMA, RUN_RECORD_SCHEMA

CONTRACT_SCHEMA_FILENAME = "ion_t4_identity_contract.schema.json"
RUN_RECORD_SCHEMA_FILENAME = "ion_t4_run_record.schema.json"

ARTIFACTS = {
    CONTRACT_SCHEMA_FILENAME: IDENTITY_CONTRACT_META_SCHEMA,
    RUN_RECORD_SCHEMA_FILENAME: RUN_RECORD_SCHEMA,
}


def schemas_dir() -> Path:
    """The repository's existing `schemas/` directory, found the way the app finds it."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schemas"
        if (candidate / "context_pack.schema.json").exists():
            return candidate
    raise RuntimeError("could not locate the repository's schemas/ directory")


def canonical_bytes(filename: str) -> bytes:
    return jcs.serialize(ARTIFACTS[filename])


def write_all(target: Path | None = None) -> dict[str, str]:
    """Write both schemas; return ``{filename: sha256}`` computed from the bytes."""
    target = target or schemas_dir()
    digests = {}
    for filename in ARTIFACTS:
        raw = canonical_bytes(filename)
        (target / filename).write_bytes(raw)
        digests[filename] = hashlib.sha256(raw).hexdigest()
    return digests


if __name__ == "__main__":  # pragma: no cover
    for name, digest in sorted(write_all().items()):
        print(f"{digest}  {name}")
