"""The two T4 JSON Schema artifacts, as data.

Holding the schemas here rather than as hand-maintained JSON has one purpose: the
files in `schemas/` must be persisted as their RFC 8785 canonical serialization
(I16, §13.3), which is a single unindented line nobody can usefully hand-edit.
These dictionaries are the source; `t4/build_schemas.py` writes them; a test
re-derives the bytes and compares, so the file and the source cannot drift.

Two schemas:

* :data:`IDENTITY_CONTRACT_META_SCHEMA` — §13.2, field by field, closed at every
  object level, with the ordering and uniqueness rules **declared** as annotations
  (`x-ordering`, `x-unique-by`). JSON Schema cannot enforce "sorted ascending under
  UTF-16 ordering" or "unique by a nested field"; §13.2 requires them declared, and
  `t4/contract_check.py` enforces them mechanically. The one array whose order
  carries meaning rather than sorting, `sources`, is marked as such (T88g).

* :data:`RUN_RECORD_SCHEMA` — §4, closed at all fifteen levels named in T35, with
  the domains of §4.9 and every conditional rule JSON Schema can carry. The
  derivations it cannot carry — `run_status` from `component_results`, the
  aggregate from `calls`, `run_fingerprint` recomputation, sequence and attempt
  consecutiveness, plan binding, measurement-path resolution, supersession
  resolution, variant selection — are enforced in `t4/emitter.py` and listed in
  :data:`CODE_ENFORCED_RULES` so the split is stated rather than assumed.
"""

from __future__ import annotations

DIMENSIONS = (
    "context", "decoding", "dispatch", "fallback", "implementation",
    "prompt", "retry", "termination", "timeout", "workload",
)
CONTENT_DIMENSIONS = ("context", "prompt", "workload")
POLICY_DIMENSIONS = ("dispatch", "fallback", "retry", "termination", "timeout")
VALUE_TYPES = ("boolean", "decimal", "integer", "null_value", "string")
RESOLUTION_STATES = (
    "explicit_value", "explicitly_disabled",
    "provider_managed_unobservable", "verified_sdk_default",
)
DISCRIMINATORS = ("component", "provider", "requested_model")
SOURCES = ("call_site", "config_file", "environment",
           "explicit", "library_default", "provider_default")

DIGEST = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
# Non-empty means "carries at least one non-whitespace character": §4.9 counts a
# whitespace-only identifier as empty. Expressed as a positive character test
# rather than a negative lookahead, which would also reject a leading newline.
NON_EMPTY = {"type": "string", "minLength": 1, "pattern": r"\S"}
BASE64 = {
    "type": "string",
    "pattern": "^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$",
    "x-encoding": "RFC 4648 standard alphabet, padded, no line breaks, no whitespace",
}
INTEGER_GRAMMAR = "^-?(0|[1-9][0-9]*)$"
DECIMAL_GRAMMAR = r"^-?(0|[1-9][0-9]*)\.[0-9]*[1-9]$"


def _closed(required, properties, **extra):
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(required),
        "properties": properties,
    }
    schema.update(extra)
    return schema


def _nullable(ref):
    return {"anyOf": [{"type": "null"}, ref]}


def _int(minimum, maximum, **extra):
    schema = {"type": "integer", "minimum": minimum, "maximum": maximum}
    schema.update(extra)
    return schema


# --------------------------------------------------------------------------- #
# Shared: the identity object and its basis (§4.2B)
# --------------------------------------------------------------------------- #

