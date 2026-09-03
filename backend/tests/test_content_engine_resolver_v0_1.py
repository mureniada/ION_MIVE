"""Content Engine resolver (E2.2 v0.1) — declared-source resolution and byte verification.

Three things stay distinct here and every test exists to keep them that way:

    source_id             declared logical identity  (never a path)
    relative_source_path  declared POSIX location    (never an identity)
    source_root           this machine's location    (never identity, never origin)

Covers exact key-set reconciliation, fail-closed behaviour on every way a binding
can be wrong (absolute, drive-lettered, backslashed, traversing, escaping,
absent, duplicated), preservation of declared identity and version, order
independence, canonical ordering inherited from the closed Content Pack,
isolation from any store or model, and the raw-byte hash basis.

Every test runs under `netguard`'s `guarded` decorator. Temporary corpora are
created with `tempfile` rather than a pytest fixture, so both `pytest` and the
stdlib `run_tests.py` collect and run these as plain functions.
"""

from __future__ import annotations

import ast
import hashlib
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.modules.content_engine import (
    ContentEngineError,
    VerifiedSource,
    measure_source_bytes,
    normalize_relative_source_path,
    resolve_and_verify,
)
from app.modules.content_pack import ContentPack, SourceEntry
from tests.netguard import BLOCKED_MODULE_PREFIXES, guarded
from tests.util import raises

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "app" / "modules" / "content_engine"

#: Everything the content_engine package may import from outside itself.
PERMITTED_ABSOLUTE_IMPORTS = frozenset({
    "__future__", "hashlib", "pathlib", "re", "dataclasses", "typing",
})

#: The only sibling product modules it may reach, all read-only reuse.
PERMITTED_RELATIVE_IMPORTS = frozenset({
    "models", "resolver", "engine",
    "retrieval.chunker",
    "retrieval.evidence_fingerprint",
    "retrieval.canonical_provenance_materializer",
    "retrieval.ingest",
    "retrieval.source_provenance",
})

TEXT_A = "Adaptive dialogue is a bounded runtime concern. " * 40
TEXT_B = "Retrieval is not reasoning, and evidence is stronger than confidence. " * 40


@contextmanager
def _corpus(**sources: str):
    """Real files under a nested relative layout, plus the pack declaring them.

    Filenames and directories deliberately differ from the declared source ids,
    so any filename- or path-derived identity would be visible immediately.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        entries = []
        bindings = {}
        for source_id, text in sources.items():
            relative = f"research/{source_id}_file.txt"
            path = root / "research" / f"{source_id}_file.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            entries.append(
                SourceEntry(
                    source_id=source_id,
                    source_version="1.0.0",
                    source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
            bindings[source_id] = relative
        pack = ContentPack.create(
            pack_id="ion_test_pack", pack_version="1.0.0", sources=entries
        )
        yield pack, bindings, root


# --------------------------------------------------------------------------- #
# R1-R3 — the binding must match the declared inventory exactly
# --------------------------------------------------------------------------- #
@guarded
def test_r1_pack_source_set_and_binding_key_set_must_match_exactly():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        verified = resolve_and_verify(pack, bindings, source_root=root)
        assert {v.source_id for v in verified} == {s.source_id for s in pack.sources}
        assert len(verified) == len(pack.sources) == 2


@guarded
def test_r2_missing_source_binding_fails_closed():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        with raises(ContentEngineError):
            resolve_and_verify(pack, {"alpha": bindings["alpha"]}, source_root=root)
        with raises(ContentEngineError):
            resolve_and_verify(pack, {}, source_root=root)


@guarded
def test_r3_unexpected_binding_fails_closed():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        stray = root / "research" / "stray.txt"
        stray.write_text(TEXT_B, encoding="utf-8")
        extra = dict(bindings)
        extra["gamma"] = "research/stray.txt"
        with raises(ContentEngineError):
            resolve_and_verify(pack, extra, source_root=root)


@guarded
def test_two_declared_sources_resolving_to_one_file_fails_closed():
    """One physical file cannot be two declared sources."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shared = root / "shared.txt"
        shared.write_text(TEXT_A, encoding="utf-8")
        digest = hashlib.sha256(shared.read_bytes()).hexdigest()
        pack = ContentPack.create(
            pack_id="ion_test_pack",
            pack_version="1.0.0",
            sources=[
                SourceEntry(source_id="alpha", source_version="1.0.0", source_sha256=digest),
                SourceEntry(source_id="beta", source_version="1.0.0", source_sha256=digest),
            ],
        )
        with raises(ContentEngineError):
            resolve_and_verify(
                pack, {"alpha": "shared.txt", "beta": "shared.txt"}, source_root=root
            )


