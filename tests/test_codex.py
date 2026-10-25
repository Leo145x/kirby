"""Tests for the Codex MCP server's pure parts: python3 -m unittest discover -s tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "codex"))

from i18n import TEXT, pick_lang  # noqa: E402
import server  # noqa: E402


class PickLang(unittest.TestCase):
    def test_lang_picks_the_dialog_language(self):
        for v in ("zh-TW", "zh_TW", "zh-Hant", "zh-HK", "繁體中文", "Traditional Chinese", "taiwanese"):
            self.assertEqual(pick_lang(v, None), "zh-TW", v)
        for v in ("zh-CN", "zh", "zh-Hans", "简体中文", "Simplified Chinese", "chinese", "中文"):
            self.assertEqual(pick_lang(v, None), "zh-CN", v)
        for v in ("english", "en", "japanese", "spanish"):
            self.assertEqual(pick_lang(v, None), "en", v)

    def test_with_no_lang_the_locale_decides_and_english_is_the_fallback(self):
        self.assertEqual(pick_lang(None, "zh_TW.UTF-8"), "zh-TW")
        self.assertEqual(pick_lang("", "zh_CN.UTF-8"), "zh-CN")
        self.assertEqual(pick_lang(None, "en_US.UTF-8"), "en")
        self.assertEqual(pick_lang(None, None), "en")
        # An explicit lang wins over the locale.
        self.assertEqual(pick_lang("japanese", "zh_TW.UTF-8"), "en")

    def test_every_language_has_distinct_option_labels_and_the_same_keys(self):
        for t in TEXT.values():
            self.assertEqual(len(set(t["options"].values())), 4)
            self.assertEqual(t.keys(), TEXT["en"].keys())
            for kind, scopes in TEXT["en"]["where"].items():
                self.assertEqual(t["where"][kind].keys(), scopes.keys())


class Server(unittest.TestCase):
    def test_project_dir_needs_exactly_one_existing_workspace(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            meta = lambda *ws: {"x-codex-turn-metadata": {"workspaces": {w: {} for w in ws}}}  # noqa: E731
            self.assertEqual(server.project_dir(meta(a)), a)
            self.assertIsNone(server.project_dir(meta(a, b)))
            self.assertIsNone(server.project_dir(meta(a + "/missing")))
            self.assertIsNone(server.project_dir(None))

    def test_terms_drop_anything_that_would_read_as_an_option(self):
        self.assertEqual(server.terms(["pdf", "-x", "", 3, "review"]), ["pdf", "review"])
        self.assertEqual(server.terms("pdf"), [])

    def test_bad_input_is_refused_before_running_anything(self):
        self.assertEqual(server.detect({"repos": ["not a repo"]}), (False, "repos must be a list of owner/repo"))
        self.assertFalse(server.detect({"repos": [f"o/r{i}" for i in range(6)]})[0])
        self.assertFalse(server.public({"query": "  "})[0])
        self.assertFalse(server.readme({"repo": "../etc"})[0])


if __name__ == "__main__":
    unittest.main()
