"""Tests for the Voice of Emergence non-font styling.

Covers voe/.streamlit/config.toml (approved theme keys only, no font or
static-serving configuration) and a Streamlit AppTest smoke test of app.py
with PilotClient's HTTP methods stubbed — no network, no real backend.
"""

from __future__ import annotations

import ast
import sys
import tomllib
import unittest
from pathlib import Path
from unittest import mock

_VOE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_VOE_DIR))

import pilot_client as pc  # noqa: E402  (path insert above must run first)
from streamlit.testing.v1 import AppTest  # noqa: E402

_APP_PATH = _VOE_DIR / "app.py"
_CONFIG_PATH = _VOE_DIR / ".streamlit" / "config.toml"
_BASE_URL = "https://voe-backend.example.internal"

_APPROVED_THEME = {
    "base": "light",
    "primaryColor": "#1D1D1B",
    "textColor": "#1D1D1B",
    "borderColor": "#D9D9D6",
    "baseFontSize": 16,
    "baseFontWeight": 400,
    "headingFontSizes": "1rem",
    "headingFontWeights": 700,
}


def _module_constant(name: str):
    tree = ast.parse(_APP_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in app.py")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        with _CONFIG_PATH.open("rb") as fh:
            self.config = tomllib.load(fh)

    def test_config_parses_with_theme_section_only(self):
        self.assertEqual(set(self.config), {"theme"})

    def test_only_approved_theme_keys_and_values(self):
        self.assertEqual(self.config["theme"], _APPROVED_THEME)

    def test_no_font_or_static_serving_configuration(self):
        theme = self.config["theme"]
        for key in ("font", "headingFont", "codeFont", "fontFaces"):
            self.assertNotIn(key, theme)
        self.assertNotIn("server", self.config)
        self.assertNotIn("enableStaticServing", _CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertFalse((_VOE_DIR / "static").exists())


class LoadingTextTests(unittest.TestCase):
    def test_loading_text_is_preserved(self):
        self.assertEqual(_module_constant("LOADING_TEXT"), "Considering the evidence…")


@mock.patch.dict("os.environ", {pc._BASE_URL_ENV_VAR: _BASE_URL})
class AppSmokeTests(unittest.TestCase):
    def _run_app(self):
        at = AppTest.from_file(str(_APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def _markdown_values(self, at):
        return [m.value for m in at.markdown]

    def test_app_renders_with_title_and_styling_css(self):
        at = self._run_app()
        self.assertEqual([t.value for t in at.title], ["Voice of Emergence"])
        css = "\n".join(v for v in self._markdown_values(at) if "<style>" in v)
        self.assertIn('[data-testid="stChatMessageAvatarUser"]', css)
        self.assertIn('[data-testid="stChatMessageAvatarAssistant"]', css)
        self.assertIn("#voice-of-emergence", css)
        self.assertIn("visibility: hidden", css)
        self.assertEqual(len(at.chat_input), 1)

    def test_answer_turn_still_renders_g7_uncertainty_and_presentation(self):
        outcome = pc.AnswerTurn(
            primary_answer="A grounded answer.",
            uncertainty=("One open question remains.",),
            presentation_status="COMPOSED",
        )
        with mock.patch.object(pc.PilotClient, "create_session", return_value="s-1"), \
                mock.patch.object(pc.PilotClient, "run_turn", return_value=outcome) as run_turn:
            at = self._run_app()
            at.chat_input[0].set_value("What is ION?").run()

        self.assertFalse(at.exception, at.exception)
        run_turn.assert_called_once_with("s-1", "What is ION?")
        markdown = self._markdown_values(at)
        self.assertIn("**What remains uncertain**", markdown)
        self.assertIn("- One open question remains.", markdown)
        self.assertIn(
            "Presented in the Voice of Emergence style from the verified interpretation.",
            [c.value for c in at.caption],
        )


if __name__ == "__main__":
    unittest.main()