def _identity_defs(dimension_enum):
    """The identity/basis definitions, shared by both schemas.

    The basis-kind truth table and the presence/basis_kind/resolution_state
    coupling are expressed structurally, as T83 and T89 require.
    """
    parameter_entry = _closed(
        ["key", "value", "value_type"],
        {
            "key": NON_EMPTY,
            "value_type": {"enum": list(VALUE_TYPES)},
            "value": {"type": "string"},
        },
        allOf=[
            {"if": {"properties": {"value_type": {"const": "integer"}}, "required": ["value_type"]},
             "then": {"properties": {"value": {"pattern": INTEGER_GRAMMAR}}}},
            {"if": {"properties": {"value_type": {"const": "decimal"}}, "required": ["value_type"]},
             "then": {"properties": {"value": {"pattern": DECIMAL_GRAMMAR}}}},
            {"if": {"properties": {"value_type": {"const": "boolean"}}, "required": ["value_type"]},
             "then": {"properties": {"value": {"enum": ["false", "true"]}}}},
            {"if": {"properties": {"value_type": {"const": "null_value"}}, "required": ["value_type"]},
             "then": {"properties": {"value": {"const": ""}}}},
        ],
        **{"x-note": "value is always a string; a raw JSON number here is refused"},
    )

    content = _closed(
        ["byte_length", "content_digest"],
        {
            "content_digest": DIGEST,
            "byte_length": _int(0, 10 ** 12),
        },
        **{"x-note": "byte_length 0 is admissible and is not a presence discriminator"},
    )

    basis = _closed(
        ["basis_kind", "content", "dimension", "key_set_variant", "parameters"],
        {
            "basis_kind": {"enum": ["absence", "content_reference",
                                    "parameter_set", "unobservable"]},
            "dimension": {"enum": list(dimension_enum)},
            "key_set_variant": _nullable(NON_EMPTY),
            "parameters": {"type": "array", "maxItems": 256,
                           "x-ordering": "sorted-ascending-by:key (UTF-16 code units)",
                           "x-unique-by": "key",
                           "items": parameter_entry},
            "content": _nullable(content),
        },
        allOf=[
            # absence: empty parameters, null content, null variant
            {"if": {"properties": {"basis_kind": {"const": "absence"}}, "required": ["basis_kind"]},
             "then": {"properties": {"parameters": {"maxItems": 0},
                                     "content": {"type": "null"},
                                     "key_set_variant": {"type": "null"}}}},
            # content_reference: empty parameters, non-null content, null variant
            {"if": {"properties": {"basis_kind": {"const": "content_reference"}},
                    "required": ["basis_kind"]},
             "then": {"properties": {"parameters": {"maxItems": 0},
                                     "content": content,
                                     "key_set_variant": {"type": "null"}}}},
            # parameter_set: non-empty parameters, null content, non-null variant
            {"if": {"properties": {"basis_kind": {"const": "parameter_set"}},
                    "required": ["basis_kind"]},
             "then": {"properties": {"parameters": {"minItems": 1},
                                     "content": {"type": "null"},
                                     "key_set_variant": NON_EMPTY}}},
            # unobservable: empty parameters, null content, null variant
            {"if": {"properties": {"basis_kind": {"const": "unobservable"}},
                    "required": ["basis_kind"]},
             "then": {"properties": {"parameters": {"maxItems": 0},
                                     "content": {"type": "null"},
                                     "key_set_variant": {"type": "null"}}}},
        ],
    )

    identity = _closed(
        ["basis", "digest", "dimension", "presence", "resolution_state"],
        {
            "dimension": {"enum": list(dimension_enum)},
            "presence": {"enum": ["absent", "present"]},
            "resolution_state": {"enum": list(RESOLUTION_STATES)},
            "basis": {"$ref": "#/$defs/basis"},
            "digest": DIGEST,
        },
        allOf=[
            # The four admissible (presence, basis_kind, resolution_state) triples.
            {"if": {"properties": {"presence": {"const": "absent"}}, "required": ["presence"]},
             "then": {"properties": {
                 "basis": {"properties": {"basis_kind": {"const": "absence"}}},
                 "resolution_state": {"const": "explicitly_disabled"}}}},
            {"if": {"properties": {"basis": {"properties": {
                "basis_kind": {"const": "content_reference"}},
                "required": ["basis_kind"]}}, "required": ["basis"]},
             "then": {"properties": {"presence": {"const": "present"},
                                     "resolution_state": {"const": "explicit_value"}}}},
            {"if": {"properties": {"basis": {"properties": {
                "basis_kind": {"const": "parameter_set"}},
                "required": ["basis_kind"]}}, "required": ["basis"]},
             "then": {"properties": {"presence": {"const": "present"},
                                     "resolution_state": {
                                         "enum": ["explicit_value", "verified_sdk_default"]}}}},
            {"if": {"properties": {"basis": {"properties": {
                "basis_kind": {"const": "unobservable"}},
                "required": ["basis_kind"]}}, "required": ["basis"]},
             "then": {"properties": {
                 "presence": {"const": "present"},
                 "resolution_state": {"const": "provider_managed_unobservable"}}}},
        ],
        **{"x-note": "strict_comparability is derived from resolution_state and is "
                     "never a field (I19); the closed property set rejects it"},
    )

    return {"basis": basis, "content": content, "identity": identity,
            "parameter_entry": parameter_entry}


# --------------------------------------------------------------------------- #
# §13.2 — the identity-contract meta-schema
# --------------------------------------------------------------------------- #

