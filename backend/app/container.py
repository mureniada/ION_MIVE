"""Composition root: wires concrete adapters into the Core at runtime.

This is the ONLY place that knows about concrete adapters. Construction is lazy
(called at runtime), so importing this module reads no secrets and opens no
connections. Provider SDK clients are created inside the adapters on first call.
"""

from __future__ import annotations

from .core.clock import SystemClock
from .core.config import Settings
from .core.errors import ConfigurationError
from .core.orchestrator import Core
from .core.ports import EmbeddingPort
from .modules.context_pack import ContextPackBuilder
from .modules.execution_profile import (
    ExecutionProfile,
    ExecutionProfileResolutionError,
    resolve_execution_profile,
)
from .modules.gemini_ive import GeminiIVE
from .modules.mive import MIVEComparator
from .modules.model_gateway import ModelGateway
from .modules.openai_ive import OpenAIIVE
from .modules.renderer import DeterministicRenderer
from .modules.response_composer import VOEResponseComposer
from .modules.retrieval.embeddings import HashingEmbedder, LocalEmbedder, OpenAIEmbedder
from .modules.retrieval.qdrant_store import QdrantRetrieval
from .modules.session import SessionController
from .modules.telemetry import PricingTable
from .modules.voe_profile import VOEProfileLoadError, VOERuntimeProfile, resolve_voe_profile


def build_embedder(settings: Settings) -> EmbeddingPort:
    backend = settings.embedding_backend.lower()
    if backend == "fake":
        return HashingEmbedder()
    if backend == "openai":
        return OpenAIEmbedder(settings.embedding_model or "text-embedding-3-small")
    # default: local
    return LocalEmbedder(settings.embedding_model)


def build_retrieval(settings: Settings, embedder: EmbeddingPort) -> QdrantRetrieval:
    return QdrantRetrieval(
        embedder,
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        collection=settings.qdrant_collection,
        upsert_batch_size=settings.qdrant_upsert_batch_size,
    )


def resolve_active_execution_profile(settings: Settings) -> ExecutionProfile:
    """Resolve the Product's active Model Execution Profile (TASK 20).

    This is the ONLY place that maps the pure `execution_profile` package's
    own package-local resolution failure onto the Product `ConfigurationError`
    boundary — the resolver itself stays closed against Core's error
    taxonomy, exactly as it stays closed against Core. The requested identity
    is passed through verbatim: nothing here strips, uppercases, normalizes,
    or defaults it, and a missing/empty/unknown/case-variant identity fails
    closed here exactly as the pure resolver already refuses it.
    """
    try:
        return resolve_execution_profile(settings.execution_profile_id)
    except ExecutionProfileResolutionError as exc:
        raise ConfigurationError(
            f"execution profile resolution failed: {exc}"
        ) from exc


def _build_engines(profile: ExecutionProfile, settings: Settings) -> dict:
    """Construct exactly the provider engines the active profile names.

    This is the ONLY place that knows which concrete engines exist. Each
    engine the profile names is constructed and registered under the
    identity it states about itself, so the key and the engine can never
    disagree; an engine id the profile names that this composition does not
    recognize is a composition error, not a silent omission. An engine the
    profile does NOT name is never constructed at all — not merely left
    unused — so STANDARD_GEMINI never instantiates an OpenAI adapter or
    requires an OpenAI credential to compose.
    """
    from .modules.gemini_ive.backend import GeminiBackend
    from .modules.openai_ive.backend import OpenAIBackend

    engines: dict = {}
    for engine_id in profile.engine_ids:
        if engine_id == "gemini":
            engine = GeminiIVE(
                GeminiBackend(settings.gemini_model, telemetry_label="ive"),
                model=settings.gemini_model,
            )
        elif engine_id == "openai":
            engine = OpenAIIVE(
                OpenAIBackend(settings.openai_model), model=settings.openai_model
            )
        else:
            raise ConfigurationError(
                f"execution profile names an unrecognized engine id: {engine_id!r}"
            )
        engines[engine.engine_id] = engine
    return engines


