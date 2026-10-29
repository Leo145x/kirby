"""Tests for the Codex MCP server's pure parts: python3 -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "codex"))

from dialog import CANCEL, SCOPES, english, next_options, read_dialog  # noqa: E402
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

    def test_a_blocked_install_leaves_install_out_of_the_first_dialog(self):
        d, _ = read_dialog(GOOD)
        self.assertEqual(next_options(d, blocked=False), ["取消", "先讀 README", "換一個", "安裝"])
        self.assertEqual(next_options(d, blocked=True), ["取消", "先讀 README", "換一個"])


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

class Blocked(unittest.TestCase):
    """A skill whose malware lookup found something: the first dialog shows the lookups and offers no
    Install, and every result tells the model why."""

    CHECK = {
        "name": "s", "commit": "aaaaaaa", "sha": "a" * 40, "files": 2, "scripts": [], "exists": False,
        "check_lines": ["scan: 2 files, the ones installed; a pattern match, not a safety review", "flagged: nothing",
                        "dependencies: package-lock.json: 1 npm",
                        "blocked: the malware lookup found a known-malicious package, so Install is not offered",
                        "danger: evil@1.0.0 (npm) is a known-malicious package (MAL-2026-1)"],
        "scan_note": "scan: the dialog showed the user no pattern hits",
        "lookup_note": "lookups: …\nblocked: the dialog did not offer Install, because …",
        "blocked": True,
    }

    def install(self, check, *answers):
        run, script = server.run, server.script
        server.run = lambda argv, cwd=None: (True, '[1, "2026-01-01T00:00:00Z", false]')
        server.script = lambda name, *args, cwd=None: (True, json.dumps(check))
        try:
            peer = OneScope.Peer(*answers)
            r = server.install(peer, {"repo": "o/r", "kind": "skill", "folder": "s", "dialog": GOOD}, None)
        finally:
            server.run, server.script = run, script
        return peer, r

    def test_the_first_dialog_shows_the_lookups_and_offers_no_install(self):
        peer, r = self.install(self.CHECK, "取消")
        question, options = peer.asked[0]
        self.assertEqual(options, ["取消", "先讀 README", "換一個"])
        self.assertIn("skill: s · commit aaaaaaa · 2 files\n" + "\n".join(self.CHECK["check_lines"]), question)
        self.assertEqual(r, "not installed: the user cancelled.\nscan: the dialog showed the user no pattern hits\n"
                            + self.CHECK["lookup_note"])

    def test_without_a_block_install_is_offered(self):
        peer, _ = self.install({**self.CHECK, "blocked": False}, "取消")
        self.assertEqual(peer.asked[0][1], GOOD["options"])


class Plugin(unittest.TestCase):
    """A plugin: the dialog shows check_plugin.py's check; a marketplace already added is checked at the commit
    it is at and not added again; after the install, a plugin from another commit is removed again."""

    SHA, OLD = "a" * 40, "c" * 40
    CHECK = {"marketplace": "mk", "marketplace_file": ".claude-plugin/marketplace.json", "sha": SHA, "commit": "aaaaaaa",
             "blocked": False, "lines": ["plugin: p · marketplace mk · commit aaaaaaa · 2 files", "source: plugins/p/ in this repo",
                                         "scan: 2 files, the ones installed; a pattern match, not a safety review"],
             "note": "scan: the dialog showed the user no pattern hits in o/mk at commit " + SHA}

    def install(self, *answers, listed=([],), heads=(), check=None):
        """listed: the marketplaces Codex lists, call by call (the last stays); heads: what git rev-parse HEAD
        gives in their root, call by call."""
        ran, scripts, heads, listed = [], [], list(heads), list(listed)
        run, script = server.run, server.script

        def fake_run(argv, cwd=None):
            ran.append(argv)
            if argv[0] == "gh":
                return True, '[1, "2026-01-01T00:00:00Z", false]'
            if argv[:4] == ["codex", "plugin", "marketplace", "list"]:
                return True, json.dumps({"marketplaces": listed.pop(0) if len(listed) > 1 else listed[0]})
            if argv[0] == "git":
                return True, heads.pop(0)
            return True, "ok"

        def fake_script(name, *args, cwd=None):
            scripts.append((name, *args))
            return True, json.dumps(check or self.CHECK)

        server.run, server.script = fake_run, fake_script
        try:
            peer = OneScope.Peer(*answers)
            r = server.install(peer, {"repo": "o/mk", "kind": "plugin", "plugin": "p", "dialog": GOOD}, None)
        finally:
            server.run, server.script = run, script
        return peer, [a for a in ran if a[0] == "codex" and a[3] != "list"], scripts, r

    def added(self, source="https://github.com/O/mk.git"):
        return {"name": "mk", "root": "/home/u/.codex/.tmp/marketplaces/mk", "marketplaceSource": {"sourceType": "git", "source": source}}

    def test_the_dialog_shows_the_check_and_a_new_marketplace_is_added_without_a_ref_then_checked(self):
        peer, ran, scripts, r = self.install("安裝", server.USER_OPTION, listed=[[], [self.added()]], heads=[self.SHA])
        self.assertEqual(scripts, [("check_plugin.py", "--agent", "codex", "--", "o/mk", "p")])
        self.assertIn("\n".join([self.CHECK["lines"][0], "marketplace: .claude-plugin/marketplace.json (Claude Code format)",
                                 *self.CHECK["lines"][1:], server.USER_ONLY]), peer.asked[0][0])
        # No --ref, so `codex plugin marketplace upgrade` keeps working (docs/adr/0003).
        self.assertEqual(ran, [["codex", "plugin", "marketplace", "add", "o/mk"], ["codex", "plugin", "add", "p@mk"]])
        self.assertTrue(r.startswith("installed (scope user): codex plugin marketplace add o/mk\ncodex plugin add p@mk\n"))
        self.assertTrue(r.endswith("\nnext: The user starts a new Codex session to use it.\n" + self.CHECK["note"]), r)

    def test_a_plugin_from_another_commit_is_removed_again(self):
        _, ran, _, r = self.install("安裝", server.USER_OPTION, listed=[[], [self.added()]], heads=[self.OLD])
        self.assertEqual(ran[-1], ["codex", "plugin", "remove", "p@mk"])
        self.assertTrue(r.startswith("install failed (scope user): codex plugin marketplace add o/mk\ncodex plugin add p@mk\n"
                                     "codex plugin remove p@mk\n"), r)
        self.assertTrue(r.endswith("\nthe marketplace mk has moved on: it is at commit ccccccc after the install, not aaaaaaa "
                                   "as shown to the user; the plugin was removed again\n" + self.CHECK["note"]), r)

    def test_a_marketplace_already_added_is_checked_at_its_commit_and_not_added_again(self):
        old = {**self.CHECK, "sha": self.OLD, "commit": "ccccccc"}
        line = "marketplace: already added as mk, at commit ccccccc; installs from it as it is"
        peer, ran, scripts, r = self.install("安裝", server.USER_OPTION, listed=[[self.added()]], heads=[self.OLD, self.OLD], check=old)
        self.assertEqual(scripts, [("check_plugin.py", "--agent", "codex", "--commit", self.OLD, "--", "o/mk", "p")])
        self.assertIn(f"{old['lines'][0]}\n{line}\n", peer.asked[0][0])
        self.assertEqual(ran, [["codex", "plugin", "add", "p@mk"]])
        self.assertTrue(r.startswith("installed (scope user): codex plugin add p@mk\n"), r)
        self.assertTrue(r.endswith(f"{old['note']}\n{line}"), r)

    def test_a_marketplace_from_another_source_is_not_taken_for_this_one(self):
        _, ran, scripts, _ = self.install("安裝", server.USER_OPTION, listed=[[self.added("https://github.com/o/other.git")]])
        self.assertEqual(scripts[0][-2:], ("o/mk", "p"))
        self.assertNotIn("--commit", scripts[0])
        self.assertEqual(ran[0][:4], ["codex", "plugin", "marketplace", "add"])

    def test_a_blocked_plugin_offers_no_install(self):
        peer, ran, _, r = self.install("取消", check={**self.CHECK, "blocked": True})
        self.assertEqual((peer.asked[0][1], ran), (GOOD["options"][:3], []))


if __name__ == "__main__":
    unittest.main()
