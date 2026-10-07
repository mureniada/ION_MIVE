"""VOE-LATENCY E3 paired composer replay (staging evaluation only).

Run INSIDE the ION_MIVE container (cwd /app), questions in E3_QUESTIONS_JSON:

    E3_QUESTIONS_JSON='[...]' python /tmp/voe_e3_paired_replay.py > out.jsonl

For each question, one real turn runs through the real Core (retrieval, IVE).
At the composer step BOTH composers run on the identical ComposerInput:
arm A = provider default thinking (no thinking config), arm B = thinking
budget E3_BUDGET_B (default 512). Call order alternates per question so a
warm prefix cache cannot favour one arm. The turn itself returns arm A's
result, so the IVE call and everything before the composer are shared.

Each composer output is scored with the G6 L1 detectors
(`scripts.voe_g6_l1_offline_eval.run_detectors`) against its own input.
Prints one `E3_META` line and one `E3_PAIR` line per question (JSON). Never
prints secrets or the environment; the only content printed is the
question, the composer's own input (the IVE report projection the composer
sees, no evidence) and the composer outputs.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/app")

USAGE = (
    ("prompt_tokens", "prompt_token_count"),
    ("candidates_tokens", "candidates_token_count"),
    ("thoughts_tokens", "thoughts_token_count"),
    ("cached_tokens", "cached_content_token_count"),
    ("total_tokens", "total_token_count"),
)
EXPECTED_SYSTEM_SHA256 = "eba5b8c80c2646bb534c3cb33da1ea3287d2f2b3bb16a74a8ec91bdf19fc0e64"
EXPECTED_FINGERPRINT = "ba22801ecb6a895ec833ca4ecdac146f49aa7cc2de2b039152f556f8213995b7"

CALLS: list[dict] = []


class _ModelsTap:
    """Records what each Gemini call sent (thinking config only) and the
    usage it reported. Passes the call through unchanged."""

    def __init__(self, models, label: str) -> None:
        self._models = models
        self._label = label

    def generate_content(self, **kwargs):
        tc = getattr(kwargs.get("config"), "thinking_config", None)
        started = time.monotonic()
        resp = self._models.generate_content(**kwargs)
        um = getattr(resp, "usage_metadata", None)
        row = {
            "label": self._label,
            "thinking_config_sent": tc is not None,
            "thinking_budget_sent": getattr(tc, "thinking_budget", None),
            "sdk_latency_ms": round((time.monotonic() - started) * 1000.0, 1),
        }
        for name, attr in USAGE:
            value = getattr(um, attr, None) if um is not None else None
            row[name] = value if isinstance(value, int) else None
        CALLS.append(row)
        return resp


class _ClientTap:
    def __init__(self, client, label: str) -> None:
        self._client = client
        self.models = _ModelsTap(client.models, label)


def install_tap(backend_module) -> None:
    original = backend_module.GeminiBackend._ensure

    def _ensure(self):
        client = original(self)
        if not isinstance(client, _ClientTap):
            client = _ClientTap(client, self._telemetry_label)
            self._client = client
        return client

    backend_module.GeminiBackend._ensure = _ensure


def composer_input_dict(ci) -> dict:
    return {
        "question": ci.question,
        "report_abstract": ci.report_abstract,
        "report_highlights": list(ci.report_highlights),
        "report_claims": [
            {"statement": c.statement, "confidence": c.confidence} for c in ci.report_claims
        ],
        "report_uncertainty": list(ci.report_uncertainty),
        "report_confidence": ci.report_confidence,
        "response_depth": ci.response_depth,
    }


def g6_case(ci_dict: dict) -> dict:
    """review_meta synthesised conservatively: claims C1..Cn, and every
    uncertainty item treated as qualifying every claim (an omission is
    then always on the FAIL branch)."""
    claim_ids = [f"C{i + 1}" for i in range(len(ci_dict["report_claims"]))]
    return {
        "composer_input": ci_dict,
        "review_meta": {
            "claim_ids": claim_ids,
            "uncertainty_links": [
                {"uncertainty_id": f"U{i + 1}", "qualifies_claim_ids": list(claim_ids)}
                for i in range(len(ci_dict["report_uncertainty"]))
            ],
        },
    }


class PairComposer:
    """Stands in for the Core's composer for the replay: runs arm A and arm B
    on the same ComposerInput and hands arm A's outcome back to the turn."""

    def __init__(self, composer_a, composer_b, errors) -> None:
        self._arms = {"A": composer_a, "B": composer_b}
        self._errors = errors  # (ResponseComposerProviderError, ResponseComposerOutputError)
        self.index = 0
        self.last: dict | None = None

    def compose(self, composer_input):
        order = ("A", "B") if self.index % 2 == 0 else ("B", "A")
        outcomes: dict = {}
        for position, arm in enumerate(order):
            first_call = len(CALLS)
            started = time.monotonic()
            try:
                result = self._arms[arm].compose(composer_input)
            except self._errors as exc:
                outcome = {"status": type(exc).__name__, "result": None, "exc": exc}
            else:
                outcome = {"status": "COMPOSED", "result": result, "exc": None}
            outcome["attempt_ms"] = round((time.monotonic() - started) * 1000.0, 1)
            outcome["position"] = position
            outcome["calls"] = CALLS[first_call:]
            outcomes[arm] = outcome
        self.last = {"input": composer_input, "order": order, "outcomes": outcomes}
        if outcomes["A"]["exc"] is not None:
            raise outcomes["A"]["exc"]
        return outcomes["A"]["result"]


