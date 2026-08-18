"""E-05 Canonical Task Identity v0.1 frozen-contract tests."""

from __future__ import annotations

import json
from dataclasses import replace

from pel.canonical_task_identity import (
    CANONICAL_TASK_IDENTITY_CONTRACT_ID,
    CANONICAL_TASK_IDENTITY_FIELDS,
    CanonicalTaskIdentityPayloadV0_1,
    compute_canonical_task_sha256,
    project_canonical_task_identity,
    serialize_canonical_task_identity_payload,
)
from pel.integrity import sha256_bytes
from pel.task_freeze import freeze_task


def _spec(
    *,
    task_id: str = "task-001",
    task_version: str = "1",
    task_class: str = "TEST",
    semantic_boundary: str | None = "bounded",
    bundle_filename: str = "bundle.bin",
    bundle_bytes: bytes = b"bundle-content",
    prompt_id: str = "prompt-label",
    prompt_bytes: bytes = b"prompt-content",
    output_contract_id: str = "output-contract-1",
    created_at: str = "2026-08-18T00:00:00+00:00",
):
    return freeze_task(
        task_id=task_id,
        task_version=task_version,
        task_class=task_class,
        semantic_boundary=semantic_boundary,
        bundle_filename=bundle_filename,
        bundle_bytes=bundle_bytes,
        prompt_id=prompt_id,
        prompt_bytes=prompt_bytes,
        output_contract_id=output_contract_id,
        created_at=created_at,
    )


def test_i01_exact_eight_field_projection():
    spec = _spec()
    payload = project_canonical_task_identity(spec)
    data = payload.to_dict()

    assert tuple(data.keys()) == CANONICAL_TASK_IDENTITY_FIELDS
    assert len(data) == 8
    assert data == {
        "identity_contract_id": CANONICAL_TASK_IDENTITY_CONTRACT_ID,
        "task_id": spec.task_id,
        "task_version": spec.task_version,
        "task_class": spec.task_class,
        "semantic_boundary": spec.semantic_boundary,
        "bundle_sha256": spec.bundle_sha256,
        "prompt_sha256": spec.prompt_sha256,
        "output_contract_id": spec.output_contract_id,
    }


def test_i02_excluded_metadata_does_not_affect_digest():
    base = _spec()

    changed = replace(
        base,
        bundle_filename="renamed-bundle.bin",
        prompt_id="different-logical-label",
        created_at="2026-08-18T12:34:56+00:00",
    )

    assert compute_canonical_task_sha256(base) == compute_canonical_task_sha256(
        changed
    )


def test_i03_each_variable_identity_field_changes_digest():
    base = _spec()
    base_digest = compute_canonical_task_sha256(base)

    variants = (
        replace(base, task_id="task-002"),
        replace(base, task_version="2"),
        replace(base, task_class="TEST-ALT"),
        replace(base, semantic_boundary="different-boundary"),
        replace(base, bundle_sha256="a" * 64),
        replace(base, prompt_sha256="b" * 64),
        replace(base, output_contract_id="output-contract-2"),
    )

    for variant in variants:
        assert compute_canonical_task_sha256(variant) != base_digest


def test_i04_prompt_id_does_not_affect_digest():
    left = _spec(prompt_id="prompt-A")
    right = replace(left, prompt_id="prompt-B")

    assert compute_canonical_task_sha256(left) == compute_canonical_task_sha256(
        right
    )


def test_i05_prompt_sha256_affects_digest():
    base = _spec()
    changed = replace(base, prompt_sha256="c" * 64)

    assert compute_canonical_task_sha256(base) != compute_canonical_task_sha256(
        changed
    )


def test_i06_semantic_boundary_null_distinct_from_empty_string():
    null_boundary = _spec(semantic_boundary=None)
    empty_boundary = _spec(semantic_boundary="")

    assert compute_canonical_task_sha256(
        null_boundary
    ) != compute_canonical_task_sha256(empty_boundary)


def test_i07_json_key_insertion_order_does_not_change_canonical_bytes():
    payload = project_canonical_task_identity(_spec())

    reversed_dict = dict(reversed(list(payload.to_dict().items())))

    expected = (
        json.dumps(
            reversed_dict,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )

    assert serialize_canonical_task_identity_payload(payload) == expected


def test_i08_exactly_one_terminal_lf_participates_in_digest():
    spec = _spec()
    payload = project_canonical_task_identity(spec)
    canonical_bytes = serialize_canonical_task_identity_payload(payload)

    assert canonical_bytes.endswith(b"\n")
    assert not canonical_bytes.endswith(b"\n\n")

    digest = compute_canonical_task_sha256(spec)

    assert digest == sha256_bytes(canonical_bytes)
    assert digest != sha256_bytes(canonical_bytes[:-1])


def test_i09_non_ascii_is_utf8_not_ascii_escape():
    spec = _spec(semantic_boundary="граница")
    payload = project_canonical_task_identity(spec)
    canonical_bytes = serialize_canonical_task_identity_payload(payload)

    assert "граница".encode("utf-8") in canonical_bytes
    assert b"\\u0433" not in canonical_bytes


def test_i10_digest_is_exact_lowercase_sha256_hex():
    digest = compute_canonical_task_sha256(_spec())

    assert len(digest) == 64
    assert digest == digest.lower()
    assert set(digest) <= set("0123456789abcdef")


def test_identity_contract_id_is_closed():
    try:
        CanonicalTaskIdentityPayloadV0_1(
            identity_contract_id="WRONG_CONTRACT",
            task_id="task-001",
            task_version="1",
            task_class="TEST",
            semantic_boundary=None,
            bundle_sha256="a" * 64,
            prompt_sha256="b" * 64,
            output_contract_id="output-contract-1",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid identity_contract_id was accepted")