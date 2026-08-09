"""The identity builder — the single construction path for every identity.

One deterministic function, :func:`build_identity`, implements the frozen
contract's projection: variant selection, byte coverage, flattening, unit
normalization and the §2A classification filter. No identity is produced any other
way, which is what makes T71's parity check and T63/T64/T80's raw-input mutation
tests mean something: mutating raw input and rebuilding is the only route to a
different digest, and patching a computed digest is not admissible evidence.

The projection per dimension is read *from the contract*, not hard-coded: the
dimension entry's `basis_kind` decides the shape, and for `parameter_set`
dimensions the selected variant's key set decides which keys must appear. What is
implementation here is only how a raw-input document is flattened onto those keys,
which the contract states in its `raw_input_shape` field.
"""

from __future__ import annotations

import base64
import hashlib

from . import jcs

__all__ = [
    "IdentityError",
    "SecretBoundaryViolation",
    "UnknownDimension",
    "VariantSelectionError",
    "build_identity",
    "select_variant",
]

# §2A S1: names whose value must never enter a basis. Classification fails closed —
# a key that matches is refused, never omitted, because an omission would produce a
# basis claiming a completeness it does not have (§2A S5).
SECRET_NAME_FRAGMENTS = (
    "api_key", "apikey", "secret", "password", "passphrase", "passwd",
    "credential", "token", "bearer", "authorization", "private_key", "cookie",
    "session_id",
)


class IdentityError(Exception):
    """An identity could not be constructed under the contract."""


class UnknownDimension(IdentityError):
    """The contract declares no such dimension."""


class VariantSelectionError(IdentityError):
    """Zero or more than one variant matched. There is no default and no fallback."""


class SecretBoundaryViolation(IdentityError):
    """A value classified security-material was offered where a basis key is expected."""


def _dimension_entry(contract: dict, dimension: str) -> dict:
    for entry in contract["dimensions"]:
        if entry["dimension"] == dimension:
            return entry
    raise UnknownDimension(f"contract declares no dimension {dimension!r}")


def _classify(key: str, value: str) -> None:
    lowered = key.lower()
    if any(fragment in lowered for fragment in SECRET_NAME_FRAGMENTS):
        raise SecretBoundaryViolation(
            f"basis key {key!r} is classified security-material and cannot be carried"
        )


def select_variant(entry: dict, discriminators: dict[str, str]) -> str:
    """Select exactly one variant from the record's own discriminator values.

    Zero matches is *unmatched*, two or more is *ambiguous*; both are errors. No
    precedence, specificity or fallback ordering exists (§13.4 rule 3).
    """
    matched = []
    for variant in entry["variants"] or []:
        if all(
            condition["match"] == "any"
            or discriminators.get(condition["discriminator"]) == condition["value"]
            for condition in variant["selector"]
        ):
            matched.append(variant)
    if len(matched) != 1:
        raise VariantSelectionError(
            f"{entry['dimension']}: {len(matched)} variants matched "
            f"{discriminators!r}; exactly one must"
        )
    return matched[0]["variant_id"]


def _parameters(entry: dict, variant_id: str, flattened: dict[str, object]) -> list[dict]:
    """Project a flattened raw input onto the selected variant's key set, closed both ways."""
    variant = next(v for v in entry["variants"] if v["variant_id"] == variant_id)
    declared = {key["key"]: key for key in variant["keys"]}

    missing = sorted(set(declared) - set(flattened))
    extra = sorted(set(flattened) - set(declared))
    if missing or extra:
        raise IdentityError(
            f"{entry['dimension']}/{variant_id}: raw input does not project onto the "
            f"contracted key set (missing={missing}, extra={extra})"
        )

    parameters = []
    for key in sorted(declared, key=lambda k: k.encode("utf-16-be")):
        value_type = declared[key]["value_type"]
        text = _typed_string(value_type, flattened[key], f"{entry['dimension']}.{key}")
        _classify(key, text)
        parameters.append({"key": key, "value": text, "value_type": value_type})
    return parameters


