"""Isolation and placement evidence for the T4 files — mandate T39 and ruling D7.

Two claims, each made by a mechanism rather than by the absence of an error:

1. **Every T4 test runs under `netguard`.** Checked structurally over the test
   modules' source, so a future test that forgets the decorator fails this one
   instead of quietly running unguarded. The guard is then shown *firing from
   inside a decorated body*, which is the form T39 asks for.
2. **T4 reaches nothing.** The `t4` package imports only the standard library: no
   provider SDK, no socket, no HTTP client, and nothing from `app`.

`netguard` protects T4's own tests. It is not, and is not cited as, containment for
anything else (mandate §3.0, Rule of evidence).
"""

from __future__ import annotations

import ast
import os
import socket
from pathlib import Path

from tests.netguard import SCRUBBED_ENV_VARS, NetworkAccessDenied, guarded
from tests.util import raises

TESTS_DIR = Path(__file__).resolve().parent
T4_DIR = TESTS_DIR.parent / "t4"

T4_TEST_MODULES = ("test_t4_jcs.py", "test_t4_contract_validation.py", "test_t4_isolation.py")

# Everything the t4 package is permitted to import from outside its own package.
PERMITTED_ABSOLUTE_IMPORTS = frozenset({
    "__future__", "base64", "binascii", "dataclasses", "datetime", "hashlib",
    "json", "jsonschema", "math", "pathlib", "re", "struct", "typing", "uuid",
})


def _decorator_names(node: ast.FunctionDef) -> set[str]:
    names = set()
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name):
            names.add(decorator.id)
        elif isinstance(decorator, ast.Attribute):
            names.add(decorator.attr)
    return names


@guarded
def test_every_t4_test_function_is_wrapped_by_the_guard():
    checked = 0
    for module_name in T4_TEST_MODULES:
        path = TESTS_DIR / module_name
        assert path.is_file(), f"missing T4 test module {module_name}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = [n for n in tree.body
                     if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        assert functions, f"{module_name} declares no test functions"
        for function in functions:
            assert "guarded" in _decorator_names(function), \
                f"{module_name}::{function.name} is not decorated with @guarded"
            checked += 1
    assert checked >= 25, f"expected the full T4 test set, counted {checked}"


@guarded
def test_the_guard_fires_from_inside_a_decorated_body():
    """Not 'no error was observed' — the denial is provoked and asserted."""
    with raises(NetworkAccessDenied):
        socket.create_connection(("provider.example", 443))
    with raises(NetworkAccessDenied):
        socket.getaddrinfo("provider.example", 443)


@guarded
def test_credentials_are_absent_inside_a_decorated_body():
    for name in SCRUBBED_ENV_VARS:
        assert name not in os.environ, f"{name} is present inside the guard"


@guarded
def test_t4_imports_nothing_that_could_reach_a_network_or_reach_into_app():
    modules = sorted(T4_DIR.glob("*.py"))
    assert modules, f"no modules found under {T4_DIR}"

    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])

        forbidden = imported & {
            "app", "socket", "http", "urllib", "requests", "httpx", "ssl",
            "openai", "google", "qdrant_client", "sentence_transformers",
        }
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}"

        unexpected = imported - PERMITTED_ABSOLUTE_IMPORTS
        assert not unexpected, f"{path.name} imports unreviewed module(s) {sorted(unexpected)}"


@guarded
def test_t4_lives_outside_backend_app():
    """D7 as a placement fact: no T4 file sits under `backend/app/`."""
    app_dir = TESTS_DIR.parent / "app"
    assert T4_DIR.is_dir()
    assert app_dir.resolve() not in T4_DIR.resolve().parents
    assert not list(app_dir.rglob("t4*")), "a T4-named file exists under backend/app/"
