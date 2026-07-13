"""Terminal entry point for the core `ask()` path (pre-API milestone).

Usage: python -m app.cli "What is money?" --top-k 5
Requires configured provider keys + a reachable Qdrant with an ingested corpus.
Prints the rendered result as JSON. Live use — respects the budget rules (docs/08).
"""

from __future__ import annotations

import argparse
import json
import sys

from .config_check import require_ready
from .container import build_core
from .core.config import Settings
from .core.errors import IonError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ION MIVE — ask the corpus.")
    parser.add_argument("question", help="The question to ask.")
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args(argv)

    settings = Settings.load()
    try:
        require_ready(settings)  # fail clearly before any external call
        core = build_core(settings)
        result = core.ask(args.question, top_k=args.top_k)
    except IonError as exc:
        print(json.dumps({"status": "error", "error_stage": exc.stage,
                          "message": exc.message}), file=sys.stderr)
        return 1
    print(json.dumps(result.rendered, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