def _meta_schema():
    defs = _identity_defs(DIMENSIONS)

    defs["content_rule"] = _closed(
        ["absence_case", "byte_coverage", "empty_case", "encoding"],
        {
            "byte_coverage": NON_EMPTY,
            "encoding": NON_EMPTY,
            "empty_case": NON_EMPTY,
            "absence_case": _nullable(NON_EMPTY),
        },
    )
    defs["state_rules"] = _closed(
        ["absent", "default", "disabled", "unknown"],
        {
            "disabled": NON_EMPTY,
            "default": NON_EMPTY,
            "unknown": NON_EMPTY,
            "absent": _nullable(NON_EMPTY),
        },
    )
    defs["unobservable_declaration"] = _closed(
        ["evidence", "reason"], {"reason": NON_EMPTY, "evidence": NON_EMPTY},
    )
    defs["sdk_default_verification"] = _closed(
        ["library", "vector_id", "version"],
        {"library": NON_EMPTY, "version": NON_EMPTY, "vector_id": NON_EMPTY},
    )
    defs["default_resolution"] = _closed(
        ["note", "readable_at_emission", "sources"],
        {
            "sources": {
                "type": "array", "minItems": 1, "uniqueItems": True,
                "items": {"enum": list(SOURCES)},
                "x-ordering": "meaning-bearing: precedence, first wins",
                "x-note": "the only array in this contract whose order is meaning "
                          "rather than canonical sorting",
            },
            "readable_at_emission": {"const": True},
            "note": _nullable(NON_EMPTY),
        },
    )
    defs["key_entry"] = _closed(
        ["default_resolution", "key", "meaning", "unit", "value_type"],
        {
            "key": NON_EMPTY,
            "value_type": {"enum": list(VALUE_TYPES)},
            "unit": _nullable(NON_EMPTY),
            "meaning": NON_EMPTY,
            "default_resolution": {"$ref": "#/$defs/default_resolution"},
        },
        **{"x-note": "unit is explicitly null where the value is dimensionless, so "
                     "'no unit' is a declaration and not an omission"},
    )
    defs["selector_condition"] = _closed(
        ["discriminator", "match", "value"],
        {
            "discriminator": {"enum": list(DISCRIMINATORS)},
            "match": {"enum": ["any", "exact"]},
            "value": _nullable(NON_EMPTY),
        },
        allOf=[
            {"if": {"properties": {"match": {"const": "any"}}, "required": ["match"]},
             "then": {"properties": {"value": {"type": "null"}}}},
            {"if": {"properties": {"match": {"const": "exact"}}, "required": ["match"]},
             "then": {"properties": {"value": NON_EMPTY}}},
        ],
        **{"x-note": "the wildcard is the mode match:'any', never a magic value; a "
                     "provider literally named '*' is an ordinary exact value"},
    )
    defs["variant"] = _closed(
        ["keys", "selector", "variant_id"],
        {
            "variant_id": NON_EMPTY,
            "selector": {"type": "array",
                         "x-ordering": "sorted-ascending-by:discriminator",
                         "x-unique-by": "discriminator",
                         "items": {"$ref": "#/$defs/selector_condition"}},
            "keys": {"type": "array", "minItems": 1,
                     "x-ordering": "sorted-ascending-by:key",
                     "x-unique-by": "key",
                     "items": {"$ref": "#/$defs/key_entry"}},
        },
    )
    defs["vector"] = _closed(
        ["expected_basis_bytes_b64", "expected_digest", "expected_identity",
         "raw_input_b64", "variant_id", "vector_id"],
        {
            "vector_id": NON_EMPTY,
            "variant_id": _nullable(NON_EMPTY),
            "raw_input_b64": BASE64,
            "expected_identity": {"$ref": "#/$defs/identity"},
            "expected_basis_bytes_b64": dict(
                BASE64, **{"x-covers": "base64 of the UTF-8 RFC 8785 canonical "
                                       "serialization of expected_identity.basis"}),
            "expected_digest": DIGEST,
        },
    )

    dimension_conditionals = [
        # basis_kind couplings
        {"if": {"properties": {"basis_kind": {"const": "content_reference"}},
                "required": ["basis_kind"]},
         "then": {"properties": {"content_rule": {"$ref": "#/$defs/content_rule"},
                                 "variants": {"type": "null"},
                                 "unobservable_declaration": {"type": "null"}}}},
        {"if": {"properties": {"basis_kind": {"const": "parameter_set"}},
                "required": ["basis_kind"]},
         "then": {"properties": {
             "content_rule": {"type": "null"},
             "unobservable_declaration": {"type": "null"},
             "variants": {"type": "array", "minItems": 1}}}},
        {"if": {"properties": {"basis_kind": {"const": "unobservable"}},
                "required": ["basis_kind"]},
         "then": {"properties": {
             "content_rule": {"type": "null"},
             "variants": {"type": "null"},
             "discriminators": {"maxItems": 0},
             "unobservable_declaration": {"$ref": "#/$defs/unobservable_declaration"}}}},
        # content_reference is admitted for the three content dimensions and only those
        {"if": {"properties": {"dimension": {"enum": list(CONTENT_DIMENSIONS)}},
                "required": ["dimension"]},
         "then": {"properties": {"basis_kind": {"const": "content_reference"}}}},
        {"if": {"properties": {"dimension": {"enum": [d for d in DIMENSIONS
                                                      if d not in CONTENT_DIMENSIONS]}},
                "required": ["dimension"]},
         "then": {"properties": {"basis_kind": {"enum": ["parameter_set", "unobservable"]}}}},
        # absence_permitted is true only for prompt and context
        {"if": {"properties": {"dimension": {"enum": ["context", "prompt"]}},
                "required": ["dimension"]},
         "then": {"properties": {"absence_permitted": {"const": True}}}},
        {"if": {"properties": {"dimension": {"enum": [d for d in DIMENSIONS
                                                      if d not in ("context", "prompt")]}},
                "required": ["dimension"]},
         "then": {"properties": {"absence_permitted": {"const": False}}}},
        # the admitted discriminator subset, pinned per dimension
        {"if": {"properties": {"dimension": {"const": "decoding"}}, "required": ["dimension"]},
         "then": {"properties": {"discriminators": {
             "items": {"enum": ["provider", "requested_model"]}}}}},
        {"if": {"properties": {"dimension": {"const": "implementation"}},
                "required": ["dimension"]},
         "then": {"properties": {"discriminators": {"items": {"enum": ["component"]}}}}},
        {"if": {"properties": {"dimension": {
            "enum": sorted(POLICY_DIMENSIONS + CONTENT_DIMENSIONS)}},
            "required": ["dimension"]},
         "then": {"properties": {"discriminators": {"maxItems": 0}}}},
    ]

    defs["dimension_entry"] = _closed(
        ["absence_permitted", "basis_kind", "content_rule", "dimension",
         "discriminators", "raw_input_shape", "sdk_default_verification",
         "state_rules", "unobservable_declaration", "variants", "vectors"],
        {
            "dimension": {"enum": list(DIMENSIONS)},
            "basis_kind": {"enum": ["content_reference", "parameter_set", "unobservable"]},
            "unobservable_declaration": _nullable({"$ref": "#/$defs/unobservable_declaration"}),
            "sdk_default_verification": _nullable({"$ref": "#/$defs/sdk_default_verification"}),
            "absence_permitted": {"type": "boolean"},
            "raw_input_shape": NON_EMPTY,
            "content_rule": _nullable({"$ref": "#/$defs/content_rule"}),
            "discriminators": {"type": "array", "uniqueItems": True,
                               "x-ordering": "sorted-ascending",
                               "items": {"enum": list(DISCRIMINATORS)}},
            "variants": _nullable({"type": "array", "minItems": 1,
                                   "x-ordering": "sorted-ascending-by:variant_id",
                                   "x-unique-by": "variant_id",
                                   "items": {"$ref": "#/$defs/variant"}}),
            "state_rules": {"$ref": "#/$defs/state_rules"},
            "vectors": {"type": "array", "minItems": 1,
                        "x-ordering": "sorted-ascending-by:vector_id",
                        "x-unique-by": "vector_id",
                        "items": {"$ref": "#/$defs/vector"}},
        },
        allOf=dimension_conditionals,
    )

    return _closed(
        ["canonicalization", "contract_kind", "contract_version",
         "digest_algorithm", "dimensions", "profile_label"],
        {
            "contract_kind": {"enum": ["ion-t4-identity-contract"]},
            "contract_version": NON_EMPTY,
            "profile_label": {"enum": ["ion-t4-runcfg-5"]},
            "digest_algorithm": {"enum": ["sha256"]},
            "canonicalization": {"enum": ["rfc8785"]},
            "dimensions": {
                "type": "array", "minItems": 10, "maxItems": 10,
                "x-ordering": "sorted-ascending-by:dimension (UTF-16 code units)",
                "x-unique-by": "dimension",
                "items": {"$ref": "#/$defs/dimension_entry"},
            },
        },
        **{
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ion.local/schemas/ion_t4_identity_contract.schema.json",
            "title": "ION T4 identity contract",
            "x-specification": "T4 execution mandate v0.3.12, section 13.2",
            "x-enforcement": "ordering and nested uniqueness are declared here and "
                             "enforced mechanically by t4/contract_check.py; JSON "
                             "Schema cannot express either",
            "$defs": defs,
        },
    )