# --------------------------------------------------------------------------- #
# C/D/E/F — the relative path is relative, and stays inside the root
# --------------------------------------------------------------------------- #
@guarded
def test_c_absolute_binding_path_is_rejected():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        absolute_posix = "/" + (root / "research" / "alpha_file.txt").as_posix().lstrip("/")
        for absolute in (absolute_posix, "/etc/passwd", "/research/alpha_file.txt"):
            with raises(ContentEngineError):
                resolve_and_verify(pack, {"alpha": absolute}, source_root=root)


@guarded
def test_d_parent_traversal_is_rejected():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        for traversal in (
            "../research/alpha_file.txt",
            "research/../research/alpha_file.txt",
            "research/../../alpha_file.txt",
            "./research/alpha_file.txt",
            "research//alpha_file.txt",
        ):
            with raises(ContentEngineError):
                resolve_and_verify(pack, {"alpha": traversal}, source_root=root)


@guarded
def test_e_binding_that_escapes_source_root_is_rejected():
    with tempfile.TemporaryDirectory() as outer:
        outer_root = Path(outer)
        inside = outer_root / "inside"
        inside.mkdir()
        outside_file = outer_root / "outside.txt"
        outside_file.write_text(TEXT_A, encoding="utf-8")

        pack = ContentPack.create(
            pack_id="ion_test_pack",
            pack_version="1.0.0",
            sources=[
                SourceEntry(
                    source_id="alpha",
                    source_version="1.0.0",
                    source_sha256=hashlib.sha256(outside_file.read_bytes()).hexdigest(),
                )
            ],
        )
        # The file exists and its digest is correct — only its location is wrong.
        with raises(ContentEngineError):
            resolve_and_verify(pack, {"alpha": "../outside.txt"}, source_root=inside)


@guarded
def test_f_windows_drive_or_backslash_binding_is_rejected():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        for windows_form in (
            "C:/research/alpha_file.txt",
            "C:\\research\\alpha_file.txt",
            "research\\alpha_file.txt",
            str(root / "research" / "alpha_file.txt"),   # native absolute
        ):
            with raises(ContentEngineError):
                resolve_and_verify(pack, {"alpha": windows_form}, source_root=root)


@guarded
def test_the_relative_path_validator_refuses_rather_than_repairs():
    for good in ("alpha.txt", "research/alpha.txt", "a/b/c/alpha.pdf"):
        assert normalize_relative_source_path(good, "alpha") == good
    for bad in ("", "  ", " alpha.txt", "alpha.txt ", "/alpha.txt", "C:/a.txt",
                "a\\b.txt", "../a.txt", "./a.txt", "a/../b.txt", None, 7):
        with raises(ContentEngineError):
            normalize_relative_source_path(bad, "alpha")


