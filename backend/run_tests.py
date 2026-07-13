"""Minimal stdlib test runner (no pytest required).

Discovers `test_*` functions in `tests/test_*.py`, runs them, prints a summary.
`pytest` also collects these same files. Run: `python run_tests.py`
"""

from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> int:
    test_dir = HERE / "tests"
    modules = sorted(p.stem for p in test_dir.glob("test_*.py"))
    passed = failed = 0
    failures: list[str] = []

    for mod_name in modules:
        module = importlib.import_module(f"tests.{mod_name}")
        for name in sorted(dir(module)):
            if not name.startswith("test_"):
                continue
            fn = getattr(module, name)
            if not callable(fn):
                continue
            try:
                fn()
                passed += 1
                print(f"  PASS {mod_name}.{name}")
            except Exception:
                failed += 1
                tb = traceback.format_exc()
                failures.append(f"FAIL {mod_name}.{name}\n{tb}")
                print(f"  FAIL {mod_name}.{name}")

    print("\n" + "=" * 60)
    if failures:
        print("\n\n".join(failures))
    print(f"TOTAL: {passed + failed}  PASSED: {passed}  FAILED: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
