"""Tests for the Codex MCP server's pure parts: python3 -m unittest discover -s tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "codex"))

from dialog import CANCEL, SCOPES, english, read_dialog  # noqa: E402
import server  # noqa: E402

GOOD = {
    "about": "把 archify 裝成 skill。",
    "next": "下一步？",
    "options": ["取消", "先讀 README", "換一個", "安裝"],
    "scope": "裝在哪個範圍？",
}


class Dialog(unittest.TestCase):
    def test_the_models_wording_is_used_when_it_is_complete(self):
        d, problem = read_dialog(GOOD)
        self.assertIsNone(problem)
        self.assertEqual(d, GOOD)

    def test_the_scope_options_are_the_tools_own(self):
        # Extra keys from an older skill, such as scopes, are ignored.
        d, problem = read_dialog({**GOOD, "scopes": {"user": "你所有的專案"}})
        self.assertIsNone(problem)
        self.assertNotIn("scopes", d)
        self.assertEqual(len({CANCEL, *SCOPES}), 4)

    def test_missing_or_unusable_wording_falls_back_to_english_and_says_why(self):
        self.assertEqual(read_dialog(None), (english(), "no dialog was given"))
        bad = [
            {**GOOD, "next": ""},
            {**GOOD, "scope": "  "},
            {**GOOD, "options": ["取消", "先讀 README", "安裝"]},
            {**GOOD, "options": ["取消", "取消", "換一個", "安裝"]},
            {**GOOD, "about": "x" * 601},
        ]
        for raw in bad:
            d, problem = read_dialog(raw)
            self.assertEqual(d, english())
            self.assertIsInstance(problem, str)


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
        sha = "a" * 40
        self.assertFalse(server.file({"repo": "o/r", "path": "../x", "ref": sha})[0])
        self.assertFalse(server.file({"repo": "o/r", "path": "/etc/passwd", "ref": sha})[0])
        self.assertFalse(server.file({"repo": "o/r", "path": "a.sh", "ref": "main"})[0])
        self.assertFalse(server.file({"repo": "o/r/x", "path": "a.sh", "ref": sha})[0])


if __name__ == "__main__":
    unittest.main()