# --------------------------------------------------------------------------- #
# R4-R6 — the file, and its bytes
# --------------------------------------------------------------------------- #
@guarded
def test_r4_missing_physical_file_fails_closed():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        with raises(ContentEngineError):
            resolve_and_verify(pack, {"alpha": "research/not_here.txt"}, source_root=root)

        # A directory is not a readable source file.
        with raises(ContentEngineError):
            resolve_and_verify(pack, {"alpha": "research"}, source_root=root)

        # Neither is a non-string binding value.
        for bad in (None, 7, ""):
            with raises(ContentEngineError):
                resolve_and_verify(pack, {"alpha": bad}, source_root=root)

        # An absent or non-directory source_root fails closed too.
        with raises(ContentEngineError):
            resolve_and_verify(pack, bindings, source_root=root / "nowhere")
        with raises(ContentEngineError):
            resolve_and_verify(pack, bindings, source_root=None)


@guarded
def test_r5_raw_sha256_mismatch_fails_closed():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        with (root / "research" / "alpha_file.txt").open("ab") as handle:
            handle.write(b"!")
        with raises(ContentEngineError):
            resolve_and_verify(pack, bindings, source_root=root)


@guarded
def test_r6_valid_raw_sha256_passes_and_returns_verified_sources():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        verified = resolve_and_verify(pack, bindings, source_root=root)
        assert all(isinstance(v, VerifiedSource) for v in verified)
        for v in verified:
            assert v.source_sha256 == measure_source_bytes(v.path)
            assert v.relative_source_path == bindings[v.source_id]


# --------------------------------------------------------------------------- #
# A/R7-R8 — declared identity survives, and is not the origin
# --------------------------------------------------------------------------- #
@guarded
def test_a_source_id_and_relative_source_path_are_distinct():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        verified = resolve_and_verify(pack, bindings, source_root=root)[0]
        assert verified.source_id == "alpha"
        assert verified.relative_source_path == "research/alpha_file.txt"
        assert verified.source_id != verified.relative_source_path
        assert verified.source_id not in verified.relative_source_path.split("/")


@guarded
def test_r7_declared_source_id_is_preserved():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        verified = resolve_and_verify(pack, bindings, source_root=root)
        assert [v.source_id for v in verified] == [s.source_id for s in pack.sources]
        assert all(v.path.stem != v.source_id for v in verified)