def build_voe_composer(
    profile: ExecutionProfile, settings: Settings
) -> tuple[VOEResponseComposer | None, VOERuntimeProfile | None]:
    """Construct the VOE Response Composer and its bound runtime profile, or
    (None, None) if the profile is disabled (Gate 4).

    Optimistic construction, mirroring `_build_engines`' own discipline for
    provider credentials: a bad or missing bundle here degrades to
    (None, None) rather than raising — this function never crashes
    `build_core()`. The actual fail-closed gate is `config_check.require_ready`,
    which independently re-resolves the SAME profile, per request, and
    refuses the request before any turn runs if it is invalid. That
    separation is deliberate: it is the exact shape `_build_engines`/
    `require_ready` already use for provider credentials, applied here to
    the VOE bundle instead.

    First-release provider/model rule (Gate 3A, Task D, option 1 — the
    minimum safe choice): the composer reuses the SAME provider and
    requested model as the active SINGLE IVE engine, as a semantically
    separate execution — `EXECUTION PROFILE != DIALOGUE PROFILE` remains
    true; this is implementation/configuration reuse only, never a shared
    instance and never a new execution-policy field. A SECOND, independent
    raw backend instance is always constructed: this function never reaches
    into `GeminiIVE._backend`/`OpenAIIVE._backend`, and never shares one
    backend object between the IVE path and the composer path.
    """
    if not settings.voe_profile_enabled:
        return None, None

    try:
        voe_runtime_profile = resolve_voe_profile(
            enabled=True, bundle_dir=settings.voe_profile_bundle_dir
        )
    except VOEProfileLoadError:
        return None, None

    from .modules.gemini_ive.backend import GeminiBackend
    from .modules.openai_ive.backend import OpenAIBackend

    # SINGLE mode: exactly one engine id, already validated by
    # `ExecutionProfile.__post_init__` and `_build_engines` above.
    engine_id = profile.engine_ids[0]
    if engine_id == "gemini":
        backend = GeminiBackend(
            settings.gemini_model,
            telemetry_label="composer",
            thinking_budget=settings.voe_composer_thinking_budget,
        )
        requested_model = settings.gemini_model
    elif engine_id == "openai":
        backend = OpenAIBackend(settings.openai_model)
        requested_model = settings.openai_model
    else:
        raise ConfigurationError(
            f"execution profile names an unrecognized engine id: {engine_id!r}"
        )

    composer = VOEResponseComposer(
        backend=backend, provider=engine_id, requested_model=requested_model
    )
    return composer, voe_runtime_profile


def build_core(settings: Settings) -> Core:
    """Production wiring: real Qdrant + the provider backends the active
    Model Execution Profile names (lazy SDKs)."""
    embedder = build_embedder(settings)
    retrieval = build_retrieval(settings, embedder)

    profile = resolve_active_execution_profile(settings)
    model_gateway = ModelGateway(_build_engines(profile, settings))
    composer, voe_runtime_profile = build_voe_composer(profile, settings)

    return Core(
        retrieval=retrieval,
        context_pack_builder=ContextPackBuilder(char_budget=settings.context_char_budget),
        model_gateway=model_gateway,
        mive=MIVEComparator(),
        renderer=DeterministicRenderer(),
        pricing=PricingTable(),
        clock=SystemClock(),
        settings=settings,
        execution_profile=profile,
        composer=composer,
        voe_runtime_profile=voe_runtime_profile,
    )


def build_session_controller(core: Core) -> SessionController:
    """Composition seam for the pilot transport (TASK E4C).

    Wraps the ONE already-constructed Core instance passed in — never builds
    a second Core or a second retrieval stack. `SessionController`'s own
    default `AdaptiveDialogueEngine` is accepted as-is (no override).
    """
    return SessionController(core=core)