def _typed_string(value_type: str, value: object, where: str) -> str:
    """Every basis parameter value is a canonical typed string (§4.2B)."""
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise IdentityError(f"{where}: expected a boolean, got {type(value).__name__}")
        return "true" if value else "false"
    if value_type == "null_value":
        if value is not None:
            raise IdentityError(f"{where}: expected null")
        return ""
    if value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise IdentityError(f"{where}: expected an integer")
        return str(value)
    if value_type == "decimal":
        if not isinstance(value, str):
            raise IdentityError(
                f"{where}: a decimal is carried as its canonical string, never a float"
            )
        return value
    if value_type == "string":
        if not isinstance(value, str):
            raise IdentityError(f"{where}: expected a string, got {type(value).__name__}")
        return value
    raise IdentityError(f"{where}: unknown value_type {value_type!r}")


def _flatten(dimension: str, raw_input: dict) -> dict[str, object]:
    """Flatten a raw-input document onto basis keys, per the contract's raw_input_shape.

    One representation per value, and the flattening is total: anything the raw
    input carries that the key set does not declare is an error rather than a
    silent drop (checked in :func:`_parameters`).
    """
    if dimension == "implementation":
        flattened: dict[str, object] = dict(raw_input["distributions"])
        flattened["python_version"] = raw_input["python"]
        return flattened
    if dimension == "dispatch":
        return {
            "configurable": raw_input["configurable"],
            "mode": raw_input["mode"],
            # a comma-separated list, in call order, with no spaces: a basis
            # parameter value is always a string (§4.2B)
            "order": ",".join(raw_input["order"]),
        }
    if dimension == "fallback":
        return {
            "enabled": raw_input["enabled"],
            "on_provider_error": raw_input["on_provider_error"],
        }
    raise IdentityError(f"no flattening is defined for dimension {dimension!r}")


def build_identity(dimension: str, raw_input: dict, contract: dict,
                   discriminators: dict[str, str] | None = None) -> dict:
    """The only path by which an identity is produced.

    ``raw_input`` is the document the contract's ``raw_input_shape`` describes.
    The returned identity carries its basis and a digest recomputed over that
    basis's canonical serialization — never a digest supplied from outside.
    """
    entry = _dimension_entry(contract, dimension)
    kind = entry["basis_kind"]

    if kind == "content_reference":
        if not raw_input.get("present", False):
            if not entry["absence_permitted"]:
                raise IdentityError(f"{dimension}: absence is not permitted")
            basis = {"basis_kind": "absence", "content": None, "dimension": dimension,
                     "key_set_variant": None, "parameters": []}
            presence, state = "absent", "explicitly_disabled"
        else:
            content_bytes = base64.b64decode(raw_input["bytes_b64"] or "", validate=True)
            basis = {
                "basis_kind": "content_reference",
                "content": {
                    "byte_length": len(content_bytes),
                    # computed, never transcribed — including for zero-length content
                    "content_digest": hashlib.sha256(content_bytes).hexdigest(),
                },
                "dimension": dimension,
                "key_set_variant": None,
                "parameters": [],
            }
            presence, state = "present", "explicit_value"

    elif kind == "unobservable":
        if raw_input.get("locally_set", False):
            raise IdentityError(
                f"{dimension}: the contract declares this dimension unobservable, but "
                f"the raw input says a value is set locally — a contract gap (§10)"
            )
        basis = {"basis_kind": "unobservable", "content": None, "dimension": dimension,
                 "key_set_variant": None, "parameters": []}
        presence, state = "present", "provider_managed_unobservable"

    elif kind == "parameter_set":
        variant_id = select_variant(entry, discriminators or {})
        basis = {
            "basis_kind": "parameter_set",
            "content": None,
            "dimension": dimension,
            "key_set_variant": variant_id,
            "parameters": _parameters(entry, variant_id, _flatten(dimension, raw_input)),
        }
        presence, state = "present", "explicit_value"

    else:  # pragma: no cover - the meta-schema admits no fourth kind
        raise IdentityError(f"{dimension}: unknown basis_kind {kind!r}")

    return {
        "basis": basis,
        "digest": hashlib.sha256(jcs.serialize(basis)).hexdigest(),
        "dimension": dimension,
        "presence": presence,
        "resolution_state": state,
    }
