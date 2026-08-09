"""The T4 emitter — records what one run actually cost, honestly.

**Where it attaches.** At the `IVEPort` boundary (`app/core/ports.py:43-58`),
invoked per engine at `app/core/orchestrator.py:173`, wrapped from outside
`backend/app/` and injected through the public keyword-only `Core.__init__` (D7).
Not at `Core.ask()`: that yields only the aggregate, carries no per-call identity,
and on a provider failure `_run_engine` re-raises before any `Metrics` is built, so
a wrapper there would observe nothing at all. :class:`ObservingIVE` records the
attempt *before* re-raising, which is the whole reason the boundary is the port.

**What it does not do.** It computes cost from the rate table by exact integer
arithmetic and never calls `PricingTable.estimate_cost`, which rounds
(`pricing.py:39`) contrary to §4.6 rule 3 and collapses two different
unavailability causes — unknown model, absent token counts — into one `None`. The
pricing module is read, never modified (U4). Rates are injected rather than
imported so `t4` keeps its one-way independence from `app`.

**What it cannot measure here.** `reported_model` is null for every call in this
environment: both provider backends discard the SDK response and return only text
and token counts (`ive_common.py:20-26`). The null carries its own unavailable
reason under B4 rather than being omitted or filled with the requested model.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import jcs, manifest, money
from .identity import IdentityError, SecretBoundaryViolation, build_identity

__all__ = [
    "DIAGNOSTIC_CODES",
    "EmissionOutcome",
    "Emitter",
    "FAILURE_CODES",
    "ObservingIVE",
    "RunObserver",
]

EMITTER_NAME = "ion_t4_emitter"
EMITTER_VERSION = "0.1.0"
CONFIGURATION_PROFILE = "ion-t4-runcfg-5"
CURRENCY = "USD"

#: IC-3. Chosen once, at creation. An undocumented code is rejected.
FAILURE_CODES = (
    "canonicalization_input_invalid",  # §4.2C input validity / canonicalization failure
    "contract_unresolved",             # I17, T85
    "domain_violation",                # §4.6 rule 4, T77
    "duplicate_run_id",                # I7, T18
    "schema_invalid",                  # the record does not satisfy the run-record schema
    "secret_boundary",                 # §2A S5, T87(d)
    "supersession_unresolved",         # T53
)

#: IC-3. Diagnostics are info or warning only; an error preventing the write leaves
#: no record, and is surfaced through the emission outcome instead.
DIAGNOSTIC_CODES = (
    "pricing_entry_absent",
    "reported_model_unobservable",
)


class EmissionRefused(Exception):
    """Carries a documented failure code out of the write path."""

    def __init__(self, code: str, detail: str) -> None:
        if code not in FAILURE_CODES:
            raise AssertionError(f"undocumented failure code {code!r}")
        super().__init__(detail)
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class EmissionOutcome:
    """§4.4.1 — returned by every emission attempt. Never a record, never stored."""

    outcome: str
    run_id: str | None
    timestamp: str
    emitter_name: str
    emitter_version: str
    failure_code: str | None
    detail: str | None

    def to_dict(self) -> dict:
        return {
            "detail": self.detail,
            "emitter_name": self.emitter_name,
            "emitter_version": self.emitter_version,
            "failure_code": self.failure_code,
            "outcome": self.outcome,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "+00:00")


def _measurement(value, source, reason):
    """One measurement under the two-form truth table (§4.6, I1, I2)."""
    if value is None:
        return {"source": source, "status": "unavailable",
                "unavailable_reason": reason, "value": None}
    return {"source": source, "status": "available",
            "unavailable_reason": None, "value": int(value)}


# --------------------------------------------------------------------------- #
# Observation — the IVEPort wrapper
# --------------------------------------------------------------------------- #

class RunObserver:
    """Collects observed calls. Assigns call ids and attempt numbers itself."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._attempts: dict[int, int] = {}

    def next_attempt(self, sequence: int) -> int:
        self._attempts[sequence] = self._attempts.get(sequence, 0) + 1
        return self._attempts[sequence]

    def new_call_id(self) -> str:
        # Unique independently of (sequence, attempt) — T60.
        return uuid.uuid4().hex

    def record(self, **call) -> None:
        self.calls.append(call)

    def ordered(self) -> list[dict]:
        return sorted(self.calls, key=lambda c: (c["sequence"], c["attempt"]))


