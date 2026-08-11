from __future__ import annotations

from dataclasses import asdict

from app.modules.live1 import assign_blind_labels, resolve_provenance
from tests.netguard import guarded


@guarded
def test_blind_labels_are_neutral_x_y():
    pair, _prov = assign_blind_labels(
        "Answer from baseline.", "B1", "baseline",
        "Answer from perturbed.", "P1", "perturbed",
    )
    assert [a.label for a in pair] == ["X", "Y"]


@guarded
def test_blinded_payload_contains_no_arm_or_provider_identity():
    # Deliberately neutral answer text: real answer content is user-facing
    # prose that could legitimately contain any word, so the structural
    # guarantee is which *fields* exist, not a substring scan of free text.
    pair, _prov = assign_blind_labels(
        "Money functions as a medium of exchange.", "B1", "baseline",
        "Money is fundamentally a form of credit.", "P1", "perturbed",
    )
    for answer in pair:
        payload = asdict(answer)
        assert set(payload.keys()) == {"label", "text", "answer_hash"}
        assert not hasattr(answer, "run_id")
        assert not hasattr(answer, "arm")
        assert not hasattr(answer, "provider")


@guarded
def test_provenance_map_recovers_original_run_and_arm():
    pair, prov = assign_blind_labels(
        "Answer from baseline.", "B1", "baseline",
        "Answer from perturbed.", "P1", "perturbed",
    )
    x_label, y_label = pair[0].label, pair[1].label
    assert resolve_provenance(x_label, prov) == ("B1", "baseline")
    assert resolve_provenance(y_label, prov) == ("P1", "perturbed")


@guarded
def test_provenance_map_is_a_separate_object_from_the_blinded_pair():
    pair, prov = assign_blind_labels(
        "Answer from baseline.", "B1", "baseline",
        "Answer from perturbed.", "P1", "perturbed",
    )
    # The provenance map is its own dict; nothing about it is reachable from
    # the BlindedAnswer objects themselves.
    for answer in pair:
        assert not hasattr(answer, "run_id")
        assert not hasattr(answer, "arm")
    assert isinstance(prov, dict)