# --------------------------------------------------------------------------- #
# §4 — the run-record schema
# --------------------------------------------------------------------------- #

def _run_record_schema():
    defs = _identity_defs(DIMENSIONS)

    defs["monetary_amount"] = _closed(
        ["scale", "units"],
        {"units": _int(0, 10 ** 15), "scale": _int(0, 9)},
        **{"x-note": "the value is exactly units x 10^(-scale); no rounding, ever"},
    )

    def _measurement(maximum, name):
        return _closed(
            ["source", "status", "unavailable_reason", "value"],
            {
                "value": _nullable(_int(0, maximum)),
                "source": _nullable(NON_EMPTY),
                "status": {"enum": ["available", "unavailable"]},
                "unavailable_reason": _nullable(NON_EMPTY),
            },
            allOf=[
                {"if": {"properties": {"status": {"const": "available"}},
                        "required": ["status"]},
                 "then": {"properties": {"value": _int(0, maximum),
                                         "source": NON_EMPTY,
                                         "unavailable_reason": {"type": "null"}}}},
                {"if": {"properties": {"status": {"const": "unavailable"}},
                        "required": ["status"]},
                 "then": {"properties": {"value": {"type": "null"},
                                         "unavailable_reason": NON_EMPTY}}},
            ],
            **{"x-role": name,
               "x-note": "a zero value with status unavailable is rejected (I1)"},
        )

    defs["token_measurement"] = _measurement(10 ** 9, "input/output tokens")
    defs["total_token_measurement"] = _measurement(2 * 10 ** 9, "total tokens")

    defs["observed_call"] = _closed(
        ["attempt", "call_id", "cost_currency", "cost_kind", "cost_status",
         "cost_unavailable_reason", "cost_value", "input_tokens", "latency_source",
         "latency_status", "latency_unavailable_reason", "model_latency_ms",
         "output_tokens", "pricing_basis_id", "provider", "reported_model",
         "reported_model_unavailable_reason", "requested_model", "sequence",
         "token_consistency_status", "token_sum_of_parts", "total_tokens"],
        {
            "call_id": NON_EMPTY,
            "sequence": _int(1, 1024),
            "attempt": _int(1, 1024),
            "provider": NON_EMPTY,
            "requested_model": NON_EMPTY,
            "reported_model": _nullable(NON_EMPTY),
            "reported_model_unavailable_reason": _nullable(NON_EMPTY),
            "input_tokens": {"$ref": "#/$defs/token_measurement"},
            "output_tokens": {"$ref": "#/$defs/token_measurement"},
            "total_tokens": {"$ref": "#/$defs/total_token_measurement"},
            "token_sum_of_parts": _nullable(_int(0, 2 * 10 ** 9)),
            "token_consistency_status": {
                "enum": ["consistent", "disagreement", "not_evaluable"]},
            "model_latency_ms": _nullable(_int(0, 10 ** 12)),
            "latency_source": _nullable(NON_EMPTY),
            "latency_status": {"enum": ["available", "unavailable"]},
            "latency_unavailable_reason": _nullable(NON_EMPTY),
            "cost_value": _nullable({"$ref": "#/$defs/monetary_amount"}),
            "cost_kind": _nullable({"enum": ["estimated", "observed"]}),
            "cost_currency": _nullable({"type": "string", "pattern": "^[A-Z]{3}$"}),
            "cost_status": {"enum": ["available", "unavailable"]},
            "cost_unavailable_reason": _nullable(NON_EMPTY),
            "pricing_basis_id": _nullable(NON_EMPTY),
        },
        allOf=[
            # B4: a null reported_model carries its reason; a present one does not.
            {"if": {"properties": {"reported_model": {"type": "null"}},
                    "required": ["reported_model"]},
             "then": {"properties": {"reported_model_unavailable_reason": NON_EMPTY}}},
            {"if": {"properties": {"reported_model": NON_EMPTY},
                    "required": ["reported_model"]},
             "then": {"properties": {
                 "reported_model_unavailable_reason": {"type": "null"}}}},
            # latency truth table
            {"if": {"properties": {"latency_status": {"const": "available"}},
                    "required": ["latency_status"]},
             "then": {"properties": {"model_latency_ms": _int(0, 10 ** 12),
                                     "latency_source": NON_EMPTY,
                                     "latency_unavailable_reason": {"type": "null"}}}},
            {"if": {"properties": {"latency_status": {"const": "unavailable"}},
                    "required": ["latency_status"]},
             "then": {"properties": {"model_latency_ms": {"type": "null"},
                                     "latency_unavailable_reason": NON_EMPTY}}},
            # cost truth table
            {"if": {"properties": {"cost_status": {"const": "available"}},
                    "required": ["cost_status"]},
             "then": {"properties": {
                 "cost_value": {"$ref": "#/$defs/monetary_amount"},
                 "cost_kind": {"enum": ["estimated", "observed"]},
                 "cost_currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
                 "cost_unavailable_reason": {"type": "null"}}}},
            {"if": {"properties": {"cost_status": {"const": "unavailable"}},
                    "required": ["cost_status"]},
             "then": {"properties": {"cost_value": {"type": "null"},
                                     "cost_kind": {"type": "null"},
                                     "cost_currency": {"type": "null"},
                                     "pricing_basis_id": {"type": "null"},
                                     "cost_unavailable_reason": NON_EMPTY}}},
            # a pricing basis exists exactly for estimates
            {"if": {"properties": {"cost_kind": {"const": "estimated"}},
                    "required": ["cost_kind"]},
             "then": {"properties": {"pricing_basis_id": NON_EMPTY}}},
            {"if": {"properties": {"cost_kind": {"const": "observed"}},
                    "required": ["cost_kind"]},
             "then": {"properties": {"pricing_basis_id": {"type": "null"}}}},
            # a sum of parts exists only where a comparison is possible
            {"if": {"properties": {
                "token_consistency_status": {"const": "not_evaluable"}},
                "required": ["token_consistency_status"]},
             "then": {"properties": {"token_sum_of_parts": {"type": "null"}}}},
        ],
    )

    defs["planned_component"] = _closed(
        ["component", "implementation_identity", "is_primary"],
        {"component": NON_EMPTY, "is_primary": {"type": "boolean"},
         "implementation_identity": {"$ref": "#/$defs/identity"}},
    )
    defs["planned_call"] = _closed(
        ["decoding_identity", "provider", "requested_model", "sequence"],
        {"sequence": _int(1, 1024), "provider": NON_EMPTY,
         "requested_model": NON_EMPTY,
         "decoding_identity": {"$ref": "#/$defs/identity"}},
    )
    defs["component_result"] = _closed(
        ["component", "incomplete_reason", "outcome"],
        {"component": NON_EMPTY,
         "outcome": {"enum": ["completed", "incomplete"]},
         "incomplete_reason": _nullable(NON_EMPTY)},
        allOf=[
            {"if": {"properties": {"outcome": {"const": "incomplete"}},
                    "required": ["outcome"]},
             "then": {"properties": {"incomplete_reason": NON_EMPTY}}},
            {"if": {"properties": {"outcome": {"const": "completed"}},
                    "required": ["outcome"]},
             "then": {"properties": {"incomplete_reason": {"type": "null"}}}},
        ],
    )
    defs["diagnostic"] = _closed(
        ["code", "detail", "severity"],
        {"code": NON_EMPTY, "severity": {"enum": ["info", "warning"]},
         "detail": NON_EMPTY},
        **{"x-note": "no 'error' severity: an error preventing the write leaves no record"},
    )
    defs["execution_policy"] = _closed(
        ["dispatch_policy_identity", "fallback_policy_identity",
         "retry_policy_identity", "termination_policy_identity",
         "timeout_policy_identity"],
        {"%s_policy_identity" % name: {"$ref": "#/$defs/identity"}
         for name in POLICY_DIMENSIONS},
    )
    defs["run_configuration"] = _closed(
        ["configuration_profile", "context_identity", "execution_policy", "extensions",
         "identity_contract_sha256", "planned_calls", "planned_components",
         "prompt_identity", "workload_identity"],
        {
            "configuration_profile": {"enum": ["ion-t4-runcfg-5"]},
            "identity_contract_sha256": DIGEST,
            "workload_identity": {"$ref": "#/$defs/identity"},
            "prompt_identity": {"$ref": "#/$defs/identity"},
            "context_identity": {"$ref": "#/$defs/identity"},
            "planned_components": {"type": "array", "minItems": 1, "maxItems": 1024,
                                   "x-ordering": "sorted-ascending-by:component",
                                   "x-unique-by": "component",
                                   "items": {"$ref": "#/$defs/planned_component"}},
            "planned_calls": {"type": "array", "minItems": 1, "maxItems": 1024,
                              "x-ordering": "ascending-by:sequence",
                              "items": {"$ref": "#/$defs/planned_call"}},
            "execution_policy": {"$ref": "#/$defs/execution_policy"},
            "extensions": {"type": "array", "maxItems": 0},
        },
    )
    defs["emission_result"] = _closed(
        ["diagnostics", "emission_status", "unavailable_measurements"],
        {
            "emission_status": {"enum": ["complete", "degraded", "incomplete"]},
            "unavailable_measurements": {"type": "array", "uniqueItems": True,
                                         "items": NON_EMPTY},
            "diagnostics": {"type": "array", "items": {"$ref": "#/$defs/diagnostic"}},
        },
        allOf=[
            {"if": {"properties": {"emission_status": {"const": "complete"}},
                    "required": ["emission_status"]},
             "then": {"properties": {"unavailable_measurements": {"maxItems": 0},
                                     "diagnostics": {"maxItems": 0}}}},
            {"if": {"properties": {"emission_status": {"const": "incomplete"}},
                    "required": ["emission_status"]},
             "then": {"properties": {"unavailable_measurements": {"minItems": 1},
                                     "diagnostics": {"maxItems": 0}}}},
            {"if": {"properties": {"emission_status": {"const": "degraded"}},
                    "required": ["emission_status"]},
             "then": {"properties": {"unavailable_measurements": {"maxItems": 0},
                                     "diagnostics": {"minItems": 1}}}},
        ],
    )
    defs["provenance"] = _closed(
        ["contract_schema_name", "contract_schema_sha256", "contract_schema_version",
         "emitter_name", "emitter_sha256", "emitter_version",
         "schema_name", "schema_sha256", "schema_version"],
        {
            "emitter_name": NON_EMPTY, "emitter_version": NON_EMPTY,
            "emitter_sha256": DIGEST,
            "schema_name": NON_EMPTY, "schema_version": NON_EMPTY,
            "schema_sha256": DIGEST,
            "contract_schema_name": NON_EMPTY, "contract_schema_version": NON_EMPTY,
            "contract_schema_sha256": DIGEST,
        },
    )

    return _closed(
        ["available_cost_subtotal", "calls", "component_results", "emission_result",
         "planned_cost", "provenance", "record_origin", "run_configuration",
         "run_fingerprint", "run_id", "run_status", "supersedes_run_id", "timestamp",
         "total_cost_composition", "total_cost_currency", "total_cost_missing_call_ids",
         "total_cost_missing_providers", "total_cost_status",
         "total_cost_unavailable_reason", "total_cost_value", "total_wall_clock_ms",
         "wall_clock_source", "wall_clock_status", "wall_clock_unavailable_reason"],
        {
            "record_origin": {
                "enum": ["recorded_fixture", "synthetic"],
                "x-note": "the third vocabulary value, live_observed, is invalid for "
                          "any T4 artifact under D3 and is therefore not admitted here",
            },
            "run_id": NON_EMPTY,
            "run_fingerprint": DIGEST,
            "supersedes_run_id": _nullable(NON_EMPTY),
            "timestamp": {"type": "string",
                          "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?"
                                     r"(Z|\+00:00)$"},
            "run_configuration": {"$ref": "#/$defs/run_configuration"},
            "run_status": {"enum": ["failed", "partial", "success"]},
            "component_results": {"type": "array", "minItems": 1, "maxItems": 1024,
                                  "items": {"$ref": "#/$defs/component_result"}},
            "calls": {"type": "array", "maxItems": 1024,
                      "x-ordering": "ascending-by:(sequence, attempt)",
                      "items": {"$ref": "#/$defs/observed_call"}},
            "total_wall_clock_ms": _nullable(_int(0, 10 ** 12)),
            "wall_clock_source": _nullable(NON_EMPTY),
            "wall_clock_status": {"enum": ["available", "unavailable"]},
            "wall_clock_unavailable_reason": _nullable(NON_EMPTY),
            "total_cost_status": {"enum": ["available", "partial", "unavailable"]},
            "total_cost_value": _nullable({"$ref": "#/$defs/monetary_amount"}),
            "available_cost_subtotal": _nullable({"$ref": "#/$defs/monetary_amount"}),
            "total_cost_currency": _nullable({"type": "string", "pattern": "^[A-Z]{3}$"}),
            "total_cost_composition": _nullable(
                {"enum": ["estimated", "mixed", "observed"]}),
            "total_cost_missing_providers": {"type": "array", "uniqueItems": True,
                                             "items": NON_EMPTY},
            "total_cost_missing_call_ids": {"type": "array", "uniqueItems": True,
                                            "items": NON_EMPTY},
            "total_cost_unavailable_reason": _nullable(NON_EMPTY),
            "planned_cost": {"type": "null"},
            "emission_result": {"$ref": "#/$defs/emission_result"},
            "provenance": {"$ref": "#/$defs/provenance"},
        },
        allOf=[
            # wall-clock truth table
            {"if": {"properties": {"wall_clock_status": {"const": "available"}},
                    "required": ["wall_clock_status"]},
             "then": {"properties": {"total_wall_clock_ms": _int(0, 10 ** 12),
                                     "wall_clock_source": NON_EMPTY,
                                     "wall_clock_unavailable_reason": {"type": "null"}}}},
            {"if": {"properties": {"wall_clock_status": {"const": "unavailable"}},
                    "required": ["wall_clock_status"]},
             "then": {"properties": {"total_wall_clock_ms": {"type": "null"},
                                     "wall_clock_unavailable_reason": NON_EMPTY}}},
            # aggregate derivation, the three exhaustive states
            {"if": {"properties": {"total_cost_status": {"const": "available"}},
                    "required": ["total_cost_status"]},
             "then": {"properties": {
                 "total_cost_value": {"$ref": "#/$defs/monetary_amount"},
                 "available_cost_subtotal": {"type": "null"},
                 "total_cost_currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
                 "total_cost_composition": {"enum": ["estimated", "mixed", "observed"]},
                 "total_cost_missing_providers": {"maxItems": 0},
                 "total_cost_missing_call_ids": {"maxItems": 0},
                 "total_cost_unavailable_reason": {"type": "null"}}}},
            {"if": {"properties": {"total_cost_status": {"const": "partial"}},
                    "required": ["total_cost_status"]},
             "then": {"properties": {
                 "total_cost_value": {"type": "null"},
                 "available_cost_subtotal": {"$ref": "#/$defs/monetary_amount"},
                 "total_cost_currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
                 "total_cost_missing_call_ids": {"minItems": 1},
                 "total_cost_missing_providers": {"minItems": 1}}}},
            {"if": {"properties": {"total_cost_status": {"const": "unavailable"}},
                    "required": ["total_cost_status"]},
             "then": {"properties": {
                 "total_cost_value": {"type": "null"},
                 "available_cost_subtotal": {"type": "null"},
                 "total_cost_currency": {"type": "null"},
                 "total_cost_composition": {"type": "null"},
                 "total_cost_unavailable_reason": NON_EMPTY}}},
        ],
        **{
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://ion.local/schemas/ion_t4_run_record.schema.json",
            "title": "ION T4 run record",
            "x-specification": "T4 execution mandate v0.3.12, section 4",
            "x-enforcement": "derivations and referential rules JSON Schema cannot "
                             "express are enforced by t4/emitter.py; see "
                             "t4.schema_sources.CODE_ENFORCED_RULES",
            "$defs": defs,
        },
    )


