"""Isolation harness for the Phase 1 local working layer.

This is the *mechanism* behind every isolation claim in the phase report. It does
not observe that no cloud call happened; it makes one impossible and proves it can
tell, on three independent channels:

1. IMPORT DENIAL   — a `sys.meta_path` finder refuses `qdrant_client`, `openai`,
                     `google*` and `sentence_transformers`, so a cloud client
                     cannot even be *initialised*, let alone connected.
2. SOCKET DENIAL   — `socket.socket.connect`, `.connect_ex`, `socket.create_connection`
                     and `socket.getaddrinfo` all raise. This covers Qdrant Cloud,
                     Railway, provider APIs and telemetry alike, since every one of
                     them would have to traverse a socket.
3. CREDENTIAL ABSENCE — cloud and deployment environment variables are removed, so
                     even a code path that slipped past 1 and 2 would have no URL,
                     key or collection to use.

Everything is restored on exit. Written as a context manager rather than a pytest
fixture because this repository's tests are plain functions run by both `pytest`
and the stdlib `run_tests.py`; a fixture would be invisible to the latter.
"""

from __future__ import annotations

import functools
import os
import socket
import sys
from contextlib import contextmanager

__all__ = [
    "BLOCKED_MODULE_PREFIXES",
    "CloudAccessDenied",
    "NetworkAccessDenied",
    "SCRUBBED_ENV_PREFIXES",
    "SCRUBBED_ENV_VARS",
    "guarded",
    "no_network_and_no_cloud_credentials",
]


class CloudAccessDenied(ImportError):
    """A cloud SDK import was attempted inside the guarded region."""


class NetworkAccessDenied(RuntimeError):
    """An outbound network operation was attempted inside the guarded region.

    Deliberately not an OSError subclass: networking code commonly catches OSError
    and retries, which would let a violation pass quietly. This must be impossible
    to swallow by accident.
    """


BLOCKED_MODULE_PREFIXES: tuple[str, ...] = (
    "qdrant_client",
    "openai",
    "google",
    "sentence_transformers",
)

SCRUBBED_ENV_VARS: tuple[str, ...] = (
    "VECTOR_STORE_URL",
    "VECTOR_STORE_API_KEY",
    "VECTOR_COLLECTION",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
)

SCRUBBED_ENV_PREFIXES: tuple[str, ...] = ("RAILWAY_",)


def _is_blocked(fullname: str) -> bool:
    return any(
        fullname == prefix or fullname.startswith(prefix + ".")
        for prefix in BLOCKED_MODULE_PREFIXES
    )


class _CloudImportBlocker:
    """A meta-path finder that refuses cloud SDKs instead of locating them."""

    def find_spec(self, fullname, path=None, target=None):
        if _is_blocked(fullname):
            raise CloudAccessDenied(
                f"import of '{fullname}' is denied inside the Phase 1 isolation guard"
            )
        return None

    # Legacy protocol, for completeness on older import paths.
    def find_module(self, fullname, path=None):
        if _is_blocked(fullname):
            raise CloudAccessDenied(
                f"import of '{fullname}' is denied inside the Phase 1 isolation guard"
            )
        return None


def _deny_network(*_args, **_kwargs):
    raise NetworkAccessDenied(
        "outbound network access is denied inside the Phase 1 isolation guard"
    )


@contextmanager
def no_network_and_no_cloud_credentials():
    """Deny cloud imports, outbound sockets and cloud credentials for the duration."""
    blocker = _CloudImportBlocker()

    # -- 1. import denial (and evict anything already cached, so the denial is real)
    evicted = {
        name: module for name, module in list(sys.modules.items()) if _is_blocked(name)
    }
    for name in evicted:
        del sys.modules[name]
    sys.meta_path.insert(0, blocker)

    # -- 2. socket denial
    patched_on_class = ("connect", "connect_ex")
    original_class_attrs = {
        name: socket.socket.__dict__.get(name, _MISSING) for name in patched_on_class
    }
    original_module_attrs = {
        name: getattr(socket, name) for name in ("create_connection", "getaddrinfo")
    }
    for name in patched_on_class:
        setattr(socket.socket, name, _deny_network)
    for name in original_module_attrs:
        setattr(socket, name, _deny_network)

    # -- 3. credential absence
    removed_env = {}
    for key in list(os.environ):
        if key in SCRUBBED_ENV_VARS or key.startswith(SCRUBBED_ENV_PREFIXES):
            removed_env[key] = os.environ.pop(key)

    try:
        yield
    finally:
        os.environ.update(removed_env)

        for name, value in original_module_attrs.items():
            setattr(socket, name, value)
        for name, value in original_class_attrs.items():
            if value is _MISSING:
                # it was inherited from _socket.socket; drop the shadow we added
                delattr(socket.socket, name)
            else:
                setattr(socket.socket, name, value)

        if blocker in sys.meta_path:
            sys.meta_path.remove(blocker)
        sys.modules.update(evicted)


def guarded(fn):
    """Run a test function entirely inside the isolation guard.

    Exists so mandate §10 requirement 10 — the *complete* Phase 1 suite running with
    credentials absent and outbound network denied — is satisfied literally, at
    runtime, rather than argued statically for the tests that never enter the guard
    themselves.

    A decorator and not a `conftest.py` autouse fixture on purpose: this repository
    has no `conftest.py`, and its tests must keep running under both `pytest` and the
    stdlib `run_tests.py`. A fixture would be invisible to the latter, which would
    silently reopen the very gap this closes.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with no_network_and_no_cloud_credentials():
            return fn(*args, **kwargs)

    return wrapper


class _Missing:
    pass


_MISSING = _Missing()