@guarded
def test_r8_source_version_is_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "whatever.txt"
        path.write_text(TEXT_A, encoding="utf-8")
        pack = ContentPack.create(
            pack_id="ion_test_pack",
            pack_version="9.9.9",
            sources=[
                SourceEntry(
                    source_id="alpha",
                    source_version="2.4.1",
                    source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            ],
        )
        verified = resolve_and_verify(pack, {"alpha": "whatever.txt"}, source_root=root)
        assert verified[0].source_version == "2.4.1"


# --------------------------------------------------------------------------- #
# G — the machine root is a runtime fact only
# --------------------------------------------------------------------------- #
@guarded
def test_g_changing_the_machine_source_root_does_not_alter_declared_location():
    def _resolve_under(root: Path):
        path = root / "research" / "alpha_file.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEXT_A, encoding="utf-8")
        pack = ContentPack.create(
            pack_id="ion_test_pack",
            pack_version="1.0.0",
            sources=[
                SourceEntry(
                    source_id="alpha",
                    source_version="1.0.0",
                    source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            ],
        )
        return resolve_and_verify(
            pack, {"alpha": "research/alpha_file.txt"}, source_root=root
        )[0]

    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        a = _resolve_under(Path(first))
        b = _resolve_under(Path(second))
        assert a.relative_source_path == b.relative_source_path
        assert a.source_id == b.source_id
        assert a.source_sha256 == b.source_sha256
        assert a.path != b.path                      # only the machine location differs


# --------------------------------------------------------------------------- #
# R9-R10 — ordering
# --------------------------------------------------------------------------- #
@guarded
def test_r9_binding_order_does_not_affect_verified_source_order():
    with _corpus(gamma=TEXT_A, alpha=TEXT_B, beta=TEXT_A) as (pack, bindings, root):
        forward = resolve_and_verify(pack, bindings, source_root=root)
        reversed_bindings = {k: bindings[k] for k in reversed(list(bindings))}
        backward = resolve_and_verify(pack, reversed_bindings, source_root=root)
        assert [v.source_id for v in forward] == [v.source_id for v in backward]


@guarded
def test_r10_canonical_order_follows_the_closed_content_pack_order():
    with _corpus(gamma=TEXT_A, alpha=TEXT_B, beta=TEXT_A) as (pack, bindings, root):
        verified = resolve_and_verify(pack, bindings, source_root=root)
        assert [v.source_id for v in verified] == [s.source_id for s in pack.sources]
        assert [v.source_id for v in verified] == ["alpha", "beta", "gamma"]


# --------------------------------------------------------------------------- #
# R11 / K — isolation, and no clock
# --------------------------------------------------------------------------- #
@guarded
def test_r11_no_qdrant_network_or_model_call_occurs():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        resolve_and_verify(pack, bindings, source_root=root)
    for prefix in BLOCKED_MODULE_PREFIXES:
        assert prefix not in sys.modules, f"{prefix} was imported during resolution"


@guarded
def test_r11_and_k_the_package_reaches_no_store_model_network_or_clock():
    modules = sorted(PACKAGE_DIR.glob("*.py"))
    assert modules, f"no modules found under {PACKAGE_DIR}"

    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        absolute: set[str] = set()
        relative: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                absolute.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    absolute.add(node.module.split(".")[0])
                else:
                    relative.add(node.module or "")

        # K: no clock, no randomness, no surrogate identity source.
        forbidden = absolute & {
            "app", "socket", "http", "urllib", "requests", "httpx", "ssl", "time",
            "datetime", "random", "uuid", "openai", "google", "qdrant_client",
            "sentence_transformers", "numpy", "calendar",
        }
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}"

        unexpected = absolute - PERMITTED_ABSOLUTE_IMPORTS
        assert not unexpected, f"{path.name} imports unreviewed module(s) {sorted(unexpected)}"

        unexpected_relative = relative - PERMITTED_RELATIVE_IMPORTS
        assert not unexpected_relative, (
            f"{path.name} reaches unreviewed sibling(s) {sorted(unexpected_relative)}"
        )

        for banned in ("retrieval.qdrant_store", "retrieval.embeddings", "container",
                       "retrieval.memory_index", "local_layer", "evidence_provenance"):
            assert banned not in relative, f"{path.name} reaches {banned}"

        source = path.read_text(encoding="utf-8")
        for clock in ("datetime.now", "time.time", "utcnow", "uuid4", "random."):
            assert clock not in source, f"{path.name} reaches a clock/random source: {clock}"


# --------------------------------------------------------------------------- #
# R12 — the hash basis
# --------------------------------------------------------------------------- #
@guarded
def test_r12_source_hash_covers_complete_raw_bytes_with_no_normalization():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "raw.txt"
        # Deliberately awkward bytes: a BOM, CRLF, trailing blanks, non-ASCII.
        raw = b"\xef\xbb\xbfalpha\r\n\r\n  beta \t\r\ngamma\xc3\xa9\n\n"
        path.write_bytes(raw)

        assert measure_source_bytes(path) == hashlib.sha256(raw).hexdigest()

        pack = ContentPack.create(
            pack_id="ion_test_pack",
            pack_version="1.0.0",
            sources=[
                SourceEntry(
                    source_id="alpha",
                    source_version="1.0.0",
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                )
            ],
        )
        verified = resolve_and_verify(pack, {"alpha": "raw.txt"}, source_root=root)
        assert verified[0].source_sha256 == hashlib.sha256(raw).hexdigest()

        # A whitespace-only byte change is still a different source.
        path.write_bytes(raw + b" ")
        with raises(ContentEngineError):
            resolve_and_verify(pack, {"alpha": "raw.txt"}, source_root=root)
