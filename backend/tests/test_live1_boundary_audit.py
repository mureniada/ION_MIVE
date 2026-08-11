"""Phase 10 boundary audit: prove statically that no file added for LIVE-1
architecture hardening imports a provider SDK, Qdrant, an embedding library,
or raw networking -- mirrors test_import_safety.py's approach."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = (
    "openai", "google", "anthropic", "qdrant_client", "sentence_transformers",
    "requests", "httpx", "urllib", "socket",
)

LIVE1_MODULE_DIR = Path(__file__).resolve().parents[1] / "app" / "modules" / "live1"


def _imported_top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_live1_module_imports_no_provider_or_network_library():
    py_files = sorted(LIVE1_MODULE_DIR.glob("*.py"))
    assert py_files, "expected the live1 module to contain source files"
    for path in py_files:
        imported = _imported_top_level_names(path)
        forbidden_hit = imported & set(FORBIDDEN_PREFIXES)
        assert not forbidden_hit, f"{path.name} imports forbidden module(s): {forbidden_hit}"


def test_live1_module_makes_no_provider_call_string_references():
    """A cheap, honest textual check: none of these files reference the real
    provider call sites at all (they simply have no reason to)."""
    forbidden_calls = ("generate_content(", "responses.create(", "ChatCompletion")
    for path in sorted(LIVE1_MODULE_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_calls:
            assert token not in text, f"{path.name} unexpectedly references {token!r}"