def arm_record(outcome: dict, ci_dict: dict, run_detectors) -> dict:
    result = outcome["result"]
    record = {
        "status": outcome["status"],
        "position": outcome["position"],
        "attempt_ms": outcome["attempt_ms"],
        "calls": outcome["calls"],
    }
    if result is None:
        return record
    text = result.response.composed_text
    flags, unc_ledger, claim_ledger = run_detectors(text, g6_case(ci_dict))
    record.update({
        "composer_latency_ms": round(result.latency_ms, 1),
        "composed_text": text,
        "suggested_questions": list(result.response.suggested_questions),
        "words": len(text.split()),
        "g6_flags": flags,
        "g6_uncertainty_ledger": unc_ledger,
        "g6_claim_ledger": claim_ledger,
    })
    return record


def replay(core, pair: PairComposer, questions: list[str], run_detectors, emit) -> None:
    core._composer = pair
    for index, question in enumerate(questions):
        pair.index = index
        pair.last = None
        first_call = len(CALLS)
        started = time.monotonic()
        error = None
        try:
            result = core.ask(question)
        except Exception as exc:  # recorded, never hidden
            result, error = None, type(exc).__name__
        row = {"index": index, "question": question,
               "turn_ms": round((time.monotonic() - started) * 1000.0, 1), "error": error}
        if result is not None:
            rendered = result.rendered or {}
            metrics = result.metrics or {}
            row.update({
                "status": result.status,
                "error_stage": result.error_stage,
                "retrieval_ms": metrics.get("retrieval_latency_ms"),
                "context_characters": metrics.get("context_characters"),
                "context_documents": metrics.get("context_documents"),
                "evidence_ids": [
                    f"{e.get('document_id')}::{e.get('chunk_id')}"
                    for e in rendered.get("evidence") or []
                ],
                "uncertainty_count": len((rendered.get("uncertainty") or {}).get("reported") or []),
                "composition_status": (rendered.get("presentation") or {}).get("composition_status"),
            })
        row["ive_calls"] = [c for c in CALLS[first_call:] if c["label"] == "ive"]
        if pair.last is not None:
            ci_dict = composer_input_dict(pair.last["input"])
            row["order"] = "".join(pair.last["order"])
            row["composer_input"] = ci_dict
            row["arms"] = {
                arm: arm_record(outcome, ci_dict, run_detectors)
                for arm, outcome in pair.last["outcomes"].items()
            }
        emit("E3_PAIR", row)


def _emit(tag: str, obj: dict) -> None:
    print(f"{tag} {json.dumps(obj, ensure_ascii=False, sort_keys=True)}", flush=True)


def main() -> None:
    import app.modules.gemini_ive.backend as gbm
    from app.container import build_core, build_voe_composer, resolve_active_execution_profile
    from app.core.config import Settings
    from app.modules.response_composer import (
        ResponseComposerOutputError,
        ResponseComposerProviderError,
        build_composer_system_instruction,
    )
    from scripts.voe_g6_l1_offline_eval import run_detectors

    questions = json.loads(os.environ["E3_QUESTIONS_JSON"])
    raw_budget_b = os.environ.get("E3_BUDGET_B", "512").strip()
    # "none" runs a default-vs-default calibration pass (detector noise floor).
    budget_b = None if raw_budget_b.lower() == "none" else int(raw_budget_b)
    install_tap(gbm)

    settings = Settings.load()
    core = build_core(settings)
    profile = resolve_active_execution_profile(settings)
    composer_a, runtime_profile = build_voe_composer(
        profile, dataclasses.replace(settings, voe_composer_thinking_budget=None)
    )
    composer_b, _ = build_voe_composer(
        profile, dataclasses.replace(settings, voe_composer_thinking_budget=budget_b)
    )
    composer_a._backend._telemetry_label = "composer-A"
    composer_b._backend._telemetry_label = "composer-B"

    system_sha = hashlib.sha256(
        build_composer_system_instruction(runtime_profile).encode("utf-8")
    ).hexdigest()
    _emit("E3_META", {
        "model": settings.gemini_model,
        "deployed_composer_thinking_budget": settings.voe_composer_thinking_budget,
        "budget_b": budget_b,
        "questions": len(questions),
        "profile_version": runtime_profile.binding.profile_version,
        "fingerprint_ok": runtime_profile.binding.runtime_behavioral_fingerprint_sha256 == EXPECTED_FINGERPRINT,
        "system_instruction_sha256": system_sha,
        "system_instruction_ok": system_sha == EXPECTED_SYSTEM_SHA256,
    })
    pair = PairComposer(
        composer_a, composer_b, (ResponseComposerProviderError, ResponseComposerOutputError)
    )
    replay(core, pair, questions, run_detectors, _emit)


if __name__ == "__main__":
    main()
