"""Frozen backend mapping profile identifiers and deterministic helpers."""

from __future__ import annotations

from typing import Any

LOCAL_LEXICAL_BACKEND = "local_lexical"
MEMORY_BACKEND = "memory"
QDRANT_BACKEND = "qdrant"

LOCAL_LEXICAL_PROFILE = "ION_RUNTIME_EVIDENCE_MAPPING_LOCAL_LEXICAL_V0_1"
MEMORY_PROFILE = "ION_RUNTIME_EVIDENCE_MAPPING_MEMORY_V0_1"
QDRANT_PROFILE = "ION_RUNTIME_EVIDENCE_MAPPING_QDRANT_V0_1"

PROFILE_TO_BACKEND = {
    LOCAL_LEXICAL_PROFILE: LOCAL_LEXICAL_BACKEND,
    MEMORY_PROFILE: MEMORY_BACKEND,
    QDRANT_PROFILE: QDRANT_BACKEND,
}

BACKEND_TO_PROFILE = {
    LOCAL_LEXICAL_BACKEND: LOCAL_LEXICAL_PROFILE,
    MEMORY_BACKEND: MEMORY_PROFILE,
    QDRANT_BACKEND: QDRANT_PROFILE,
}


def get_value(obj: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field_name, default)
    return getattr(obj, field_name, default)


def get_path(obj: Any, path: str, default: Any = None) -> Any:
    current = obj
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
        else:
            if not hasattr(current, part):
                return default
            current = getattr(current, part)
    return current


def copy_extensions(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    return dict(metadata)
