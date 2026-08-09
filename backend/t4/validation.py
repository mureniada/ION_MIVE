"""Record validation, and reading a record back (I16, I17, T82c, T85d).

Two rules that are easy to state and easy to lose:

* a record is validated against the **registered** run-record schema, resolved
  through the manifest by recomputed hash — never against a schema found by
  filename;
* a stored record whose bytes are not their own canonical serialization is
  **rejected on read**, before the data model is trusted for anything.
"""

from __future__ import annotations

from pathlib import Path

import jsonschema

from . import jcs, manifest

__all__ = ["RecordRejected", "load_record", "record_validator"]


class RecordRejected(Exception):
    """A stored record is unverifiable: non-canonical bytes, or invalid, or unresolved."""


def record_validator(manifest_path: Path | None = None):
    """Return ``validate(record) -> error_message | None`` against the registered schema."""
    _path, raw, _digest = manifest.resolve(manifest.ROLE_RUN_RECORD_SCHEMA, manifest_path)
    schema = jcs.parse(raw)
    validator = jsonschema.Draft202012Validator(schema)

    def validate(record: dict) -> str | None:
        errors = sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path))
        if not errors:
            return None
        first = errors[0]
        location = "/".join(str(p) for p in first.absolute_path) or "<root>"
        return f"invalid at '{location}': {first.message}"

    return validate


def load_record(path: Path, manifest_path: Path | None = None) -> dict:
    """Read a stored record, refusing non-canonical bytes and invalid content."""
    raw = path.read_bytes()
    try:
        record = jcs.parse(raw)
    except jcs.CanonicalizationError as exc:
        raise RecordRejected(f"{path.name}: not admissible JSON: {exc}") from None
    if jcs.serialize(record) != raw:
        raise RecordRejected(
            f"{path.name}: stored bytes are not the canonical serialization (I16)")

    declared = record.get("run_configuration", {}).get("identity_contract_sha256")
    try:
        _file, _bytes, digest = manifest.resolve(manifest.ROLE_CONTRACT, manifest_path)
    except manifest.ManifestError as exc:
        raise RecordRejected(
            f"{path.name}: the contract it was written under does not resolve, so the "
            f"record is unverifiable and is not compared: {exc}") from None
    if declared != digest:
        raise RecordRejected(
            f"{path.name}: written under contract {declared}, which is not the "
            f"registered contract {digest}")

    error = record_validator(manifest_path)(record)
    if error is not None:
        raise RecordRejected(f"{path.name}: {error}")
    return record
