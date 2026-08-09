"""Mechanical pre-freeze validation of an identity contract — mandate section 13.6.

Implements items 1-10 of the pre-freeze checklist. Item 11 (the stored bytes are
canonical) is a property of the file rather than of the parsed document and is
checked by :func:`stored_bytes_are_canonical`.

**Item 1 is checked structurally, not against a registered meta-schema artifact.**
Section 13.2 specifies the meta-schema field by field; the checks below enforce
that specification directly — closedness at every object level, field presence,
types, bounds, pinned enums, ordering and uniqueness. What they are not is a
validation against the meta-schema *artifact* of section 7 item 2, which does not
exist: authoring and registering it belongs to the freeze, and the freeze is
blocked (see the report). Where item 1 says "valid against the meta-schema", read
"conforms to section 13.2 as enforced here".

**Item 10 is checked against a pattern set, not against a recorded classification.**
Section 13.6 item 10 says the check runs "against the classification recorded in
Phase 0". No machine-readable record of that classification exists in this
repository, so what runs here is the weaker, conservative half: no key, meaning,
note, unit, raw input or parameter value matches a known credential-bearing name
or shape. The residue is RO-1's, and is reported as such rather than counted as
passed.

Nothing here mutates the contract. A failed check is a finding, never a repair.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from typing import Any

from . import jcs

__all__ = ["CheckResult", "check_contract", "stored_bytes_are_canonical"]


# The ten dimensions of section 4.2B.
DIMENSIONS = (
    "context", "decoding", "dispatch", "fallback", "implementation",
    "prompt", "retry", "termination", "timeout", "workload",
)
CONTENT_DIMENSIONS = frozenset({"workload", "prompt", "context"})
ABSENCE_PERMITTED = frozenset({"prompt", "context"})
ADMITTED_DISCRIMINATORS = {
    "decoding": frozenset({"provider", "requested_model"}),
    "implementation": frozenset({"component"}),
}
DISCRIMINATOR_ENUM = ("component", "provider", "requested_model")
SOURCE_ENUM = frozenset({
    "explicit", "call_site", "environment",
    "config_file", "provider_default", "library_default",
})
VALUE_TYPES = frozenset({"integer", "decimal", "boolean", "string", "null_value"})
BASIS_KINDS = frozenset({"absence", "content_reference", "parameter_set", "unobservable"})
RESOLUTION_STATES = frozenset({
    "explicit_value", "explicitly_disabled",
    "verified_sdk_default", "provider_managed_unobservable",
})
ADMITTED_PROFILE_LABEL = "ion-t4-runcfg-5"

# (presence, basis_kind) -> admissible resolution states, section 4.2B coupling table.
COUPLING = {
    ("absent", "absence"): frozenset({"explicitly_disabled"}),
    ("present", "content_reference"): frozenset({"explicit_value"}),
    ("present", "parameter_set"): frozenset({"explicit_value", "verified_sdk_default"}),
    ("present", "unobservable"): frozenset({"provider_managed_unobservable"}),
}

DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
INTEGER_RE = re.compile(r"\A-?(0|[1-9][0-9]*)\Z")
DECIMAL_RE = re.compile(r"\A-?(0|[1-9][0-9]*)\.[0-9]*[1-9]\Z")
BYTE_LENGTH_MAX = 10 ** 12

# Conservative credential-name patterns for item 10's mechanical half.
SECRET_NAME_RE = re.compile(
    r"api[_-]?key|secret|passwd|password|passphrase|credential|"
    r"\btoken\b|bearer|authorization|private[_-]?key|cookie|session[_-]?id",
    re.IGNORECASE,
)
SECRET_SHAPE_RE = re.compile(
    r"sk-[A-Za-z0-9]{16,}|AIza[A-Za-z0-9_\-]{20,}|"
    r"[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s@]+@",
)


class CheckResult:
    """Findings from one contract validation. Empty findings means every check passed."""

    def __init__(self) -> None:
        self.findings: list[str] = []
        self.checks_run: list[str] = []

    def note(self, item: str) -> None:
        if item not in self.checks_run:
            self.checks_run.append(item)

    def fail(self, item: str, detail: str) -> None:
        self.note(item)
        self.findings.append(f"[{item}] {detail}")

    def require(self, condition: bool, item: str, detail: str) -> bool:
        self.note(item)
        if not condition:
            self.findings.append(f"[{item}] {detail}")
        return condition

    @property
    def passed(self) -> bool:
        return not self.findings


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _closed(result: CheckResult, item: str, where: str, obj: Any,
            required: tuple[str, ...]) -> bool:
    """Every required field present, and no field beyond them (closed both ways)."""
    if not isinstance(obj, dict):
        result.fail(item, f"{where}: expected an object, got {type(obj).__name__}")
        return False
    present, expected = set(obj), set(required)
    ok = True
    for missing in sorted(expected - present):
        result.fail(item, f"{where}: missing required field {missing!r}")
        ok = False
    for unknown in sorted(present - expected):
        result.fail(item, f"{where}: unknown key {unknown!r}")
        ok = False
    return ok


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _sorted_utf16(values: list[str]) -> bool:
    keys = [v.encode("utf-16-be") for v in values]
    return keys == sorted(keys)


def _decode_b64(result: CheckResult, item: str, where: str, text: Any) -> bytes | None:
    """RFC 4648 standard alphabet, padded, no whitespace and no line breaks."""
    if not isinstance(text, str):
        result.fail(item, f"{where}: base64 field is not a string")
        return None
    if text != text.strip() or any(c.isspace() for c in text):
        result.fail(item, f"{where}: base64 carries whitespace or line breaks")
        return None
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        result.fail(item, f"{where}: base64 does not decode: {exc}")
        return None
    if base64.b64encode(raw).decode("ascii") != text:
        result.fail(item, f"{where}: base64 is not the canonical padded encoding")
        return None
    return raw


def _scan_secret(result: CheckResult, where: str, text: Any) -> None:
    if not isinstance(text, str):
        return
    if SECRET_NAME_RE.search(text):
        result.fail("10", f"{where}: matches a credential-bearing name pattern: {text[:60]!r}")
    if SECRET_SHAPE_RE.search(text):
        result.fail("10", f"{where}: matches a credential shape pattern")


# --------------------------------------------------------------------------- #
# section 4.2B basis / identity checks, used by item 8
# --------------------------------------------------------------------------- #

def _check_parameters(result: CheckResult, where: str, params: Any,
                      expected_keys: set[str] | None) -> None:
    if not isinstance(params, list):
        result.fail("8", f"{where}: parameters is not an array")
        return
    if len(params) > 256:
        result.fail("8", f"{where}: parameters exceeds the 256-entry bound")
    keys: list[str] = []
    for index, entry in enumerate(params):
        spot = f"{where}.parameters[{index}]"
        if not _closed(result, "8", spot, entry, ("key", "value", "value_type")):
            continue
        key, value, value_type = entry["key"], entry["value"], entry["value_type"]
        if not _nonempty_string(key):
            result.fail("8", f"{spot}: key is empty")
            continue
        keys.append(key)
        if value_type not in VALUE_TYPES:
            result.fail("8", f"{spot}: unknown value_type {value_type!r}")
            continue
        if not isinstance(value, str):
            result.fail("8", f"{spot}: value is not a string (a raw JSON number is refused)")
            continue
        if value_type == "integer" and not INTEGER_RE.match(value):
            result.fail("8", f"{spot}: {value!r} is not a canonical integer")
        elif value_type == "decimal" and not DECIMAL_RE.match(value):
            result.fail("8", f"{spot}: {value!r} is not a canonical decimal")
        elif value_type == "boolean" and value not in ("true", "false"):
            result.fail("8", f"{spot}: {value!r} is not a boolean")
        elif value_type == "null_value" and value != "":
            result.fail("8", f"{spot}: null_value must be the empty string")
    if len(set(keys)) != len(keys):
        result.fail("8", f"{where}: duplicate parameter keys")
    if not _sorted_utf16(keys):
        result.fail("8", f"{where}: parameter keys are not sorted ascending")
    if expected_keys is not None and set(keys) != expected_keys:
        missing = sorted(expected_keys - set(keys))
        extra = sorted(set(keys) - expected_keys)
        result.fail("8", f"{where}: key set differs from the variant's "
                         f"(missing={missing}, extra={extra})")


def _check_basis(result: CheckResult, where: str, basis: Any, dimension: str,
                 variants_by_id: dict[str, set[str]]) -> None:
    if not _closed(result, "8", where, basis,
                   ("basis_kind", "content", "dimension", "key_set_variant", "parameters")):
        return
    kind = basis["basis_kind"]
    if kind not in BASIS_KINDS:
        result.fail("8", f"{where}: unknown basis_kind {kind!r}")
        return
    if basis["dimension"] != dimension:
        result.fail("8", f"{where}: basis dimension {basis['dimension']!r} "
                         f"disagrees with {dimension!r}")

    variant = basis["key_set_variant"]
    content = basis["content"]

    if kind == "parameter_set":
        if not _nonempty_string(variant):
            result.fail("8", f"{where}: parameter_set carries no key_set_variant")
            expected = None
        elif variant not in variants_by_id:
            result.fail("8", f"{where}: key_set_variant {variant!r} names no variant")
            expected = None
        else:
            expected = variants_by_id[variant]
        if content is not None:
            result.fail("8", f"{where}: parameter_set carries content")
        _check_parameters(result, where, basis["parameters"], expected)
        if isinstance(basis["parameters"], list) and not basis["parameters"]:
            result.fail("8", f"{where}: parameter_set carries an empty key set")
    else:
        if variant is not None:
            result.fail("8", f"{where}: {kind} carries a key_set_variant")
        if basis["parameters"] != []:
            result.fail("8", f"{where}: {kind} carries parameters")
        if kind == "content_reference":
            if not _closed(result, "8", f"{where}.content", content,
                           ("byte_length", "content_digest")):
                return
            length = content["byte_length"]
            if isinstance(length, bool) or not isinstance(length, (int, float)) \
                    or float(length) != int(length):
                result.fail("8", f"{where}.content: byte_length is not an integer")
            elif not 0 <= int(length) <= BYTE_LENGTH_MAX:
                result.fail("8", f"{where}.content: byte_length {int(length)} out of domain")
            if not (isinstance(content["content_digest"], str)
                    and DIGEST_RE.match(content["content_digest"])):
                result.fail("8", f"{where}.content: content_digest is not 64 lowercase hex")
        elif content is not None:
            result.fail("8", f"{where}: {kind} carries content")


def _check_identity(result: CheckResult, where: str, identity: Any, dimension: str,
                    variants_by_id: dict[str, set[str]]) -> None:
    if not _closed(result, "8", where, identity,
                   ("basis", "digest", "dimension", "presence", "resolution_state")):
        return
    if identity["dimension"] != dimension:
        result.fail("8", f"{where}: identity dimension disagrees with its dimension entry")
    presence, state = identity["presence"], identity["resolution_state"]
    if presence not in ("present", "absent"):
        result.fail("8", f"{where}: unknown presence {presence!r}")
    if state not in RESOLUTION_STATES:
        result.fail("8", f"{where}: unknown resolution_state {state!r}")
    if presence == "absent" and dimension not in ABSENCE_PERMITTED:
        result.fail("8", f"{where}: absent is not permitted for {dimension!r}")

    basis = identity["basis"]
    _check_basis(result, f"{where}.basis", basis, dimension, variants_by_id)

    if isinstance(basis, dict) and basis.get("basis_kind") in BASIS_KINDS:
        admissible = COUPLING.get((presence, basis["basis_kind"]))
        if admissible is None:
            result.fail("8", f"{where}: ({presence}, {basis['basis_kind']}) is "
                             f"not an admissible pair")
        elif state not in admissible:
            result.fail("8", f"{where}: resolution_state {state!r} is not admissible "
                             f"for ({presence}, {basis['basis_kind']})")


# --------------------------------------------------------------------------- #
# the checklist
# --------------------------------------------------------------------------- #

def _check_vector(result: CheckResult, dimension: str, entry: dict, vector: Any,
                  variants_by_id: dict[str, set[str]]) -> None:
    where = f"{dimension}.vectors[{vector.get('vector_id') if isinstance(vector, dict) else '?'}]"
    result.note("8")
    if not _closed(result, "8", where, vector,
                   ("expected_basis_bytes_b64", "expected_digest", "expected_identity",
                    "raw_input_b64", "variant_id", "vector_id")):
        return
    if not _nonempty_string(vector["vector_id"]):
        result.fail("8", f"{where}: vector_id is empty")

    is_parameter_set = entry["basis_kind"] == "parameter_set"
    variant_id = vector["variant_id"]
    if is_parameter_set:
        if not _nonempty_string(variant_id):
            result.fail("8", f"{where}: a parameter_set vector carries no variant_id")
        elif variant_id not in variants_by_id:
            result.fail("8", f"{where}: variant_id {variant_id!r} names no variant")
    elif variant_id is not None:
        result.fail("8", f"{where}: variant_id is non-null on a {entry['basis_kind']} dimension")

    _check_identity(result, f"{where}.expected_identity", vector["expected_identity"],
                    dimension, variants_by_id)

    basis_bytes = _decode_b64(result, "8", f"{where}.expected_basis_bytes_b64",
                              vector["expected_basis_bytes_b64"])
    identity = vector["expected_identity"]
    if basis_bytes is not None and isinstance(identity, dict) and "basis" in identity:
        recomputed = jcs.serialize(identity["basis"])
        if recomputed != basis_bytes:
            result.fail("8", f"{where}: expected_basis_bytes_b64 does not decode to "
                             f"JCS(expected_identity.basis)")
        digest = hashlib.sha256(basis_bytes).hexdigest()
        if vector["expected_digest"] != digest:
            result.fail("8", f"{where}: expected_digest {vector['expected_digest']!r} "
                             f"is not SHA-256 of the decoded bytes ({digest})")
        if identity.get("digest") != vector["expected_digest"]:
            result.fail("8", f"{where}: expected_identity.digest differs from expected_digest")
    if isinstance(vector["expected_digest"], str) \
            and not DIGEST_RE.match(vector["expected_digest"]):
        result.fail("8", f"{where}: expected_digest is not 64 lowercase hex")

    raw = _decode_b64(result, "8", f"{where}.raw_input_b64", vector["raw_input_b64"])
    if raw is not None:
        try:
            if jcs.canonicalize(raw) != raw:
                result.fail("8", f"{where}: raw_input_b64 does not decode to canonical JSON")
        except jcs.CanonicalizationError as exc:
            result.fail("8", f"{where}: raw_input_b64 is not admissible JSON: {exc}")
        _scan_secret(result, f"{where}.raw_input", raw.decode("utf-8", "replace"))


def _check_dimension(result: CheckResult, entry: Any, index: int) -> str | None:
    where = f"dimensions[{index}]"
    if not _closed(result, "1", where, entry, (
            "absence_permitted", "basis_kind", "content_rule", "dimension",
            "discriminators", "raw_input_shape", "sdk_default_verification",
            "state_rules", "unobservable_declaration", "variants", "vectors")):
        return None

    dimension = entry["dimension"]
    if dimension not in DIMENSIONS:
        result.fail("3", f"{where}: unknown dimension {dimension!r}")
        return None
    where = dimension

    kind = entry["basis_kind"]
    if kind not in ("content_reference", "parameter_set", "unobservable"):
        result.fail("1", f"{where}: basis_kind {kind!r} is not admissible on a dimension entry")
        return dimension
    if dimension in CONTENT_DIMENSIONS and kind != "content_reference":
        result.fail("1", f"{where}: a content dimension must be content_reference")
    if dimension not in CONTENT_DIMENSIONS and kind == "content_reference":
        result.fail("1", f"{where}: content_reference is admitted only for the three "
                         f"content dimensions")

    result.require(entry["absence_permitted"] is (dimension in ABSENCE_PERMITTED),
                   "1", f"{where}: absence_permitted must be true only for prompt and context")
    result.require(_nonempty_string(entry["raw_input_shape"]),
                   "1", f"{where}: raw_input_shape is empty")

    # --- state_rules (closed; `absent` non-null exactly when absence is permitted)
    rules = entry["state_rules"]
    if _closed(result, "1", f"{where}.state_rules", rules,
               ("absent", "default", "disabled", "unknown")):
        for field in ("default", "disabled", "unknown"):
            result.require(_nonempty_string(rules[field]), "1",
                           f"{where}.state_rules.{field} is empty")
        if dimension in ABSENCE_PERMITTED:
            result.require(_nonempty_string(rules["absent"]), "1",
                           f"{where}.state_rules.absent must be non-null here")
        else:
            result.require(rules["absent"] is None, "1",
                           f"{where}.state_rules.absent must be null here")

    # --- content_rule: item 4
    rule = entry["content_rule"]
    if kind == "content_reference":
        if result.require(rule is not None, "4",
                          f"{where}: a content_reference dimension needs a content_rule") \
                and _closed(result, "4", f"{where}.content_rule", rule,
                            ("absence_case", "byte_coverage", "empty_case", "encoding")):
            for field in ("byte_coverage", "empty_case", "encoding"):
                result.require(_nonempty_string(rule[field]), "4",
                               f"{where}.content_rule.{field} is empty")
            if dimension in ABSENCE_PERMITTED:
                result.require(_nonempty_string(rule["absence_case"]), "4",
                               f"{where}.content_rule.absence_case must be non-null here")
            else:
                result.require(rule["absence_case"] is None, "4",
                               f"{where}.content_rule.absence_case must be null here")
        result.require(entry["variants"] is None, "4",
                       f"{where}: a content_reference dimension carries no variants")
    else:
        result.require(rule is None, "4",
                       f"{where}: content_rule must be null for {kind}")

    # --- discriminators: item 5
    discriminators = entry["discriminators"]
    if isinstance(discriminators, list):
        admitted = ADMITTED_DISCRIMINATORS.get(dimension, frozenset())
        if kind == "unobservable":
            result.require(discriminators == [], "4a",
                           f"{where}: an unobservable dimension declares no discriminators")
        for name in discriminators:
            if name not in DISCRIMINATOR_ENUM:
                result.fail("5", f"{where}: {name!r} is not a discriminator")
            elif name not in admitted:
                result.fail("5", f"{where}: discriminator {name!r} is outside the "
                                 f"admitted subset {sorted(admitted)}")
        result.require(len(set(discriminators)) == len(discriminators), "5",
                       f"{where}: duplicate discriminators")
        result.require(_sorted_utf16([d for d in discriminators if isinstance(d, str)]),
                       "5", f"{where}: discriminators are not sorted")
    else:
        result.fail("1", f"{where}: discriminators is not an array")
        discriminators = []

    # --- unobservable_declaration: item 4a
    declaration = entry["unobservable_declaration"]
    if kind == "unobservable":
        if result.require(declaration is not None, "4a",
                          f"{where}: an unobservable dimension needs a declaration") \
                and _closed(result, "4a", f"{where}.unobservable_declaration",
                            declaration, ("evidence", "reason")):
            for field in ("evidence", "reason"):
                result.require(_nonempty_string(declaration[field]), "4a",
                               f"{where}.unobservable_declaration.{field} is empty")
        result.require(entry["variants"] is None, "4a",
                       f"{where}: an unobservable dimension carries no variants")
    else:
        result.require(declaration is None, "4a",
                       f"{where}: unobservable_declaration must be null for {kind}")

    # --- variants and key sets: items 4, 9
    variants_by_id: dict[str, set[str]] = {}
    variants = entry["variants"]
    library_default_first = False
    if kind == "parameter_set":
        if not (isinstance(variants, list) and variants):
            result.fail("4", f"{where}: a parameter_set dimension needs at least one variant")
            variants = []
        ids = []
        for v_index, variant in enumerate(variants):
            spot = f"{where}.variants[{v_index}]"
            if not _closed(result, "1", spot, variant, ("keys", "selector", "variant_id")):
                continue
            variant_id = variant["variant_id"]
            if not _nonempty_string(variant_id):
                result.fail("1", f"{spot}: variant_id is empty")
                continue
            ids.append(variant_id)

            # selector: exactly one condition per declared discriminator (item 5)
            selector = variant["selector"]
            if not isinstance(selector, list):
                result.fail("5", f"{spot}: selector is not an array")
                selector = []
            named = [c.get("discriminator") for c in selector if isinstance(c, dict)]
            result.require(sorted(named) == sorted(discriminators), "5",
                           f"{spot}: selector must carry exactly one condition per declared "
                           f"discriminator (declared={sorted(discriminators)}, got={sorted(named)})")
            result.require(_sorted_utf16([n for n in named if isinstance(n, str)]), "5",
                           f"{spot}: selector is not sorted by discriminator")
            for c_index, condition in enumerate(selector):
                c_spot = f"{spot}.selector[{c_index}]"
                if not _closed(result, "5", c_spot, condition,
                               ("discriminator", "match", "value")):
                    continue
                if condition["match"] == "exact":
                    result.require(_nonempty_string(condition["value"]), "5",
                                   f"{c_spot}: match 'exact' needs a non-empty value")
                elif condition["match"] == "any":
                    result.require(condition["value"] is None, "5",
                                   f"{c_spot}: match 'any' must carry a null value")
                else:
                    result.fail("5", f"{c_spot}: unknown match mode {condition['match']!r}")

            # keys
            keys = variant["keys"]
            if not (isinstance(keys, list) and keys):
                result.fail("4", f"{spot}: variant carries an empty key set")
                keys = []
            names = []
            for k_index, key_entry in enumerate(keys):
                k_spot = f"{spot}.keys[{k_index}]"
                if not _closed(result, "1", k_spot, key_entry,
                               ("default_resolution", "key", "meaning", "unit", "value_type")):
                    continue
                names.append(key_entry["key"])
                result.require(_nonempty_string(key_entry["key"]), "1", f"{k_spot}: key is empty")
                result.require(_nonempty_string(key_entry["meaning"]), "1",
                               f"{k_spot}: meaning is empty")
                result.require(key_entry["value_type"] in VALUE_TYPES, "1",
                               f"{k_spot}: unknown value_type {key_entry['value_type']!r}")
                unit = key_entry["unit"]
                result.require(unit is None or _nonempty_string(unit), "1",
                               f"{k_spot}: unit must be null or a non-empty string")
                for field, text in (("key", key_entry["key"]), ("meaning", key_entry["meaning"]),
                                    ("unit", unit)):
                    _scan_secret(result, f"{k_spot}.{field}", text)

                # item 9
                resolution = key_entry["default_resolution"]
                if _closed(result, "9", f"{k_spot}.default_resolution", resolution,
                           ("note", "readable_at_emission", "sources")):
                    sources = resolution["sources"]
                    if not (isinstance(sources, list) and sources):
                        result.fail("9", f"{k_spot}: sources is empty")
                    else:
                        for source in sources:
                            if source not in SOURCE_ENUM:
                                result.fail("9", f"{k_spot}: unknown source {source!r}")
                        result.require(len(set(sources)) == len(sources), "9",
                                       f"{k_spot}: duplicate sources")
                        if sources[0] == "library_default":
                            library_default_first = True
                    result.require(resolution["readable_at_emission"] is True, "9",
                                   f"{k_spot}: readable_at_emission must be true")
                    result.require(resolution["note"] is None
                                   or _nonempty_string(resolution["note"]), "9",
                                   f"{k_spot}: note must be null or non-empty")
                    _scan_secret(result, f"{k_spot}.note", resolution["note"])

            result.require(len(set(names)) == len(names), "1", f"{spot}: duplicate keys")
            result.require(_sorted_utf16([n for n in names if isinstance(n, str)]), "1",
                           f"{spot}: keys are not sorted")
            variants_by_id[variant_id] = {n for n in names if isinstance(n, str)}

        result.require(len(set(ids)) == len(ids), "1", f"{where}: duplicate variant_id")
        result.require(_sorted_utf16(ids), "1", f"{where}: variants are not sorted by variant_id")

        # item 6 — pairwise mutual exclusivity
        selectors = [(v["variant_id"], v["selector"]) for v in variants
                     if isinstance(v, dict) and isinstance(v.get("selector"), list)]
        for i in range(len(selectors)):
            for j in range(i + 1, len(selectors)):
                if _can_both_match(selectors[i][1], selectors[j][1]):
                    result.fail("6", f"{where}: selectors of {selectors[i][0]!r} and "
                                     f"{selectors[j][0]!r} can both match one assignment")
        result.note("6")
    else:
        result.require(variants is None, "4",
                       f"{where}: variants must be null for {kind}")

    # --- item 4b
    verification = entry["sdk_default_verification"]
    if library_default_first:
        if result.require(verification is not None, "4b",
                          f"{where}: a key names library_default first, so "
                          f"sdk_default_verification is required") \
                and _closed(result, "4b", f"{where}.sdk_default_verification", verification,
                            ("library", "vector_id", "version")):
            for field in ("library", "vector_id", "version"):
                result.require(_nonempty_string(verification[field]), "4b",
                               f"{where}.sdk_default_verification.{field} is empty")
    else:
        result.require(verification is None, "4b",
                       f"{where}: no key names library_default first, so "
                       f"sdk_default_verification must be null")

    # --- vectors: items 7, 8, 4a
    vectors = entry["vectors"]
    if not (isinstance(vectors, list) and vectors):
        result.fail("7", f"{where}: dimension carries no vector")
        return dimension
    vector_ids = [v.get("vector_id") for v in vectors if isinstance(v, dict)]
    result.require(len(set(vector_ids)) == len(vector_ids), "1",
                   f"{where}: duplicate vector_id")
    result.require(_sorted_utf16([v for v in vector_ids if isinstance(v, str)]), "1",
                   f"{where}: vectors are not sorted by vector_id")
    for vector in vectors:
        if isinstance(vector, dict):
            _check_vector(result, dimension, entry, vector, variants_by_id)

    covered = {v.get("variant_id") for v in vectors if isinstance(v, dict)}
    for variant_id in variants_by_id:
        result.require(variant_id in covered, "7",
                       f"{where}: variant {variant_id!r} carries no vector")

    if kind == "unobservable":
        conforming = [
            v for v in vectors
            if isinstance(v, dict) and isinstance(v.get("expected_identity"), dict)
            and isinstance(v["expected_identity"].get("basis"), dict)
            and v["expected_identity"]["basis"].get("basis_kind") == "unobservable"
            and v["expected_identity"].get("resolution_state") == "provider_managed_unobservable"
            and v["expected_identity"]["basis"].get("parameters") == []
            and v["expected_identity"]["basis"].get("content") is None
            and v["expected_identity"]["basis"].get("key_set_variant") is None
        ]
        result.require(bool(conforming), "4a",
                       f"{where}: an unobservable dimension needs at least one vector whose "
                       f"expected_identity is the single legal unobservable form")

    return dimension


def _can_both_match(left: list, right: list) -> bool:
    """True when one discriminator assignment satisfies both selectors."""
    by_name = {}
    for condition in left:
        if isinstance(condition, dict):
            by_name[condition.get("discriminator")] = condition
    for condition in right:
        if not isinstance(condition, dict):
            continue
        other = by_name.get(condition.get("discriminator"))
        if other is None:
            continue
        if other.get("match") == "exact" and condition.get("match") == "exact" \
                and other.get("value") != condition.get("value"):
            return False  # this discriminator alone separates them
    return True


def check_contract(contract: Any, meta_schema: Any = None) -> CheckResult:
    """Run section 13.6 items 1-10 over a parsed contract document.

    When ``meta_schema`` is supplied, item 1 is checked against that artifact as
    well as structurally. When it is not, item 1 is the structural checks alone —
    which is weaker, and is why the caller is expected to supply it.
    """
    result = CheckResult()

    if meta_schema is not None:
        import jsonschema

        validator = jsonschema.Draft202012Validator(meta_schema)
        for error in sorted(validator.iter_errors(contract),
                            key=lambda e: list(e.absolute_path)):
            location = "/".join(str(p) for p in error.absolute_path) or "<root>"
            result.fail("1", f"meta-schema: invalid at '{location}': {error.message}")
        result.note("1")

    # --- item 1 (top level) and item 2
    if not _closed(result, "1", "<root>", contract, (
            "canonicalization", "contract_kind", "contract_version",
            "digest_algorithm", "dimensions", "profile_label")):
        return result

    result.require(contract["contract_kind"] == "ion-t4-identity-contract", "2",
                   f"contract_kind is {contract['contract_kind']!r}")
    result.require(contract["digest_algorithm"] == "sha256", "2",
                   f"digest_algorithm is {contract['digest_algorithm']!r}")
    result.require(contract["canonicalization"] == "rfc8785", "2",
                   f"canonicalization is {contract['canonicalization']!r}")
    result.require(_nonempty_string(contract["contract_version"]), "2",
                   "contract_version is empty")
    result.require(contract["profile_label"] == ADMITTED_PROFILE_LABEL, "2",
                   f"profile_label {contract['profile_label']!r} is not the admitted "
                   f"record label {ADMITTED_PROFILE_LABEL!r}")

    # --- item 3
    dimensions = contract["dimensions"]
    if not isinstance(dimensions, list):
        result.fail("3", "dimensions is not an array")
        return result
    names: list[str] = []
    for index, entry in enumerate(dimensions):
        name = _check_dimension(result, entry, index)
        if name is not None:
            names.append(name)
    result.require(len(names) == 10 and set(names) == set(DIMENSIONS), "3",
                   f"expected exactly the ten dimensions, got {sorted(names)}")
    result.require(len(set(names)) == len(names), "3", "duplicate dimension entries")
    result.require(_sorted_utf16(names), "3", "dimensions are not sorted ascending")

    result.note("10")
    return result


def stored_bytes_are_canonical(raw: bytes) -> bool:
    """Item 11: the stored artifact's bytes are already its canonical serialization."""
    return jcs.canonicalize(raw) == raw
