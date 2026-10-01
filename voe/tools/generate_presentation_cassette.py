"""Generate VOE Presentation Cassette PC1 (staging) from the governed THE_WORKS state.

Presentation-only navigation and label metadata over already-authorized ACTIVE
objects (design v2.1 §5). It carries no knowledge text, no summaries and no
answer semantics, and it changes nothing in retrieval, admission or the backend.

Every input is pinned by SHA-256. On any missing input, hash mismatch or
consistency failure the generator writes NOTHING and exits non-zero.

Usage (from the repo root):
    python voe/tools/generate_presentation_cassette.py --works-root <THE_WORKS>
    python voe/tools/generate_presentation_cassette.py --works-root <THE_WORKS> --check
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

_VOE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = _VOE_DIR / "presentation_cassettes" / "pc1_staging.json"

SCHEMA = "VOE_PRESENTATION_CASSETTE_V1"
CASSETTE_ID = "VOE-PC1-STAGING"
ENVIRONMENT = "staging"
PC1_DECISION = "OP-DEC-20261001-VOE-PC1-01"
TW3_DECISION = "OP-DEC-20260929-09"

# THE_WORKS inputs (relative to --works-root), pinned to the approved bytes.
WORKS_INPUTS = {
    "register": ("99_CONTROL/AUTHORIZED_CONTENT_OBJECT_REGISTER_v0.1.csv",
                 "1c4cae328acc929f771de4a610771f52828949278d5467225a56f3d51a42afc8"),
    "pack_manifest": ("07-CONTENT-PACK/CANDIDATES/TW-CP-0006/CONTENT-PACK-CANDIDATE-MANIFEST.csv",
                      "4a6d0d823afc7492e7df04c78c486c905e0b4108e3a68fc0020072a41ab1f246"),
    "pack_declaration": ("07-CONTENT-PACK/CANDIDATES/TW-CP-0006/PACK-DECLARATION.md",
                         "cd3c7d9bc391ab05d61dfcdf6062e9ac7bfff520d4999031aca0d93ee79809a9"),
    "op_dec_tw_src_0003": ("99_CONTROL/OP-DEC-20260929-09-TW-SRC-0003-CONTINUED-AUTHORIZATION-STAGING-REFINEMENT-CYCLE.md",
                           "81982d658eafad11f054c408ac260c935f8e554629ec5da383ed8773b2cad7ee"),
    "op_dec_pc1": ("99_CONTROL/OP-DEC-20261001-VOE-PC1-01-PRESENTATION-SCOPE-PC1-STAGING.md",
                   "a6b17ccd5b02952ec2380d77cd572301b725e8788cee9f43898a6465ae768b2c"),
    "classification_map": ("99_CONTROL/PRESENTATION_CLASSIFICATION_MAP_v0.1.csv",
                           "663f3cd8560a6704c98b8eeabba2cf5b073b23682a59a895617958fc62b3ad1a"),
}
# Repo-side inputs: the v0.3 navigation file (question wording, `related` links and
# the 2026-09-29 anchored-retrieval probe) and the readable source names.
REPO_INPUTS = {
    "v03_navigation_probe": ("works_navigation.json",
                             "1e5313644dea4fe70a38d7c0bbb3944ca31aa1276e444cb5fc1597a8b7c9c01c"),
    "source_labels": ("source_labels.json",
                      "1524d066466a9c71fa15bd18e4594fb0750cbaedd90228d4f46477efdf25367b"),
}

AUTHORIZATION_CHECK_REF = {
    "artifact": "2026-10-01_TW_SRC_0001_0005_CURRENT_AUTHORIZATION_SCOPE_CHECK.md",
    "check_window_utc": "2026-10-01T15:29:54Z/2026-10-01T15:36:36Z",
    "result": "IN_FORCE 42 / EXPIRED 0 / UNCLEAR 21; UNCLEAR resolved by OP-DEC-20261001-VOE-PC1-01",
}
SCOPE_END = {
    PC1_DECISION: "The next explicit staging acceptance of Presentation Cassette v1.",
    TW3_DECISION: "The next staging acceptance of the voe-staging-rc product-refinement cycle.",
}
# Withheld from every navigation offer; the objects stay answerable when asked.
NAVIGATION_WITHHELD = {
    "TW-OBJ-0043": "Q19: withheld while Rubicon is HOLD (design v2.1 O-5); object untouched.",
    "TW-OBJ-0049": "Q25: removed from navigation (design v2.1 O-4); object untouched.",
}
# Presentation cautions, as declared in the TW-CP-0006 pack declaration §3.1/§3.3
# (bound above by hash). Navigation metadata only; never answer semantics.
PRESENTATION_CAUTIONS = {
    "TWO_LAYER_CONTEXTS": ("TW-OBJ-0001", "TW-OBJ-0008", "TW-OBJ-0013", "TW-OBJ-0033", "TW-OBJ-0036",
                           "TW-OBJ-0041", "TW-OBJ-0044", "TW-OBJ-0046", "TW-OBJ-0047", "TW-OBJ-0049",
                           "TW-OBJ-0050"),
    "METAPHOR": ("TW-OBJ-0047",),
    "CONDITIONAL": ("TW-OBJ-0049", "TW-OBJ-0050"),
    "DISTINCT_LOOP": ("TW-OBJ-0041",),
}
# Client-side suggestion blocklist additions for HOLD topics (design v2.1 §8.3 step 0).
# No generic "guarantee" block (operator, 2026-10-01): Q25 is withheld by object.
EXTRA_BLOCKED_PHRASES = ("rubicon", "cloud 9", "orpheus", "profit-sharing", "profit sharing")
BRANCH_CODES = {("ION", ""): "ION", ("Research", "Peer-reviewed"): "RESEARCH.PEER_REVIEWED"}


class CassetteError(Exception):
    """Any reason the cassette must not be emitted."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_pinned(base: Path, rel: str, expected: str) -> bytes:
    path = base / rel
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CassetteError(f"missing input: {rel}") from exc
    actual = _sha256(data)
    if actual != expected:
        raise CassetteError(f"hash mismatch: {rel} is {actual}, expected {expected}")
    return data


