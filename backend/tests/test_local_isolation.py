"""Isolation of the Phase 1 execution path from Qdrant Cloud and Railway.

Covers mandate §10 requirements 8, 9 and 10.

Read this file together with §11.1. What is proved here is that the Phase 1
execution path is *technically prevented* from issuing a cloud operation, and that
the prevention mechanism demonstrably fires. Nothing here audits the remote Qdrant
Cloud account or establishes its global state — Phase 1 is forbidden from contacting
it, so it structurally cannot make that claim.

The first two tests exist because "no error was observed" is not evidence. They fail
if the guard silently stops working.
"""

from __future__ import annotations

import ast
import importlib
import os
import socket
import sys
from pathlib import Path

from tests.netguard import (
    BLOCKED_MODULE_PREFIXES,
    SCRUBBED_ENV_PREFIXES,
    SCRUBBED_ENV_VARS,
    CloudAccessDenied,
    NetworkAccessDenied,
    no_network_and_no_cloud_credentials,
)
from tests.util import raises

LOCAL_LAYER_DIR = (
    Path(__file__).resolve().parents[1] / "app" / "modules" / "local_layer"
)

# Everything the local layer is permitted to import from outside its own package.
PERMITTED_ABSOLUTE_IMPORTS = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "functools",
        "hashlib",
        "json",
        "jsonschema",
        "math",
        "os",
        "pathlib",
        "re",
        "typing",
    }
)


# --------------------------------------------------------------------------- #
# 1. The guard demonstrably fires (it is not a no-op we are trusting)
# --------------------------------------------------------------------------- #
def test_guard_blocks_outbound_socket_connections():
    with no_network_and_no_cloud_credentials():
        with raises(NetworkAccessDenied):
            socket.create_connection(("qdrant.example", 6333))
        with raises(NetworkAccessDenied):
            socket.getaddrinfo("qdrant.example", 6333)
        with raises(NetworkAccessDenied):
            socket.socket().connect(("railway.example", 443))


def test_guard_blocks_cloud_sdk_imports():
    with no_network_and_no_cloud_credentials():
        for module_name in BLOCKED_MODULE_PREFIXES:
            with raises(CloudAccessDenied):
                importlib.import_module(module_name)


def test_guard_blocks_qdrant_client_construction_at_import_time():
    """A client cannot be initialised, which is stricter than 'cannot connect'."""
    with no_network_and_no_cloud_credentials():
        with raises(CloudAccessDenied):
            from qdrant_client import QdrantClient  # noqa: F401


def test_guard_removes_cloud_and_deployment_credentials():
    os.environ["VECTOR_STORE_URL"] = "https://dummy.invalid"
    os.environ["VECTOR_STORE_API_KEY"] = "dummy-not-a-real-key"
    os.environ["RAILWAY_TOKEN"] = "dummy-not-a-real-token"
    try:
        with no_network_and_no_cloud_credentials():
            for name in SCRUBBED_ENV_VARS:
                assert name not in os.environ, f"{name} survived the guard"
            assert not [k for k in os.environ if k.startswith(SCRUBBED_ENV_PREFIXES)]
        # restored afterwards, so the guard does not leak into the rest of the suite
        assert os.environ["VECTOR_STORE_URL"] == "https://dummy.invalid"
        assert os.environ["RAILWAY_TOKEN"] == "dummy-not-a-real-token"
    finally:
        for name in ("VECTOR_STORE_URL", "VECTOR_STORE_API_KEY", "RAILWAY_TOKEN"):
            os.environ.pop(name, None)


def test_guard_restores_networking_on_exit():
    original_create_connection = socket.create_connection
    with no_network_and_no_cloud_credentials():
        assert socket.create_connection is not original_create_connection
    assert socket.create_connection is original_create_connection
    # the shadow added to socket.socket is removed, not left behind
    assert "connect" not in socket.socket.__dict__


# --------------------------------------------------------------------------- #
# 2. §10.8 / §10.9 / §10.10 — the vertical runs fully inside the guard
# --------------------------------------------------------------------------- #
def test_full_vertical_runs_with_network_denied_and_credentials_absent():
    with no_network_and_no_cloud_credentials():
        from app.modules.local_layer.pipeline import run_control_question

        pack = run_control_question()

        assert pack["documents"], "vertical produced no documents under the guard"
        assert pack["metadata"]["origin"] == "local_working_layer"
        for name in SCRUBBED_ENV_VARS:
            assert name not in os.environ


def test_no_cloud_sdk_is_loaded_after_running_the_vertical():
    with no_network_and_no_cloud_credentials():
        from app.modules.local_layer.pipeline import run_control_question

        run_control_question()

        loaded = sorted(
            name
            for name in sys.modules
            if any(
                name == prefix or name.startswith(prefix + ".")
                for prefix in BLOCKED_MODULE_PREFIXES
            )
        )
        assert loaded == [], f"cloud SDK modules were loaded: {loaded}"


def test_index_rebuild_also_runs_under_the_guard():
    """Rebuilding is a write path; it must be as isolated as the read path."""
    with no_network_and_no_cloud_credentials():
        from app.modules.local_layer.pipeline import LocalLayerPaths, build_index, delete_index

        paths = LocalLayerPaths.resolve()
        index = build_index(paths, persist=True)
        assert len(index) > 0
        assert paths.index.is_file()
        delete_index(paths)


# --------------------------------------------------------------------------- #
# 3. Static corroboration: the code has no cloud reachability to begin with
# --------------------------------------------------------------------------- #
def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_local_layer_imports_nothing_that_could_reach_a_network():
    modules = sorted(LOCAL_LAYER_DIR.glob("*.py"))
    assert modules, f"no modules found under {LOCAL_LAYER_DIR}"

    for path in modules:
        imported = _absolute_imports(path)
        forbidden = {
            name
            for name in imported
            if any(name == prefix for prefix in BLOCKED_MODULE_PREFIXES)
            or name in {"socket", "http", "urllib", "requests", "httpx", "ssl"}
        }
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}"

        unexpected = imported - PERMITTED_ABSOLUTE_IMPORTS
        assert not unexpected, f"{path.name} imports unreviewed module(s) {sorted(unexpected)}"
