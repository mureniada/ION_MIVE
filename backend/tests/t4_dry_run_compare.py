"""Field-by-field comparison of the dry-run record against the demonstration record.

Not a test module (no `test_` prefix), so nothing collects it and the suite totals stay
comparable.

Both records are read through `t4.validation.load_record`, which refuses non-canonical
stored bytes (I16) and refuses a record whose identity contract does not resolve to the
registered one (I17). A record that cannot be verified is not compared at all.

Every leaf is compared. Each difference is then classified against
:data:`EXPECTED_DIFFERENCES` — a table of causes stated in advance, not fitted
afterwards. **A difference matching no entry is reported as UNEXPLAINED**, which is a
finding about the emitter, the contract or the fixture. Neither record is adjusted.
"""

from __future__ import annotations

import re
from pathlib import Path

from t4 import manifest
from t4.validation import load_record

#: (path pattern, cause). Order is irrelevant; the first match wins. A pattern is a
#: full-match regular expression over the flattened leaf path.
EXPECTED_DIFFERENCES: tuple[tuple[str, str], ...] = (
    (r"run_id",
     "two runs are two runs; run_id is never derived from content (§4.2)"),
    (r"timestamp",
     "the moment this run started, not the fixture's recorded moment"),
    (r"run_fingerprint",
     "SHA-256 over the whole stored run_configuration, so any identity below moves it"),
    (r"run_configuration/workload_identity/.*",
     "the question is the Phase 1 control question, because the offline retrieval path "
     "is the local layer; the fixture asked a different question"),
    (r"run_configuration/prompt_identity/.*",
     "the prompt is built by ive_common.build_user_prompt from the real pack, so its "
     "bytes are the real pack's bytes"),
    (r"run_configuration/context_identity/.*",
     "the Context Pack is built from registry-admitted local material, not from the "
     "fixture's three inline documents"),
    (r"run_configuration/planned_components/\d+/implementation_identity/.*",
     "the ten implementation values are read in the executing environment; the fixture "
     "transcribed the environment of the run it described"),
    (r"calls/\d+/call_id",
     "call_id is uuid4 per attempt, unique independently of (sequence, attempt) — T60"),
    (r"total_cost_missing_call_ids/\d+",
     "carries a call_id, which is per-attempt"),
    (r"total_wall_clock_ms",
     "measured on this traversal by operator decision of 2026-08-09, not recorded"),
    (r"wall_clock_source",
     "names the measurement as observed, because it is; the per-call latency_source "
     "still says recorded_fixture"),
)


def flatten(node, prefix: str = "") -> dict[str, object]:
    """Every leaf of a JSON document, keyed by its path. Containers are not leaves."""
    if isinstance(node, dict):
        if not node:
            return {prefix: "<empty object>"}
        out: dict[str, object] = {}
        for key in sorted(node):
            out.update(flatten(node[key], f"{prefix}/{key}" if prefix else key))
        return out
    if isinstance(node, list):
        if not node:
            return {prefix: "<empty array>"}
        out = {}
        for index, item in enumerate(node):
            out.update(flatten(item, f"{prefix}/{index}"))
        return out
    return {prefix: node}


def classify(path: str) -> str | None:
    for pattern, cause in EXPECTED_DIFFERENCES:
        if re.fullmatch(pattern, path):
            return cause
    return None


def compare(left_path: Path, right_path: Path, manifest_path: Path | None = None) -> dict:
    """Compare two verified records. Returns the full account, nothing elided."""
    left = load_record(left_path, manifest_path)
    right = load_record(right_path, manifest_path)

    a, b = flatten(left), flatten(right)
    only_left = sorted(set(a) - set(b))
    only_right = sorted(set(b) - set(a))
    shared = sorted(set(a) & set(b))

    differing = [(p, a[p], b[p]) for p in shared if a[p] != b[p]]
    identical = [p for p in shared if a[p] == b[p]]

    explained, unexplained = [], []
    for path, left_value, right_value in differing:
        cause = classify(path)
        (explained if cause else unexplained).append(
            {"path": path, "demonstration": left_value, "dry_run": right_value,
             "cause": cause})

    # A path present in one record and not the other is a structural difference, and a
    # closed schema should make it impossible. It is never "explained".
    for path in only_left:
        unexplained.append({"path": path, "demonstration": a[path],
                            "dry_run": "<absent>", "cause": None})
    for path in only_right:
        unexplained.append({"path": path, "demonstration": "<absent>",
                            "dry_run": b[path], "cause": None})

    return {
        "leaves_compared": len(shared),
        "identical": identical,
        "identical_count": len(identical),
        "explained": explained,
        "unexplained": unexplained,
    }


def _render(value) -> str:
    text = str(value)
    return text if len(text) <= 78 else text[:75] + "..."


def main(store: Path | None = None) -> int:  # pragma: no cover
    store = store or (manifest.repository_root() / "backend" / "t4" / "records")
    report = compare(store / "ion-t4-demo-0001.json", store / "ion-t4-dryrun-0001.json")

    print(f"leaves compared: {report['leaves_compared']}  "
          f"identical: {report['identical_count']}  "
          f"differing: {len(report['explained']) + len(report['unexplained'])}")

    print(f"\n--- EXPLAINED DIFFERENCES ({len(report['explained'])}) ---")
    for row in report["explained"]:
        print(f"\n{row['path']}")
        print(f"  demonstration: {_render(row['demonstration'])}")
        print(f"  dry run:       {_render(row['dry_run'])}")
        print(f"  cause:         {row['cause']}")

    print(f"\n--- UNEXPLAINED DIFFERENCES ({len(report['unexplained'])}) ---")
    if not report["unexplained"]:
        print("  none")
    for row in report["unexplained"]:
        print(f"\n{row['path']}")
        print(f"  demonstration: {_render(row['demonstration'])}")
        print(f"  dry run:       {_render(row['dry_run'])}")

    print(f"\n--- IDENTICAL LEAVES ({report['identical_count']}) ---")
    for path in report["identical"]:
        print(f"  {path}")

    return 1 if report["unexplained"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
