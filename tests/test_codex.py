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

    def test_stars_passes_only_the_options_it_was_given(self):
        ran, script = [], server.script
        server.script = lambda name, *args, cwd=None: ran.append((name, *args)) or (True, "")
        try:
            server.stars({})
            server.stars({"lists": True, "list": "ai", "match": ["pdf", "-x"], "refresh": True})
            server.stars({"lists": "yes", "list": "", "refresh": 1})
        finally:
            server.script = script
        self.assertEqual(ran, [("stars.py",), ("stars.py", "--lists", "--list", "ai", "--match", "pdf", "--refresh"),
                               ("stars.py",)])

    def test_every_tool_states_all_four_hints(self):
        hints = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
        for tool in server.TOOLS:
            a = tool["annotations"]
            self.assertEqual(sorted(a), sorted(hints), tool["name"])
            self.assertTrue(all(type(v) is bool for v in a.values()), tool["name"])
            self.assertEqual(a["readOnlyHint"], tool["name"] != "install", tool["name"])


class OneScope(unittest.TestCase):
    """An MCP server goes to user only: the first dialog says so, and the scope dialog's install option,
    in the server's words, says it again, so a first dialog with its options out of order cannot install
    unseen."""

    class Peer:
        can_elicit = True

        def __init__(self, *answers):
            self.answers, self.asked = list(answers), []

        def ask(self, question, options):
            self.asked.append((question, options))
            return self.answers.pop(0)

    def install(self, *answers, dialog=GOOD):
        ran, run = [], server.run

        def fake(argv, cwd=None):
            ran.append(argv)
            return True, '[1, "2026-01-01T00:00:00Z", false]' if argv[0] == "gh" else "added"

        server.run = fake
        try:
            peer = self.Peer(*answers)
            args = ["probe", "--", "npx", "-y", "probe"]
            r = server.install(peer, {"repo": "o/r", "kind": "mcp", "mcp_args": args, "dialog": dialog}, None)
        finally:
            server.run = run
        return peer, [a for a in ran if a[0] == "codex"], r

    def test_the_scope_dialog_says_where_in_the_servers_words(self):
        peer, ran, r = self.install("安裝", server.USER_OPTION)
        self.assertIn(f"{server.MCP_NOT_SCANNED}\n{server.USER_ONLY}", peer.asked[0][0])
        self.assertEqual(peer.asked[1], (GOOD["scope"], [CANCEL, server.USER_OPTION]))
        self.assertEqual(ran, [["codex", "mcp", "add", "probe", "--", "npx", "-y", "probe"]])
        self.assertTrue(r.startswith("installed (scope user): codex mcp add probe -- npx -y probe\nadded\n"))

    def test_cancel_at_the_scope_dialog_runs_nothing(self):
        peer, ran, r = self.install("安裝", CANCEL)
        self.assertEqual((len(peer.asked), ran), (2, []))
        self.assertEqual(r, f"not installed: the user cancelled at the scope step.\n{server.MCP_NOT_SCANNED}")

    def test_options_out_of_order_still_meet_the_scope_dialog(self):
        # The model put cancel last, so the user's cancel reads as install; the scope dialog still stops it.
        swapped = {**GOOD, "options": ["安裝", "先讀 README", "換一個", "取消"]}
        peer, ran, r = self.install("取消", CANCEL, dialog=swapped)
        self.assertEqual((len(peer.asked), ran), (2, []))
        self.assertTrue(r.startswith("not installed: the user cancelled at the scope step."))

if __name__ == "__main__":
    unittest.main()
