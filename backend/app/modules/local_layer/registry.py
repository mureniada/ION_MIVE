"""Local material registry: the sole gate deciding what may be processed.

Two independent checks run over every registry load, in this order:

1. the whole document is validated against `schemas/local_material_registry.schema.json`;
2. each record is re-checked field by field so a failure names the offending
   material and the offending field, rather than a JSON pointer.

Missing-source-file policy: FAIL FAST. A record naming a file that is not on disk
raises `MissingSourceFileError`. A registry is a claim about what exists; silently
skipping a broken claim would let the working corpus shrink without anyone noticing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

REGISTRY_SCHEMA = "local_material_registry.schema.json"

# The eight fields mandated for every registered material.
REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "source_file",
    "version",
    "status",
    "authority",
    "retrieval_enabled",
    "approved_for_publication",
)

_BOOL_FIELDS = frozenset({"retrieval_enabled", "approved_for_publication"})


class LocalRegistryError(Exception):
    """The registry is unusable: malformed, or a record is invalid."""


class MissingSourceFileError(LocalRegistryError):
    """A registered material names a source file that is not on disk."""


@dataclass(frozen=True)
class MaterialRecord:
    id: str
    title: str
    source_file: str
    version: str
    status: str
    authority: str
    retrieval_enabled: bool
    approved_for_publication: bool

    def provenance(self, *, fragment_id: str) -> dict[str, Any]:
        """The provenance block carried with every fragment cut from this material.

        Draft/working status travels with the text, so it stays visible at every
        later stage instead of being reattachable only by looking the material up.
        """
        return {
            "material_id": self.id,
            "fragment_id": fragment_id,
            "title": self.title,
            "source_file": self.source_file,
            "version": self.version,
            "status": self.status,
            "authority": self.authority,
            "approved_for_publication": self.approved_for_publication,
        }


@dataclass(frozen=True)
class Registry:
    registry_version: str
    materials: tuple[MaterialRecord, ...]

    @property
    def retrievable(self) -> tuple[MaterialRecord, ...]:
        """Only materials the registry permits to be retrieved."""
        return tuple(m for m in self.materials if m.retrieval_enabled)


# --------------------------------------------------------------------------- #
# Locations
# --------------------------------------------------------------------------- #
def _schemas_dir() -> Path:
    """Locate `schemas/`, honouring ION_SCHEMAS_DIR.

    Deliberately a local copy of the rule used by `app/validation/validators.py`
    rather than an import of its private helper: that module is frozen for this
    phase and is neither modified nor reached into.
    """
    override = os.environ.get("ION_SCHEMAS_DIR")
    if override:
        candidate = Path(override)
        if (candidate / REGISTRY_SCHEMA).exists():
            return candidate
        raise LocalRegistryError(f"ION_SCHEMAS_DIR has no {REGISTRY_SCHEMA}: {candidate}")
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "schemas"
        if (candidate / REGISTRY_SCHEMA).exists():
            return candidate
    raise LocalRegistryError(
        f"Could not locate schemas/{REGISTRY_SCHEMA}; set ION_SCHEMAS_DIR."
    )


def local_materials_dir() -> Path:
    """Root of the local working materials, honouring ION_LOCAL_MATERIALS_DIR."""
    override = os.environ.get("ION_LOCAL_MATERIALS_DIR")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "local_materials"
        if (candidate / "registry.json").exists():
            return candidate
    raise LocalRegistryError(
        "Could not locate local_materials/registry.json; set ION_LOCAL_MATERIALS_DIR."
    )


def documents_dir(materials_dir: Path | None = None) -> Path:
    return (materials_dir or local_materials_dir()) / "documents"


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads((_schemas_dir() / REGISTRY_SCHEMA).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _validate_document(raw: Any) -> None:
    try:
        jsonschema.validate(instance=raw, schema=_schema())
    except jsonschema.ValidationError as exc:
        location = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise LocalRegistryError(
            f"{REGISTRY_SCHEMA}: invalid at '{location}': {exc.message}"
        ) from None


def _validate_record(raw: dict[str, Any], position: int) -> MaterialRecord:
    """Field-by-field check so the error names the material and the field."""
    where = raw.get("id") if isinstance(raw.get("id"), str) else f"materials[{position}]"

    for field in REQUIRED_FIELDS:
        if field not in raw:
            raise LocalRegistryError(f"material '{where}': missing required field '{field}'")
        value = raw[field]
        if field in _BOOL_FIELDS:
            if not isinstance(value, bool):
                raise LocalRegistryError(
                    f"material '{where}': field '{field}' must be a boolean, "
                    f"got {type(value).__name__}"
                )
        elif not isinstance(value, str) or not value.strip():
            raise LocalRegistryError(
                f"material '{where}': field '{field}' must be a non-empty string"
            )

    unknown = sorted(set(raw) - set(REQUIRED_FIELDS))
    if unknown:
        raise LocalRegistryError(
            f"material '{where}': unknown field(s) {unknown}; "
            f"permitted fields are {list(REQUIRED_FIELDS)}"
        )

    return MaterialRecord(**{f: raw[f] for f in REQUIRED_FIELDS})


def load_registry(registry_path: str | Path | None = None) -> Registry:
    """Read and fully validate the registry. Raises `LocalRegistryError` on any fault."""
    path = Path(registry_path) if registry_path else local_materials_dir() / "registry.json"
    if not path.is_file():
        raise LocalRegistryError(f"Registry not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LocalRegistryError(f"Registry is not valid JSON ({path}): {exc}") from None

    _validate_document(raw)

    records = [_validate_record(item, i) for i, item in enumerate(raw["materials"])]

    seen: set[str] = set()
    for record in records:
        if record.id in seen:
            raise LocalRegistryError(f"material '{record.id}': duplicate id in registry")
        seen.add(record.id)

    return Registry(registry_version=raw["registry_version"], materials=tuple(records))


def resolve_source_path(record: MaterialRecord, docs_dir: str | Path) -> Path:
    """Resolve a record's source file, failing fast when it is absent (documented policy)."""
    path = Path(docs_dir) / record.source_file
    if not path.is_file():
        raise MissingSourceFileError(
            f"material '{record.id}': source file not found: {path}. "
            "Policy is fail-fast — fix or remove the registry entry."
        )
    return path