class ObservingIVE:
    """Wraps one `IVEPort`. Structural conformance only — nothing from `app` is imported.

    Delegates `engine_id`, `provider` and `model`, and times `run` on its own clock,
    so the measurement does not depend on anything the core chooses to report.
    """

    def __init__(self, inner, *, observer: RunObserver, sequence: int,
                 provider: str, requested_model: str, clock, latency_source: str) -> None:
        self._inner = inner
        self._observer = observer
        self._sequence = sequence
        self._provider = provider
        self._requested_model = requested_model
        self._clock = clock
        self._latency_source = latency_source

    @property
    def engine_id(self) -> str:
        return self._inner.engine_id

    @property
    def provider(self) -> str:
        return self._inner.provider

    @property
    def model(self) -> str:
        return self._inner.model

    def run(self, context_pack):
        attempt = self._observer.next_attempt(self._sequence)
        call_id = self._observer.new_call_id()
        started = self._clock()
        try:
            report = self._inner.run(context_pack)
        except BaseException as exc:
            # An attempt that yielded nothing is still an entry, with its
            # measurements unavailable and reasoned (B4). Then the failure
            # continues on its way: the emitter does not alter the computation (I8a).
            self._observer.record(
                call_id=call_id, sequence=self._sequence, attempt=attempt,
                provider=self._provider, requested_model=self._requested_model,
                reported_model=None,
                reported_model_reason="provider call raised before any response was read",
                input_tokens=None, output_tokens=None,
                token_reason=f"provider call failed: {type(exc).__name__}",
                latency_ms=None,
                latency_reason=f"provider call failed: {type(exc).__name__}",
                latency_source=self._latency_source,
            )
            raise
        elapsed = self._clock() - started
        usage = report.usage
        self._observer.record(
            call_id=call_id, sequence=self._sequence, attempt=attempt,
            provider=self._provider, requested_model=self._requested_model,
            # Null for every call in this environment, with its reason (B4):
            # the backends return text and token counts only.
            reported_model=None,
            reported_model_reason=(
                "the provider backend discards the SDK response and returns only "
                "text and token counts, so no model identifier reaches the emitter"
            ),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_reason=None if usage.input_tokens is not None
            else "provider reported no usage",
            latency_ms=int(elapsed),
            latency_reason=None,
            latency_source=self._latency_source,
        )
        return report


# --------------------------------------------------------------------------- #
# The emitter
# --------------------------------------------------------------------------- #