def _csv_rows(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))


def _pc1_objects(text: str) -> dict[str, str]:
    """object_id -> source_id from the §3 table of OP-DEC-20261001-VOE-PC1-01."""
    out: dict[str, str] = {}
    for src, first, rest, count in re.findall(
            r"^\| (TW-SRC-\d{4}) \| TW-OBJ-(\d{4})((?:, \d{4})*) \| (\d+) \|$", text, re.M):
        ids = [first] + [x.strip() for x in rest.split(",") if x.strip()]
        if len(ids) != int(count):
            raise CassetteError(f"{PC1_DECISION}: count mismatch for {src}")
        out.update({f"TW-OBJ-{n}": src for n in ids})
    return out


def _tw3_objects(text: str) -> set[str]:
    """The objects listed under 'Objects covered' in OP-DEC-20260929-09."""
    match = re.search(r"^## Objects covered.*?$(.*?)^## ", text, re.M | re.S)
    if not match:
        raise CassetteError(f"{TW3_DECISION}: 'Objects covered' section not found")
    return set(re.findall(r"TW-OBJ-\d{4}", match.group(1)))


def build(works_root: Path) -> tuple[dict, dict]:
    """Return (cassette, input bindings). Raises CassetteError on any failure."""
    raw = {k: _read_pinned(works_root, rel, h) for k, (rel, h) in WORKS_INPUTS.items()}
    raw.update({k: _read_pinned(_VOE_DIR, rel, h) for k, (rel, h) in REPO_INPUTS.items()})
    bindings = {k: {"path": rel, "sha256": h} for k, (rel, h) in {**WORKS_INPUTS, **REPO_INPUTS}.items()}

    register = _csv_rows(raw["register"])
    manifest = {r["object_id"]: r for r in _csv_rows(raw["pack_manifest"])}
    cmap = {r["source_id"]: r for r in _csv_rows(raw["classification_map"])}
    pc1 = _pc1_objects(raw["op_dec_pc1"].decode("utf-8"))
    tw3 = _tw3_objects(raw["op_dec_tw_src_0003"].decode("utf-8"))
    nav = json.loads(raw["v03_navigation_probe"].decode("utf-8"))
    labels = json.loads(raw["source_labels"].decode("utf-8"))["labels"]
    nav_items = {i["object_id"]: i for i in nav["items"]}
    if len(pc1) != 49 or len(tw3) != 14:
        raise CassetteError(f"authorization lists: PC1 {len(pc1)} (expected 49), TW-SRC-0003 {len(tw3)} (expected 14)")

    members = []
    for row in register:
        oid, src = row["object_id"], row["source_id"]
        if row["status"] != "ACTIVE":
            continue
        packed = manifest.get(oid)
        if not packed or packed["registered_object_sha256"] != row["object_sha256"]:
            continue  # not in the activated pack with these bytes: not presentable
        if oid in pc1:
            if pc1[oid] != src:
                raise CassetteError(f"{oid}: source {src} differs from {PC1_DECISION}")
            auth = PC1_DECISION
        elif oid in tw3 and src == "TW-SRC-0003":
            auth = TW3_DECISION
        else:
            continue  # no in-force authorization: dropped (fail-closed)
        cls = cmap.get(src)
        if not cls or cls["registration_state_at_decision"] != "REGISTERED":
            continue  # unclassified or unregistered: unplaced
        branch = BRANCH_CODES.get((cls["catalogue_branch"], cls["catalogue_sub_branch"]))
        if branch is None:
            raise CassetteError(f"{src}: no branch code for {cls['catalogue_branch']}/{cls['catalogue_sub_branch']}")
        member = {
            "object_id": oid,
            "object_sha256": row["object_sha256"],
            "source_id": src,
            "fragment_id": row["fragment_id"],
            "presentation_genre": cls["presentation_genre"],
            "branch": branch,
            "catalogue_branch": cls["catalogue_branch"],
            "catalogue_sub_branch": cls["catalogue_sub_branch"],
            "authorization_ref": auth,
            "scope_end": SCOPE_END[auth],
            "presentation_cautions": sorted(c for c, ids in PRESENTATION_CAUTIONS.items() if oid in ids),
            "navigable_after_answer": False,
        }
        item = nav_items.get(oid)
        if item is not None:
            if item["object_sha256"] != row["object_sha256"]:
                raise CassetteError(f"{oid}: v0.3 navigation hash differs from the register")
            member.update({
                "q_number": item["q_number"],
                "question": item["question"],
                "question_ref": item["source_reference_label"],
                "related": list(item.get("related") or []),
                "navigable_after_answer": item["navigable_after_answer"] is True and oid not in NAVIGATION_WITHHELD,
            })
        members.append(member)

    members.sort(key=lambda m: (m.get("q_number") is None, m.get("q_number") or 0, m["object_id"]))
    if len(members) != 63:
        raise CassetteError(f"expected 63 members, got {len(members)}")
    by_id = {m["object_id"]: m for m in members}
    for oid in NAVIGATION_WITHHELD:
        if by_id.get(oid, {}).get("navigable_after_answer"):
            raise CassetteError(f"{oid} is withheld but navigable")
    for m in members:
        if m["presentation_genre"] in ("PATENT_DISCLOSURE_CLAIM", "PRODUCT_DESCRIPTION"):
            raise CassetteError(f"{m['object_id']}: patent/product member without DEP-7")

    sources = sorted({m["source_id"] for m in members})
    blocked = nav["blocked"]
    cassette = {
        "schema": SCHEMA,
        "cassette_id": CASSETTE_ID,
        "environment": ENVIRONMENT,
        "purpose": ("Presentation-only navigation and label metadata over authorized ACTIVE objects. "
                    "Never evidence, never knowledge, never answer semantics; every click is an "
                    "ordinary question through the normal submit path."),
        "authorization_refs": [PC1_DECISION, TW3_DECISION],
        "authorization_check_ref": AUTHORIZATION_CHECK_REF,
        "production": "NOT_AUTHORIZED",
        "inputs": bindings,
        "opening": "STARTER_ONLY",
        "entry_questions": [],
        "rules": {
            "max_works_items_after_answer": 2,
            "navigable_after_answer": ("v0.3 rule (operator holds on Q9, Q16, Q17, Q27; anchored-retrieval "
                                       "probe 2026-09-29 top 3), minus the withheld objects."),
        },
        "navigation_withheld": [{"object_id": k, "basis": v} for k, v in NAVIGATION_WITHHELD.items()],
        "source_labels": {s: labels[s] for s in sources if s in labels},
        "suggestion_blocklist": {
            "fragments": list(blocked["fragments"]),
            # Withheld wording is also blocked as a composer suggestion, so it is
            # never offered by any path (it stays answerable when typed).
            "questions": list(blocked["questions"]) + [by_id[o]["question"] for o in NAVIGATION_WITHHELD],
            "phrases": list(blocked["phrases"]) + list(EXTRA_BLOCKED_PHRASES),
        },
        "counts": {s: sum(1 for m in members if m["source_id"] == s) for s in sources},
        "members": members,
    }
    return cassette, bindings


def render(cassette: dict) -> bytes:
    return (json.dumps(cassette, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--works-root", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="verify --out is byte-identical; write nothing")
    args = parser.parse_args(argv)
    try:
        data = render(build(args.works_root)[0])
    except (CassetteError, KeyError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    if args.check:
        current = args.out.read_bytes() if args.out.exists() else b""
        same = current == data
        print(("MATCH " if same else "DIFFERS ") + _sha256(data))
        return 0 if same else 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    print(f"WROTE {args.out} {_sha256(data)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
