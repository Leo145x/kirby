"""Tests for the Codex MCP server's pure parts: python3 -m unittest discover -s tests"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "codex"))

from dialog import CANCEL, REVIEW_MAX, SCOPES, english, next_options, read_dialog, read_review  # noqa: E402
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


SHA = "a" * 40
NEEDED = {"needed": True, "repo": "o/r", "sha": SHA, "files": ["s/SKILL.md", "s/run.sh"]}


class Review(unittest.TestCase):
    """The model review's result as the install tool takes it (docs/adr/0002): only when the check asked for one
    does it reach the dialog, checked against a fixed structure, cleaned and within the limits."""

    def test_findings_are_warn_lines_labelled_as_the_models(self):
        lines, problem = read_review({"findings": [{"file": "s/run.sh", "line": 3, "reason": "Sends the token to a host."}]},
                                     SHA, NEEDED)
        self.assertIsNone(problem)
        self.assertEqual(lines, ["warn: s/run.sh:3: Sends the token to a host. (model review, as reported by the model)"])
        self.assertEqual(read_review({"findings": []}, SHA, NEEDED),
                         (["model review: nothing found (as reported by the model)"], None))

    def test_a_missing_review_or_one_that_could_not_run_is_one_unchecked_line(self):
        self.assertEqual(read_review(None, None, NEEDED), (["model review: unchecked (no review result was passed)"], None))
        self.assertEqual(read_review({"could_not_run": "no subagent tool"}, None, NEEDED),
                         (["model review: unchecked (no subagent tool)"], None))
        self.assertEqual(read_review(None, None, {"needed": True, "files": []}),
                         (["model review: unchecked (kirby had no files of it to read)"], None))

    def test_a_review_of_another_commit_is_unchecked(self):
        self.assertEqual(read_review({"findings": []}, "b" * 40, NEEDED),
                         (["model review: unchecked (it read bbbbbbb, not aaaaaaa, the one checked here)"], None))

    def test_without_a_danger_or_warn_finding_no_review_reaches_the_dialog(self):
        quiet = {**NEEDED, "needed": False}
        for raw in (None, {"findings": [{"file": "s/run.sh", "line": 1, "reason": "x"}]}, {"could_not_run": "x"}, "junk"):
            self.assertEqual(read_review(raw, SHA, quiet), ([], None), raw)

    def test_hidden_and_control_characters_are_stripped(self):
        reason = "Reads​ ~/.ssh‮ and\nposts\tit."
        lines, _ = read_review({"findings": [{"file": "s/run.sh", "line": 1, "reason": reason}]}, SHA, NEEDED)
        self.assertEqual(lines, ["warn: s/run.sh:1: Reads ~/.ssh and posts it. (model review, as reported by the model)"])
        lines, _ = read_review({"could_not_run": "timed\x1b[2J out"}, None, NEEDED)
        self.assertEqual(lines, ["model review: unchecked (timed [2J out)"])

    def test_anything_outside_the_structure_or_the_limits_is_refused(self):
        ok = {"file": "s/run.sh", "line": 1, "reason": "Runs a download."}
        for raw, sha, problem in [
            ("could not run: x", SHA, 'review must be {"findings": [...]} or {"could_not_run": "<reason>"}'),
            ({"findings": [], "could_not_run": "x"}, SHA, 'review must be {"findings": [...]} or {"could_not_run": "<reason>"}'),
            ({"findings": [ok] * 6}, SHA, "review.findings must be a list of at most 5"),
            ({"findings": [{**ok, "reason": "x" * 121}]}, SHA, "review.findings[0].reason must be one sentence of at most 120 characters"),
            ({"findings": [{**ok, "reason": " ​ "}]}, SHA, "review.findings[0].reason must be one sentence of at most 120 characters"),
            ({"findings": [ok, {**ok, "file": "s/other.sh"}]}, SHA, "review.findings[1].file must be one of the files the check tool listed"),
            ({"findings": [{**ok, "line": 0}]}, SHA, "review.findings[0].line must be a line number"),
            ({"findings": [{**ok, "line": True}]}, SHA, "review.findings[0].line must be a line number"),
            ({"findings": [{**ok, "quote": "x"}]}, SHA, "review.findings[0] must have exactly file, line and reason"),
            ({"could_not_run": "x" * 121}, SHA, "review.could_not_run must be a reason of at most 120 characters"),
            ({"findings": [ok]}, None, "sha must be the one the check tool returned, which the review read"),
        ]:
            self.assertEqual(read_review(raw, sha, NEEDED), ([], problem), raw)
        # The limits count characters, not bytes.
        self.assertIsNone(read_review({"findings": [{**ok, "reason": "讀" * 120}]}, SHA, NEEDED)[1])

    def test_the_codex_skill_asks_the_subagent_for_the_structure_and_limits_the_tool_takes(self):
        # Claude Code's reviewer agent carries the same instructions as its own prompt (tests/register.test.ts).
        skill = Path(__file__).resolve().parent.parent / "codex/skills/inhale/SKILL.md"
        prompt = skill.read_text().split("You review the files of an agent tool", 1)[1].split("```", 1)[0]
        self.assertIn('{"findings": [{"file": "<a path from FILES>", "line": <line number>, "reason": "<one sentence in '
                      f'your own words, at most {REVIEW_MAX["reason"]} characters', prompt)
        self.assertIn(f'At most {REVIEW_MAX["findings"]} findings', prompt)
        self.assertIn('{"could_not_run": "<why, at most 120 characters>"}', prompt)
        # The subagent reviews on its own: what the main model fills in is where the files are, and which.
        self.assertEqual(set(re.findall(r"<[A-Z]+>", prompt)), {"<READ>", "<FILES>"})

    def test_the_claude_code_skill_gives_the_reviewer_only_where_the_files_are_and_which(self):
        text = (Path(__file__).resolve().parent.parent / "skills/inhale/SKILL.md").read_text()
        self.assertIn("`subagent_type` `kirby:reviewer`", text)
        self.assertIn("```\nREAD: <READ>\nFILES: <FILES>\n```", text)
        self.assertNotIn("You review the files of an agent tool", text)


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

    def test_the_file_tool_reads_an_mcp_servers_package_through_the_check(self):
        ran, script = [], server.script
        server.script = lambda name, *args, cwd=None: ran.append((name, *args)) or (True, "fetch(u)\n")
        package = {"ecosystem": "npm", "name": "@o/srv", "version": "1.2.3"}
        digest = "e" * 64
        try:
            self.assertEqual(server.file({"package": package, "path": "dist/index.js", "ref": digest}), (True, "fetch(u)\n"))
            for bad in [{"ref": SHA}, {"path": "../x"}, {"package": {**package, "ecosystem": "cargo"}},
                        {"package": {**package, "version": ""}}, {"repo": "o/r"}]:
                ok, out = server.file({"package": package, "path": "dist/index.js", "ref": digest, **bad})
                self.assertFalse(ok, bad)
        finally:
            server.script = script
        self.assertEqual(ran, [("check_mcp.py", "--read", json.dumps({**package, "sha": digest, "path": "dist/index.js"}))])

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

    ARGS = ["probe", "--", "npx", "-y", "probe"]
    CHECK = {"mcp_args": ["probe", "--", "npx", "-y", "probe@1.0.0"], "blocked": False,
             "lines": ["package: probe@1.0.0 (npm), named by this repo's package.json; not verified to come from this repo",
                       "pinned: only probe, to 1.0.0; its dependencies are not pinned, so they may differ from those "
                       "checked when the server starts",
                       "check: nothing found (3 files, 2 npm dependencies, advisory and malware lookups)"],
             "note": "scan: the dialog showed the user no pattern hits in the npm package probe@1.0.0",
             "review": {"needed": False, "package": {"ecosystem": "npm", "name": "probe", "version": "1.0.0"}, "sha": "e" * 64,
                        "files": ["dist/index.js"]}}

    def install(self, *answers, dialog=GOOD, check=None):
        ran, scripts, run, script = [], [], server.run, server.script

        def fake(argv, cwd=None):
            ran.append(argv)
            return True, '[1, "2026-01-01T00:00:00Z", false]' if argv[0] == "gh" else "added"

        def fake_script(name, *args, cwd=None):
            scripts.append((name, *args))
            return True, json.dumps(check or self.CHECK)

        server.run, server.script = fake, fake_script
        try:
            peer = self.Peer(*answers)
            r = server.install(peer, {"repo": "o/r", "kind": "mcp", "mcp_args": self.ARGS, "dialog": dialog}, None)
        finally:
            server.run, server.script = run, script
        self.scripts = scripts
        return peer, [a for a in ran if a[0] == "codex"], r

    def test_the_dialog_shows_the_check_and_the_pinned_command_installs(self):
        peer, ran, r = self.install("安裝", server.USER_OPTION)
        self.assertEqual(self.scripts, [("check_mcp.py", "--", "o/r", json.dumps(self.ARGS))])
        self.assertIn("\n".join(["MCP server: codex mcp add probe -- npx -y probe@1.0.0", *self.CHECK["lines"], server.USER_ONLY]),
                      peer.asked[0][0])
        self.assertEqual(peer.asked[1], (GOOD["scope"], [CANCEL, server.USER_OPTION]))
        self.assertEqual(ran, [["codex", "mcp", "add", "probe", "--", "npx", "-y", "probe@1.0.0"]])
        self.assertTrue(r.startswith("installed (scope user): codex mcp add probe -- npx -y probe@1.0.0\nadded\n"))
        self.assertTrue(r.endswith(f"\n{self.CHECK['note']}"), r)

    def test_cancel_at_the_scope_dialog_runs_nothing(self):
        peer, ran, r = self.install("安裝", CANCEL)
        self.assertEqual((len(peer.asked), ran), (2, []))
        self.assertEqual(r, f"not installed: the user cancelled at the scope step.\n{self.CHECK['note']}")

    def test_a_blocked_server_offers_no_install(self):
        peer, ran, r = self.install("取消", check={**self.CHECK, "blocked": True})
        self.assertEqual((peer.asked[0][1], ran), (GOOD["options"][:3], []))

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
        # A blocked install gets no model review: Install is not offered anyway.
        "review": {"needed": False, "repo": "o/r", "sha": "a" * 40, "files": ["s/SKILL.md", "s/package-lock.json"]},
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
        self.assertNotIn("model review", question)

    def test_without_a_block_install_is_offered(self):
        peer, _ = self.install({**self.CHECK, "blocked": False}, "取消")
        self.assertEqual(peer.asked[0][1], GOOD["options"])


class ModelReview(unittest.TestCase):
    """check → the model review, when the check asks for one → install with the sha checked and the review's
    result (docs/adr/0002). install decides from its own check whether a review was needed."""

    CHECK = {
        "name": "s", "commit": "aaaaaaa", "sha": SHA, "files": 2, "scripts": ["run.sh"], "exists": False,
        "check_lines": ["scan: 2 files, the ones installed; a pattern match, not a safety review", "warn: credentials ×1 (run.sh:1)"],
        "scan_note": "scan: the dialog showed the user these pattern hits", "lookup_note": "lookups: none", "blocked": False,
        "review": NEEDED,
    }
    FINDING = {"file": "s/run.sh", "line": 1, "reason": "Reads the SSH key."}
    LINE = "warn: s/run.sh:1: Reads the SSH key. (model review, as reported by the model)"

    def call(self, a, *answers, check=None, tool="install"):
        run, script = server.run, server.script
        server.run = lambda argv, cwd=None: (True, '[1, "2026-01-01T00:00:00Z", false]')
        server.script = lambda name, *args, cwd=None: (True, json.dumps(check or self.CHECK))
        try:
            peer = OneScope.Peer(*answers)
            r = server.check(a, None) if tool == "check" else server.install(peer, a, None)
        finally:
            server.run, server.script = run, script
        return peer, r

    SKILL = {"repo": "o/r", "kind": "skill", "folder": "s", "dialog": GOOD}

    def test_check_gives_what_the_review_reads_and_the_other_findings(self):
        _, (ok, out) = self.call(self.SKILL, tool="check")
        self.assertTrue(ok)
        self.assertEqual(json.loads(out), {
            "review": "needed", "read": {"repo": "o/r", "ref": SHA}, "files": ["s/SKILL.md", "s/run.sh"],
            "findings": ["skill: s · commit aaaaaaa · 2 files", "scripts: 1, e.g. run.sh", *self.CHECK["check_lines"],
                         server.SKILL_USER_ONLY],
            "blocked": False})

    def test_check_says_when_no_review_is_needed_or_possible(self):
        _, (_, out) = self.call(self.SKILL, check={**self.CHECK, "review": {**NEEDED, "needed": False}}, tool="check")
        self.assertEqual(json.loads(out)["review"], "not needed")
        self.assertNotIn("files", json.loads(out))
        _, (_, out) = self.call(self.SKILL, check={**self.CHECK, "review": {"needed": True, "files": []}}, tool="check")
        self.assertEqual(json.loads(out)["review"], "not possible: kirby has no files of it to read; call install without review")

    def test_check_lists_at_most_200_files_and_counts_the_rest(self):
        many = {**NEEDED, "files": [f"s/{i}.md" for i in range(250)]}
        _, (_, out) = self.call(self.SKILL, check={**self.CHECK, "review": many}, tool="check")
        self.assertEqual((len(json.loads(out)["files"]), json.loads(out)["more_files"]), (200, 50))

    def test_check_refuses_what_install_refuses(self):
        _, (ok, out) = self.call({"repo": "o/r", "kind": "skill"}, tool="check")
        self.assertEqual((ok, out), (False, "not checked: kind=skill needs folder"))

    def test_the_reviews_findings_follow_the_check_in_the_dialog_and_in_every_result(self):
        peer, r = self.call({**self.SKILL, "sha": SHA, "review": {"findings": [self.FINDING]}}, "取消")
        self.assertIn("\n".join([*self.CHECK["check_lines"], self.LINE, server.SKILL_USER_ONLY]), peer.asked[0][0])
        self.assertEqual(peer.asked[0][1], GOOD["options"])
        self.assertEqual(r, "not installed: the user cancelled.\nscan: the dialog showed the user these pattern hits\n"
                            f"lookups: none\nreview: the dialog showed the user these model review lines:\n  {self.LINE}")

    def test_without_a_review_the_dialog_says_so_and_install_stays(self):
        peer, r = self.call(self.SKILL, "取消")
        self.assertIn("warn: credentials ×1 (run.sh:1)\nmodel review: unchecked (no review result was passed)\n",
                      peer.asked[0][0])
        self.assertEqual(peer.asked[0][1], GOOD["options"])
        self.assertTrue(r.endswith("\n  model review: unchecked (no review result was passed)"), r)

    def test_a_review_the_check_did_not_ask_for_is_left_out(self):
        quiet = {**self.CHECK, "review": {**NEEDED, "needed": False}}
        peer, r = self.call({**self.SKILL, "sha": SHA, "review": {"findings": [self.FINDING]}}, "取消", check=quiet)
        self.assertNotIn("model review", peer.asked[0][0] + r)

    def test_a_review_outside_the_structure_opens_no_dialog(self):
        peer, r = self.call({**self.SKILL, "sha": SHA, "review": {"findings": [self.FINDING] * 6}})
        self.assertEqual(peer.asked, [])
        self.assertEqual(r, "not installed: review.findings must be a list of at most 5; call this tool again with "
                            "review as the inhale skill describes.")

    def test_a_review_outside_the_structure_also_says_why_the_dialogs_would_be_in_english(self):
        # As Claude Code does: the model can fix both in its next call.
        a = {"repo": "o/r", "kind": "skill", "folder": "s", "sha": SHA, "review": {"findings": [self.FINDING] * 6}}
        _, r = self.call(a)
        self.assertEqual(r, "not installed: review.findings must be a list of at most 5; call this tool again with "
                            "review as the inhale skill describes.\nnote: the dialogs were in English because no dialog "
                            "was given; pass dialog as the inhale skill describes.")
        _, r = self.call({"repo": "o/r", "kind": "skill"})
        self.assertEqual(r, "not installed: kind=skill needs folder\nnote: the dialogs were in English because no dialog "
                            "was given; pass dialog as the inhale skill describes.")

    def test_an_mcp_servers_review_line_comes_before_where_it_installs(self):
        package = {"needed": True, "package": {"ecosystem": "npm", "name": "probe", "version": "1.0.0"}, "sha": "e" * 64,
                   "files": ["dist/index.js"]}
        check = {**OneScope.CHECK, "review": package}
        a = {"repo": "o/r", "kind": "mcp", "mcp_args": OneScope.ARGS, "dialog": GOOD}
        _, (_, out) = self.call(a, check=check, tool="check")
        self.assertEqual(json.loads(out)["read"], {"package": package["package"], "ref": "e" * 64})
        peer, _ = self.call({**a, "sha": "e" * 64, "review": {"findings": []}}, "取消", check=check)
        self.assertIn(f"{OneScope.CHECK['lines'][-1]}\nmodel review: nothing found (as reported by the model)\n{server.USER_ONLY}",
                      peer.asked[0][0])


class Plugin(unittest.TestCase):
    """A plugin: the dialog shows check_plugin.py's check; a marketplace already added is checked at the commit
    it is at and not added again; after the install, a plugin from another commit is removed again."""

    SHA, OLD = "a" * 40, "c" * 40
    CHECK = {"marketplace": "mk", "marketplace_file": ".claude-plugin/marketplace.json", "sha": SHA, "commit": "aaaaaaa",
             "blocked": False, "lines": ["plugin: p · marketplace mk · commit aaaaaaa · 2 files", "source: plugins/p/ in this repo",
                                         "scan: 2 files, the ones installed; a pattern match, not a safety review"],
             "note": "scan: the dialog showed the user no pattern hits in o/mk at commit " + SHA,
             "review": {"needed": False, "repo": "o/mk", "sha": SHA, "files": ["plugins/p/a.md", "plugins/p/b.md"]}}

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
                got = listed.pop(0) if len(listed) > 1 else listed[0]
                return (False, "boom") if got is None else (True, json.dumps({"marketplaces": got}))
            if argv[0] == "git":
                head = heads.pop(0)
                return (False, "fatal: not a git repository") if head is None else (True, head)
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

    def test_a_marketplace_list_that_fails_is_one_unchecked_line_and_the_check_goes_ahead(self):
        line = ("unchecked: whether this marketplace is already added (codex plugin marketplace list failed: boom); the check is "
                "of its repo as it stands, and the plugin is removed again if kirby cannot tell it installs from that commit")
        peer, ran, scripts, r = self.install("安裝", server.USER_OPTION, listed=[None])
        self.assertEqual(scripts, [("check_plugin.py", "--agent", "codex", "--", "o/mk", "p")])
        self.assertIn(f"{self.CHECK['lines'][0]}\n{line}\n", peer.asked[0][0])
        # Still unable to tell which commit it came from after the install, kirby removes it again.
        self.assertEqual(ran[-1], ["codex", "plugin", "remove", "p@mk"])
        self.assertTrue(r.startswith("install failed (scope user): "), r)
        self.assertTrue(r.endswith(f"{self.CHECK['note']}\n{line}"), r)

    def test_an_added_marketplace_whose_commit_cannot_be_read_is_one_unchecked_line(self):
        line = ("unchecked: which commit the marketplace mk, already added, is at (could not read it in "
                "/home/u/.codex/.tmp/marketplaces/mk: fatal: not a git repository); the check is of its repo as it stands, and "
                "the plugin is removed again if kirby cannot tell it installs from that commit")
        peer, ran, scripts, r = self.install("安裝", server.USER_OPTION, listed=[[self.added()]], heads=[None, self.SHA])
        self.assertEqual(scripts, [("check_plugin.py", "--agent", "codex", "--", "o/mk", "p")])
        self.assertIn(f"{self.CHECK['lines'][0]}\n{line}\n", peer.asked[0][0])
        # Readable after the install and the commit checked: the plugin stays.
        self.assertEqual(ran, [["codex", "plugin", "add", "p@mk"]])
        self.assertTrue(r.startswith("installed (scope user): codex plugin add p@mk\n"), r)

    def test_a_blocked_plugin_offers_no_install(self):
        peer, ran, _, r = self.install("取消", check={**self.CHECK, "blocked": True})
        self.assertEqual((peer.asked[0][1], ran), (GOOD["options"][:3], []))


if __name__ == "__main__":
    unittest.main()
