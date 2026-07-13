"""Runtime readiness checks that must pass BEFORE any external call (docs/04, /11).

Never returns or logs secret values — only presence booleans and safety checks.
"""

from __future__ import annotations

import os
import re

from .core.config import Settings, secret_presence
from .core.errors import ConfigurationError

# header-safe: no control chars / whitespace that would corrupt an auth header
_HEADER_SAFE = re.compile(r"^[\x21-\x7E]+$")


def _key_is_header_safe(name: str, env: dict[str, str]) -> bool:
    val = env.get(name, "")
    return bool(val) and bool(_HEADER_SAFE.match(val.strip()))


def require_ready(settings: Settings, env: dict[str, str] | None = None) -> None:
    e = env if env is not None else os.environ
    missing: list[str] = []

    presence = secret_presence(e)
    if not presence["OPENAI_API_KEY"]:
        missing.append("OPENAI_API_KEY")
    if not presence["GEMINI_API_KEY"]:
        missing.append("GEMINI_API_KEY")
    if not settings.openai_model:
        missing.append("OPENAI_MODEL")
    if not settings.gemini_model:
        missing.append("GEMINI_MODEL")

    if missing:
        raise ConfigurationError(
            "Missing required configuration (values never shown): " + ", ".join(missing)
        )

    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        if not _key_is_header_safe(key, e):
            raise ConfigurationError(
                f"{key} contains characters that are not header-safe."
            )