class Emitter:
    """Builds, validates and writes one run record.

    The contract is resolved through the manifest before anything is built or
    verified (I17); an unresolved contract refuses emission rather than proceeding.
    """

    name = EMITTER_NAME
    version = EMITTER_VERSION

    def __init__(self, *, manifest_path: Path, store_path: Path,
                 rates: dict, pricing_basis_id: str, validator=None) -> None:
        self._manifest_path = manifest_path
        self._store = store_path
        self._rates = dict(rates)
        self._pricing_basis_id = pricing_basis_id
        self._validate = validator

    # -- contract resolution ------------------------------------------------ #
    def resolve_contract(self) -> tuple[dict, str]:
        try:
            _path, raw, digest = manifest.resolve(manifest.ROLE_CONTRACT,
                                                  self._manifest_path)
        except manifest.ManifestError as exc:
            raise EmissionRefused("contract_unresolved", str(exc)) from None
        if jcs.canonicalize(raw) != raw:
            raise EmissionRefused(
                "contract_unresolved",
                "the registered contract's stored bytes are not canonical (I16)")
        return jcs.parse(raw), digest

    def _provenance(self) -> dict:
        out = {}
        for role, prefix in ((manifest.ROLE_EMITTER, "emitter"),
                             (manifest.ROLE_RUN_RECORD_SCHEMA, "schema"),
                             (manifest.ROLE_CONTRACT_SCHEMA, "contract_schema")):
            try:
                _path, _raw, digest = manifest.resolve(role, self._manifest_path)
            except manifest.ManifestError as exc:
                raise EmissionRefused("contract_unresolved", str(exc)) from None
            entry = next(e for e in manifest.load(self._manifest_path)["artifacts"]
                         if e["role"] == role)
            out[f"{prefix}_name"] = entry["name"]
            out[f"{prefix}_version"] = entry["version"]
            out[f"{prefix}_sha256"] = digest
        return out

    # -- cost --------------------------------------------------------------- #
    def _cost(self, requested_model: str, input_tokens, output_tokens) -> dict:
        """Exactly from the rate table, or an honestly reasoned absence (D4, B4)."""
        rates = self._rates.get(requested_model)
        if rates is None:
            return {"cost_currency": None, "cost_kind": None,
                    "cost_status": "unavailable",
                    "cost_unavailable_reason":
                        f"no pricing entry exists for model {requested_model!r}",
                    "cost_value": None, "pricing_basis_id": None}
        if input_tokens is None or output_tokens is None:
            return {"cost_currency": None, "cost_kind": None,
                    "cost_status": "unavailable",
                    "cost_unavailable_reason":
                        "token counts were not reported, so no estimate is derivable",
                    "cost_value": None, "pricing_basis_id": None}
        input_rate, output_rate = (money.rate_from_price(r) for r in rates)
        total = money.add([money.cost_of_tokens(input_tokens, input_rate),
                           money.cost_of_tokens(output_tokens, output_rate)],
                          bound=money.PER_CALL_VALUE_BOUND)
        return {"cost_currency": CURRENCY, "cost_kind": "estimated",
                "cost_status": "available", "cost_unavailable_reason": None,
                "cost_value": total, "pricing_basis_id": self._pricing_basis_id}

    # -- assembly ----------------------------------------------------------- #
    def _observed_call(self, raw: dict) -> dict:
        input_tokens = _measurement(raw["input_tokens"], "provider_reported",
                                    raw["token_reason"])
        output_tokens = _measurement(raw["output_tokens"], "provider_reported",
                                     raw["token_reason"])
        if raw["input_tokens"] is None or raw["output_tokens"] is None:
            total = _measurement(None, None, raw["token_reason"])
            consistency = "not_evaluable"
        else:
            derived = raw["input_tokens"] + raw["output_tokens"]
            total = _measurement(derived, "locally_derived", None)
            # A locally derived total must satisfy total = input + output; it does
            # here by construction, and the validator re-checks it (T47).
            consistency = "consistent"

        call = {
            "attempt": raw["attempt"],
            "call_id": raw["call_id"],
            "input_tokens": input_tokens,
            "latency_source": raw["latency_source"] if raw["latency_ms"] is not None
            else raw["latency_source"],
            "latency_status": "available" if raw["latency_ms"] is not None
            else "unavailable",
            "latency_unavailable_reason": raw["latency_reason"],
            "model_latency_ms": raw["latency_ms"],
            "output_tokens": output_tokens,
            "provider": raw["provider"],
            "reported_model": raw["reported_model"],
            "reported_model_unavailable_reason": raw["reported_model_reason"],
            "requested_model": raw["requested_model"],
            "sequence": raw["sequence"],
            # Non-null exactly when both parts and a provider-reported total exist;
            # here the total is locally derived, so it stays null (§4.6).
            "token_sum_of_parts": None,
            "token_consistency_status": consistency,
            "total_tokens": total,
        }
        call.update(self._cost(raw["requested_model"], raw["input_tokens"],
                               raw["output_tokens"]))
        return call

    def _aggregate(self, calls: list[dict]) -> dict:
        available = [c for c in calls if c["cost_status"] == "available"]
        missing = [c for c in calls if c["cost_status"] != "available"]
        currencies = {c["cost_currency"] for c in available}

        if not calls or not available or len(currencies) > 1:
            reason = ("no call carries an available cost"
                      if not available else
                      f"available costs span more than one currency: "
                      f"{sorted(currencies)}; no conversion rule exists")
            return {
                "available_cost_subtotal": None, "total_cost_composition": None,
                "total_cost_currency": None,
                "total_cost_missing_call_ids": sorted(c["call_id"] for c in missing),
                "total_cost_missing_providers": sorted({c["provider"] for c in missing}),
                "total_cost_status": "unavailable",
                "total_cost_unavailable_reason": reason, "total_cost_value": None,
            }

        kinds = {c["cost_kind"] for c in available}
        composition = kinds.pop() if len(kinds) == 1 else "mixed"
        exact_sum = money.add([c["cost_value"] for c in available])
        currency = currencies.pop()

        if not missing:
            return {
                "available_cost_subtotal": None, "total_cost_composition": composition,
                "total_cost_currency": currency, "total_cost_missing_call_ids": [],
                "total_cost_missing_providers": [], "total_cost_status": "available",
                "total_cost_unavailable_reason": None, "total_cost_value": exact_sum,
            }
        return {
            "available_cost_subtotal": exact_sum, "total_cost_composition": composition,
            "total_cost_currency": currency,
            "total_cost_missing_call_ids": sorted(c["call_id"] for c in missing),
            "total_cost_missing_providers": sorted({c["provider"] for c in missing}),
            "total_cost_status": "partial",
            "total_cost_unavailable_reason":
                "at least one call carries no cost; the known part is the subtotal",
            "total_cost_value": None,
        }

    def _run_status(self, component_results: list[dict], planned: list[dict]) -> str:
        primaries = {c["component"] for c in planned if c["is_primary"]}
        completed = {r["component"] for r in component_results
                     if r["outcome"] == "completed"}
        if not primaries & completed:
            return "failed"
        if any(r["outcome"] == "incomplete" for r in component_results):
            return "partial"
        return "success"

    # -- the write ---------------------------------------------------------- #
    def emit(self, *, record_origin: str, run_id: str, timestamp: str,
             raw_identities: dict, planned_components: list[dict],
             planned_calls: list[dict], component_results: list[dict],
             observer: RunObserver, wall_clock_ms, wall_clock_source: str,
             wall_clock_reason=None, supersedes_run_id=None,
             unavailable_measurements=None) -> tuple[EmissionOutcome, dict | None]:
        """Build, validate and write exactly one record. Returns the §4.4.1 outcome."""
        try:
            contract, contract_sha256 = self.resolve_contract()
            record = self._build(
                contract=contract, contract_sha256=contract_sha256,
                record_origin=record_origin, run_id=run_id, timestamp=timestamp,
                raw_identities=raw_identities,
                planned_components=planned_components, planned_calls=planned_calls,
                component_results=component_results, observer=observer,
                wall_clock_ms=wall_clock_ms, wall_clock_source=wall_clock_source,
                wall_clock_reason=wall_clock_reason,
                supersedes_run_id=supersedes_run_id,
                unavailable_measurements=unavailable_measurements or [],
            )
            raw = self._serialize(record)
            self._write(run_id, raw)
        except EmissionRefused as refused:
            return EmissionOutcome(
                outcome="write_failed", run_id=run_id, timestamp=_now_iso(),
                emitter_name=self.name, emitter_version=self.version,
                failure_code=refused.code, detail=refused.detail), None
        return EmissionOutcome(
            outcome="written", run_id=run_id, timestamp=_now_iso(),
            emitter_name=self.name, emitter_version=self.version,
            failure_code=None, detail=None), record

    def _build(self, *, contract, contract_sha256, record_origin, run_id, timestamp,
               raw_identities, planned_components, planned_calls, component_results,
               observer, wall_clock_ms, wall_clock_source, wall_clock_reason,
               supersedes_run_id, unavailable_measurements) -> dict:
        try:
            identities = {
                name: build_identity(dimension, raw, contract)
                for name, (dimension, raw) in raw_identities.items()
            }
        except SecretBoundaryViolation as exc:
            raise EmissionRefused("secret_boundary", str(exc)) from None
        except IdentityError as exc:
            raise EmissionRefused("contract_unresolved", str(exc)) from None

        components = sorted(planned_components,
                            key=lambda c: c["component"].encode("utf-16-be"))
        calls_in_order = sorted(planned_calls, key=lambda c: c["sequence"])
        if [c["sequence"] for c in calls_in_order] != list(range(1, len(calls_in_order) + 1)):
            raise EmissionRefused("schema_invalid",
                                  "planned call sequences are not consecutive from 1")

        run_configuration = {
            "configuration_profile": CONFIGURATION_PROFILE,
            "context_identity": identities["context"],
            "execution_policy": {
                f"{name}_policy_identity": identities[name]
                for name in ("dispatch", "fallback", "retry", "termination", "timeout")
            },
            "extensions": [],
            "identity_contract_sha256": contract_sha256,
            "planned_calls": [
                {"decoding_identity": identities["decoding"],
                 "provider": c["provider"], "requested_model": c["requested_model"],
                 "sequence": c["sequence"]}
                for c in calls_in_order
            ],
            "planned_components": [
                {"component": c["component"],
                 "implementation_identity": identities["implementation"],
                 "is_primary": c["is_primary"]}
                for c in components
            ],
            "prompt_identity": identities["prompt"],
            "workload_identity": identities["workload"],
        }

        try:
            observed = [self._observed_call(c) for c in observer.ordered()]
            aggregate = self._aggregate(observed)
        except money.DomainViolation as exc:
            raise EmissionRefused("domain_violation", str(exc)) from None

        planned_by_sequence = {c["sequence"]: c for c in calls_in_order}
        for call in observed:
            planned = planned_by_sequence.get(call["sequence"])
            if planned is None:
                raise EmissionRefused(
                    "schema_invalid",
                    f"observed call {call['call_id']} names sequence "
                    f"{call['sequence']}, which is not planned")
            if (call["provider"], call["requested_model"]) != (
                    planned["provider"], planned["requested_model"]):
                raise EmissionRefused(
                    "schema_invalid",
                    f"observed call {call['call_id']} contradicts its planned entry")
        if len({c["call_id"] for c in observed}) != len(observed):
            raise EmissionRefused("schema_invalid", "duplicate call_id")

        results = [
            {"component": r["component"], "incomplete_reason": r.get("incomplete_reason"),
             "outcome": r["outcome"]}
            for r in sorted(component_results,
                            key=lambda r: r["component"].encode("utf-16-be"))
        ]
        if [r["component"] for r in results] != [c["component"] for c in components]:
            raise EmissionRefused(
                "schema_invalid",
                "component_results do not correspond one-to-one with planned_components")

        emission_status = "incomplete" if unavailable_measurements else "complete"
        record = {
            "calls": observed,
            "component_results": results,
            "emission_result": {
                "diagnostics": [],
                "emission_status": emission_status,
                "unavailable_measurements": sorted(unavailable_measurements),
            },
            "planned_cost": None,
            "provenance": self._provenance(),
            "record_origin": record_origin,
            "run_configuration": run_configuration,
            "run_fingerprint": hashlib.sha256(
                jcs.serialize(run_configuration)).hexdigest(),
            "run_id": run_id,
            "run_status": self._run_status(results, components),
            "supersedes_run_id": supersedes_run_id,
            "timestamp": timestamp,
            "total_wall_clock_ms": wall_clock_ms,
            "wall_clock_source": wall_clock_source if wall_clock_ms is not None else None,
            "wall_clock_status": "available" if wall_clock_ms is not None
            else "unavailable",
            "wall_clock_unavailable_reason": wall_clock_reason,
        }
        record.update(aggregate)

        if supersedes_run_id is not None:
            if supersedes_run_id == run_id:
                raise EmissionRefused("supersession_unresolved",
                                      "a record cannot supersede itself")
            if not self._record_path(supersedes_run_id).is_file():
                raise EmissionRefused(
                    "supersession_unresolved",
                    f"superseded run_id {supersedes_run_id!r} does not resolve")

        self._check_measurement_paths(record)
        if self._validate is not None:
            error = self._validate(record)
            if error is not None:
                raise EmissionRefused("schema_invalid", error)
        return record

    def _check_measurement_paths(self, record: dict) -> None:
        """The closed path grammar of §4.4: exact template, resolvable, unavailable, unique."""
        paths = record["emission_result"]["unavailable_measurements"]
        if len(set(paths)) != len(paths):
            raise EmissionRefused("schema_invalid", "duplicate unavailable measurement path")
        for path in paths:
            if path == "total_wall_clock_ms":
                if record["wall_clock_status"] != "unavailable":
                    raise EmissionRefused("schema_invalid",
                                          f"{path} names an available measurement")
                continue
            head, _, field = path.partition(".")
            if not (head.startswith("calls[") and head.endswith("]")):
                raise EmissionRefused("schema_invalid", f"{path} is outside the grammar")
            try:
                index = int(head[len("calls["):-1])
                call = record["calls"][index]
            except (ValueError, IndexError):
                raise EmissionRefused("schema_invalid", f"{path} does not resolve") from None
            if field in ("input_tokens", "output_tokens", "total_tokens"):
                status = call[field]["status"]
            elif field == "model_latency_ms":
                status = call["latency_status"]
            elif field == "cost_value":
                status = call["cost_status"]
            else:
                raise EmissionRefused("schema_invalid", f"{path} is outside the grammar")
            if status != "unavailable":
                raise EmissionRefused("schema_invalid",
                                      f"{path} names an available measurement")

    def _serialize(self, record: dict) -> bytes:
        try:
            jcs.require_integer_domain(record)
            return jcs.serialize(record)
        except jcs.CanonicalizationError as exc:
            raise EmissionRefused("canonicalization_input_invalid", str(exc)) from None

    def _record_path(self, run_id: str) -> Path:
        return self._store / f"{run_id}.json"

    def _write(self, run_id: str, raw: bytes) -> None:
        """IC-1: one file per run, atomic, append-only by rejection, canonical bytes."""
        self._store.mkdir(parents=True, exist_ok=True)
        target = self._record_path(run_id)
        if target.exists():
            raise EmissionRefused("duplicate_run_id",
                                  f"a record for run_id {run_id!r} already exists")
        temporary = target.with_suffix(".json.partial")
        try:
            temporary.write_bytes(raw)
            temporary.replace(target)  # atomic within one filesystem
        finally:
            if temporary.exists():  # pragma: no cover - only on a failed replace
                temporary.unlink()