IDENTITY_CONTRACT_META_SCHEMA = _meta_schema()
RUN_RECORD_SCHEMA = _run_record_schema()

#: Rules that are part of §4 but are not expressible in JSON Schema. Each is
#: enforced in `t4/emitter.py` and asserted by a test. Listed so the split between
#: schema-enforced and code-enforced is a stated fact rather than an assumption.
CODE_ENFORCED_RULES = (
    "run_status derived from component_results and planned primaries (§4.3)",
    "component_results correspond one-to-one with planned_components, in order (T22)",
    "aggregate cost derived exhaustively from calls, exact aligned integer sum (§4.7)",
    "run_fingerprint = SHA-256 of JCS(run_configuration), recomputed (T58, T59)",
    "every identity digest = SHA-256 of JCS(basis), recomputed (T70)",
    "key_set_variant equals the variant selected independently from discriminators (T86)",
    "planned_calls sequences consecutive from 1; calls ordered by (sequence, attempt)",
    "call_id unique independently of (sequence, attempt) (T60)",
    "observed provider and requested_model are verified echoes of the plan (T52)",
    "a locally_derived total token count satisfies total = input + output (T47)",
    "measurement paths in unavailable_measurements resolve and are non-duplicated (§4.4)",
    "supersedes_run_id resolves to a stored record at write time (T53)",
    "duplicate run_id is rejected, not merged (I7)",
    "stored bytes are the RFC 8785 canonical serialization (I16, T82)",
)
