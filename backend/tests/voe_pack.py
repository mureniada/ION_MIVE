"""Where the VOE Dialogue Profile v0.2 runtime pack lives, for tests.

`COMMITTED_VOE_PACK_DIR` is the copy of the four pinned runtime behavioral
files committed with the loader under `app/modules/voe_profile/assets/`.
`.gitattributes` marks those files `binary`, so every checkout reproduces the
pinned bytes on any platform. Tests that need the real pinned bytes read
this directory, so they run on any machine that has the repository.

`EXTERNAL_SOURCE_PACK_DIR` is the machine-local, immutable source
preparation pack the committed files were taken from. It is used only by an
optional cross-check that the committed files are byte-identical to it,
which skips when the folder is absent. Nothing ever writes to either
directory.

Stdlib only, like `tests/util.py`.
"""

from __future__ import annotations

from pathlib import Path

COMMITTED_VOE_PACK_DIR = (
    Path(__file__).resolve().parents[1] / "app" / "modules" / "voe_profile" / "assets"
)

EXTERNAL_SOURCE_PACK_DIR = Path(
    r"C:\Users\murenia\Documents\Projects\ION_ON\ION_PROFILE_INTEGRATION"
    r"\VOE-DIALOGUE-PROFILE\v0.2\00_INPUT_IMMUTABLE\EXTRACTED_PACK"
    r"\VOE_DIALOGUE_PROFILE_RUNTIME_PACK_v0.2"
)
