"""Tests for the advisory and malware lookups (lookups.py), with OSV.dev, GitHub, npm and uv faked:
python3 -m unittest discover -s tests"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills/inhale/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("lookups", SCRIPTS / "lookups.py")
assert spec and spec.loader
lookups = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lookups)
from words import in_english, say  # noqa: E402


def en(r):
    """The lookups' part of the dialog, in English, as the check tool's findings give it."""
    return in_english(lookups.summary(r))

SHA = "c" * 40
LODASH_HIGH = {"id": "GHSA-35jh-r3h4-6jhm", "aliases": ["CVE-2021-23337"], "summary": "Command Injection in lodash",
               "database_specific": {"severity": "HIGH"}}


def lock(*packages):
    """A package-lock.json (lockfile version 3) holding these (name, version) pairs."""
    entries = {"": {"name": "skill"}, **{f"node_modules/{n}": {"version": v} for n, v in packages}}
    return json.dumps({"lockfileVersion": 3, "packages": entries})


class Net:
    """OSV.dev, GitHub, npm and uv as the tests need them. vulns maps (ecosystem, name, version or None)
    to the ids OSV returns for that query; commit is the ids for the pinned commit; fail names the parts
    that fail (osv, vulns, gh)."""

    def __init__(self, vulns=None, records=(), commit=(), advisories=(), tools=("npm", "uv"), resolve=None, fail=()):
        self.vulns, self.commit, self.advisories_, self.tools, self.resolve, self.fail = (
            vulns or {}, list(commit), list(advisories), tools, resolve or {}, fail)
        self.records = {r["id"]: r for r in records}
        self.queries, self.ran, self.given = [], [], []

    def querybatch(self, queries):
        if "osv" in self.fail:
            raise lookups.Failed("OSV.dev: timed out")
        self.queries += queries
        out = []
        for q in queries:
            if "commit" in q:
                ids = self.commit
            else:
                ids = self.vulns.get((q["package"]["ecosystem"], q["package"]["name"], q.get("version")), [])
            out.append({"vulns": [{"id": i} for i in ids]} if ids else {})
        return out

    def vuln(self, vid):
        if "vulns" in self.fail:
            raise lookups.Failed("OSV.dev: timed out")
        return self.records.get(vid, {"id": vid})

    def advisories(self, repo):
        if "gh" in self.fail:
            raise lookups.Failed("gh api: HTTP 404")
        return self.advisories_

    def which(self, name):
        return name in self.tools

    def run(self, argv, cwd=None):
        """npm writes a lockfile into cwd; uv prints the pins. resolve maps the tool to what it gives."""
        self.ran.append((list(argv), sorted(p.name for p in Path(cwd).iterdir()) if cwd else None))
        self.given.append({p.name: p.read_text() for p in Path(cwd).iterdir()} if cwd else {})
        out = self.resolve.get(argv[0])
        if out is None:
            return False, f"{argv[0]} ERR! could not resolve"
        if argv[0] == "npm":
            (Path(cwd) / "package-lock.json").write_text(out)
            return True, ""
        return True, out


def check(files, net):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, content in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(content)
        return lookups.check("o/r", SHA, root, sorted(files), net)


class Dependencies(unittest.TestCase):
    def test_a_high_vulnerability_in_a_locked_dependency_is_danger(self):
        net = Net(vulns={("npm", "lodash", "4.17.20"): ["GHSA-35jh-r3h4-6jhm"]}, records=[LODASH_HIGH])
        r = check({"SKILL.md": "", "package-lock.json": lock(("lodash", "4.17.20"))}, net)
        self.assertEqual(en(r), [
            "✕ danger: lodash@4.17.20 (npm) has 1 published vulnerability, worst high (GHSA-35jh-r3h4-6jhm)",
            "dependencies: package-lock.json: 1 npm",
            "✓ malware lookup: nothing found",
        ])
        self.assertFalse(r["blocked"])
        # The dialog shows a summary, so the model gets each finding, and is told what the user saw of them.
        self.assertEqual(r["note"], "\n".join([
            f"lookups: the advisory and malware lookup findings for o/r at commit {SHA} (the dialog showed the user each "
            "danger one with its ids, and the warn ones by name only):",
            "  danger advisory lodash@4.17.20 (npm) GHSA-35jh-r3h4-6jhm high: Command Injection in lodash",
            "dependencies: package-lock.json: 1 npm",
        ]))

    def test_a_known_malicious_dependency_blocks_and_the_note_says_why(self):
        net = Net(vulns={("npm", "flatmap-stream", "0.1.1"): ["MAL-2025-20690"]})
        r = check({"package-lock.json": lock(("flatmap-stream", "0.1.1"))}, net)
        self.assertTrue(r["blocked"])
        self.assertEqual(en(r), [
            "✕ blocked: the malware lookup found a known-malicious package, so Install is not offered",
            "✕ danger: flatmap-stream@0.1.1 (npm) is listed as malicious (MAL-2025-20690)",
            "dependencies: package-lock.json: 1 npm",
            "✓ advisory lookup: nothing found",
        ])
        self.assertTrue(r["note"].endswith(
            "\nblocked: the dialog did not offer Install, because the malware lookup lists flatmap-stream@0.1.1 (npm) as "
            "known-malicious. kirby will not install it; tell the user why, and that installing it anyway means doing it "
            "by hand."), r["note"])

    def test_each_danger_finding_has_a_line_of_its_own_up_to_six_and_the_rest_are_counted(self):
        names = [f"evil{i}" for i in range(8)]
        net = Net(vulns={("npm", n, "1.0.0"): [f"MAL-2026-{i}"] for i, n in enumerate(names)})
        lines = en(check({"package-lock.json": lock(*[(n, "1.0.0") for n in names])}, net))
        self.assertEqual(lines[1:8], [f"✕ danger: evil{i}@1.0.0 (npm) is listed as malicious (MAL-2026-{i})" for i in range(6)]
                         + ["✕ danger: 2 more, listed for the model"])

    def test_a_moderate_or_unrated_vulnerability_is_warn_and_does_not_block(self):
        records = [{"id": "GHSA-aaaa-aaaa-aaaa", "database_specific": {"severity": "MODERATE"}}, {"id": "GHSA-bbbb-bbbb-bbbb"}]
        net = Net(vulns={("npm", "a", "1.0.0"): ["GHSA-aaaa-aaaa-aaaa", "GHSA-bbbb-bbbb-bbbb"]}, records=records)
        r = check({"package-lock.json": lock(("a", "1.0.0"))}, net)
        # A warn finding is named on the one warn line, without its ids, which the model gets.
        self.assertEqual(en(r)[0], "⚠ warn (1): 2 published vulnerabilities in a@1.0.0 (npm)")
        self.assertIn("\n  warn advisory a@1.0.0 (npm) GHSA-aaaa-aaaa-aaaa moderate\n", r["note"])
        self.assertFalse(r["blocked"])

    def test_the_worst_rated_come_first_and_a_record_without_a_summary_has_none(self):
        records = [LODASH_HIGH, {"id": "GHSA-zzzz-zzzz-zzzz", "database_specific": {"severity": "CRITICAL"}}]
        net = Net(vulns={("npm", "a", "1.0.0"): ["GHSA-35jh-r3h4-6jhm"], ("npm", "z", "1.0.0"): ["GHSA-zzzz-zzzz-zzzz"]},
                  records=records)
        r = check({"package-lock.json": lock(("a", "1.0.0"), ("z", "1.0.0"))}, net)
        self.assertEqual([line.split(" (")[0] for line in en(r)[:2]], ["✕ danger: z@1.0.0", "✕ danger: a@1.0.0"])
        self.assertIn("\n  danger advisory z@1.0.0 (npm) GHSA-zzzz-zzzz-zzzz critical\n", r["note"])

    def test_a_failed_lookup_is_unchecked_not_nothing_found(self):
        r = check({"package-lock.json": lock(("lodash", "4.17.20"))}, Net(fail=("osv",)))
        self.assertEqual(en(r), [
            "? unchecked: advisory and malware lookups for this commit, package-lock.json (OSV.dev: timed out)",
            "dependencies: package-lock.json: 1 npm",
            # GitHub still answered for the repo's own advisories.
            "✓ advisory lookup: nothing found in the rest",
        ])
        self.assertEqual(say(lookups.summary(r)[0], "zh-TW"),
                         "？ 未檢查：這個 commit、package-lock.json 的漏洞、惡意套件查詢（OSV.dev: timed out）")
        self.assertFalse(r["blocked"])
        self.assertIn("\n  unchecked: advisory lookup for this commit", r["note"])

    def test_with_no_dependency_files_only_the_repo_is_looked_up(self):
        net = Net()
        r = check({"SKILL.md": "", "scripts/run.py": ""}, net)
        # No line for the missing dependency files, and one line for both lookups.
        self.assertEqual(en(r), ["✓ advisory and malware lookups: nothing found"])
        self.assertEqual(net.queries, [{"commit": SHA}])
        self.assertEqual(r["note"], f"lookups: the dialog showed the user no findings from the advisory and malware "
                                    f"lookups for o/r at commit {SHA}\ndependencies: no npm or Python dependency files")


class Resolving(unittest.TestCase):
    PACKAGE = json.dumps({"name": "s", "dependencies": {"lodash": "^4.17.0"}, "devDependencies": {"left-pad": "1.x"}})

    def test_ranges_are_resolved_by_npm_without_running_scripts_and_the_dialog_says_so(self):
        net = Net(resolve={"npm": lock(("lodash", "4.17.20"), ("left-pad", "1.3.0"))},
                  vulns={("npm", "lodash", "4.17.20"): ["GHSA-35jh-r3h4-6jhm"]}, records=[LODASH_HIGH])
        r = check({"package.json": self.PACKAGE, ".npmrc": "registry=https://evil.invalid/"}, net)
        self.assertEqual(net.ran, [(["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
                                    ["package.json"])])
        self.assertEqual(en(r)[:2], [
            "✕ danger: lodash@4.17.20 (npm) has 1 published vulnerability, worst high (GHSA-35jh-r3h4-6jhm)",
            "dependencies: package.json: 2 npm, versions resolved at check time",
        ])

    def test_without_npm_the_names_are_looked_up_for_malware_and_the_advisory_lookup_is_unchecked(self):
        net = Net(tools=(), vulns={("npm", "left-pad", None): ["MAL-2024-1", "GHSA-cccc-cccc-cccc"]})
        r = check({"package.json": self.PACKAGE}, net)
        self.assertIn({"package": {"name": "lodash", "ecosystem": "npm"}}, net.queries)
        self.assertEqual(net.ran, [])
        self.assertTrue(r["blocked"])
        self.assertEqual(en(r), [
            "✕ blocked: the malware lookup found a known-malicious package, so Install is not offered",
            "✕ danger: left-pad (npm) is listed as malicious (MAL-2024-1); matched by name, the version was not resolved",
            "? unchecked: advisory lookup for package.json (npm not found, so versions were not resolved)",
            "dependencies: package.json: 2 npm, names only",
            "✓ advisory lookup: nothing found in the rest",
        ])

    def test_a_dependency_from_outside_the_registry_is_not_resolved(self):
        net = Net()
        r = check({"package.json": json.dumps({"dependencies": {"x": "github:evil/x", "y": "^1.0.0"}})}, net)
        self.assertEqual(net.ran, [])
        self.assertIn("? unchecked: advisory lookup for package.json (some dependencies come from outside the npm "
                      "registry, so versions were not resolved)", en(r))

    def test_a_failed_resolution_falls_back_to_the_names(self):
        r = check({"package.json": self.PACKAGE}, Net())
        self.assertIn("dependencies: package.json: 2 npm, names only", en(r))
        self.assertIn("? unchecked: advisory lookup for package.json (npm could not resolve the versions: npm ERR! could "
                      "not resolve)", en(r))

    def test_python_requirements_are_resolved_by_uv_without_building(self):
        net = Net(resolve={"uv": "requests==2.19.0\nurllib3==1.23\n"},
                  vulns={("PyPI", "requests", "2.19.0"): ["PYSEC-2018-28"]})
        r = check({"scripts/requirements.txt": "requests>=2\n# a comment\n-r other.txt\n"}, net)
        argv, _ = net.ran[0]
        self.assertEqual(argv[:4] + argv[-1:], ["uv", "pip", "compile", "--no-build", "requirements.txt"])
        self.assertIn("--no-config", argv)
        self.assertEqual(en(r)[:2], [
            "⚠ warn (1): 1 published vulnerability in requests@2.19.0 (PyPI)",
            "dependencies: scripts/requirements.txt: 2 PyPI, versions resolved at check time",
        ])

    def test_lockfiles_are_read_as_they_are(self):
        uv = ('version = 1\n[[package]]\nname = "Requests"\nversion = "2.19.0"\nsource = { registry = "https://pypi.org/simple" }\n'
              '[[package]]\nname = "skill"\nversion = "0.1.0"\nsource = { editable = "." }\n')
        net = Net()
        r = check({"uv.lock": uv, "pyproject.toml": "[project]\ndependencies = ['requests']\n",
                   "package-lock.json": lock(("a", "1.0.0"), ("b", "2.0.0")), "package.json": self.PACKAGE}, net)
        self.assertEqual(net.ran, [])
        self.assertEqual(en(r)[0], "dependencies: package-lock.json: 2 npm, uv.lock: 1 PyPI")
        self.assertIn({"package": {"name": "requests", "ecosystem": "PyPI"}, "version": "2.19.0"}, net.queries)

    def test_dependency_files_past_the_tenth_are_unchecked_not_dropped(self):
        files = {f"{d}/package-lock.json": lock(("a", "1.0.0")) for d in "abcdefghijkl"}
        r = check(files, Net())
        self.assertEqual([en(r)[0], *en(r)[2:]], [
            "? unchecked: advisory and malware lookups for more dependency files (k/package-lock.json, l/package-lock.json) "
            "(kirby reads at most 10)",
            "✓ advisory and malware lookups: nothing found in the rest"])
        self.assertIsNone(r["nothing_found"])
        self.assertIn("\n  unchecked: advisory lookup for 2 more dependency files", r["note"])

    def test_the_dialog_names_at_most_four_dependency_files(self):
        files = {f"{d}/package-lock.json": lock(("a", "1.0.0")) for d in "abcdef"}
        self.assertEqual(en(check(files, Net()))[0], "dependencies: a/package-lock.json: 1 npm, b/package-lock.json: "
                         "1 npm, c/package-lock.json: 1 npm, d/package-lock.json: 1 npm, … (+2)")


class TheToolItself(unittest.TestCase):
    def test_an_advisory_osv_places_on_the_commit_is_danger_and_the_rest_warn(self):
        records = [{"id": "CVE-2026-1", "aliases": ["GHSA-1111-1111-1111"], "summary": "Path traversal"}]
        advisories = [
            {"ghsa_id": "GHSA-1111-1111-1111", "severity": "high", "state": "published", "withdrawn_at": None},
            {"ghsa_id": "GHSA-2222-2222-2222", "severity": "medium", "state": "published", "withdrawn_at": None},
            {"ghsa_id": "GHSA-3333-3333-3333", "severity": "low", "state": "published", "withdrawn_at": "2026-01-01"},
        ]
        r = check({"SKILL.md": ""}, Net(commit=["CVE-2026-1"], records=records, advisories=advisories))
        self.assertEqual(en(r), [
            "✕ danger: this commit is affected by 1 published vulnerability (CVE-2026-1)",
            "⚠ warn (1): advisories this repo published (1)",
            "✓ malware lookup: nothing found",
        ])
        self.assertIn("\n  warn repo-advisory GHSA-2222-2222-2222 medium: could not tell whether it affects this commit",
                      r["note"])

    def test_the_repos_advisories_that_cannot_be_read_are_unchecked(self):
        r = check({"SKILL.md": ""}, Net(fail=("gh",)))
        self.assertEqual(en(r), ["? unchecked: advisory lookup for this repo's advisories (gh api: HTTP 404)",
                                 "✓ advisory lookup: nothing found in the rest", "✓ malware lookup: nothing found"])


class ThePackageOfAnMcpServer(unittest.TestCase):
    """check_package: an MCP server's published package at the version the command is pinned to, and the
    packages it depends on as its package manager would resolve them now."""

    def package(self, ecosystem, name, version, net, direct=(), why=None):
        return lookups.check_package("o/r", ecosystem, name, version, list(direct), net, why)

    def test_npm_resolves_the_tree_of_the_package_itself_and_an_advisory_for_it_is_danger(self):
        net = Net(resolve={"npm": lock(("srv", "1.2.3"), ("lodash", "4.17.20"))},
                  vulns={("npm", "srv", "1.2.3"): ["GHSA-srv1-srv1-srv1"]},
                  records=[{"id": "GHSA-srv1-srv1-srv1", "summary": "SSRF", "database_specific": {"severity": "LOW"}}])
        r = self.package("npm", "srv", "1.2.3", net)
        argv, files = net.ran[0]
        self.assertEqual((argv[:4], files), (["npm", "install", "--package-lock-only", "--ignore-scripts"], ["package.json"]))
        self.assertEqual(json.loads(net.given[0]["package.json"])["dependencies"], {"srv": "1.2.3"})
        self.assertEqual(net.queries, [{"package": {"name": "srv", "ecosystem": "npm"}, "version": "1.2.3"},
                                       {"package": {"name": "lodash", "ecosystem": "npm"}, "version": "4.17.20"}])
        self.assertEqual(en(r), [
            "✕ danger: srv@1.2.3 (npm) is affected by 1 published vulnerability (GHSA-srv1-srv1-srv1)",
            "dependencies: srv@1.2.3: 1 npm, versions resolved at check time",
            "✓ malware lookup: nothing found",
        ])
        self.assertIn("\n  danger advisory the package srv@1.2.3 (npm) GHSA-srv1-srv1-srv1 low: SSRF\n", r["note"])

    def test_pypi_resolves_with_uv_and_the_package_is_not_its_own_dependency(self):
        net = Net(resolve={"uv": "mcp-server-x==1.0\nrequests==2.19.0\n"})
        r = self.package("PyPI", "MCP_Server.X", "1.0", net)
        self.assertEqual(net.given[0], {"requirements.txt": "MCP_Server.X==1.0\n"})
        self.assertEqual(in_english(r["nothing_found"]), ["1 PyPI dependency"])
        self.assertEqual(r["note"], "lookups: the dialog showed the user no findings from the advisory and malware lookups "
                                    "for the package MCP_Server.X@1.0 (PyPI)\ndependencies: MCP_Server.X@1.0: 1 PyPI, "
                                    "versions resolved at check time")

    def test_without_npm_its_direct_dependencies_are_looked_up_by_name(self):
        net = Net(tools=(), vulns={("npm", "evil", None): ["MAL-2026-9"]})
        r = self.package("npm", "srv", "1.2.3", net, direct=["evil", "zod"])
        self.assertTrue(r["blocked"])
        self.assertEqual(en(r), [
            "✕ blocked: the malware lookup found a known-malicious package, so Install is not offered",
            "✕ danger: evil (npm) is listed as malicious (MAL-2026-9); matched by name, the version was not resolved",
            "? unchecked: advisory lookup for the dependencies of srv@1.2.3 (npm not found, so versions were not resolved)",
            "dependencies: srv@1.2.3: 2 npm, names only",
            "✓ advisory lookup: nothing found in the rest",
        ])

    def test_a_known_malicious_package_itself_blocks(self):
        net = Net(resolve={"npm": lock(("srv", "1.2.3"))}, vulns={("npm", "srv", "1.2.3"): ["MAL-2026-1"]})
        r = self.package("npm", "srv", "1.2.3", net)
        self.assertTrue(r["blocked"])
        self.assertIn("✕ danger: srv@1.2.3 (npm) is listed as malicious (MAL-2026-1)", en(r))
        self.assertIn("because the malware lookup lists the package srv@1.2.3 (npm) as known-malicious", r["note"])

    def test_of_the_repos_advisories_only_those_for_this_package_count(self):
        def advisory(ghsa, *packages):
            return {"ghsa_id": ghsa, "severity": "medium", "state": "published", "withdrawn_at": None,
                    "vulnerabilities": [{"package": {"ecosystem": e, "name": n}} for e, n in packages]}
        advisories = [advisory("GHSA-1111-1111-1111", ("npm", "other-server")), advisory("GHSA-2222-2222-2222", ("pip", "my_srv")),
                      advisory("GHSA-3333-3333-3333"), advisory("GHSA-4444-4444-4444", ("npm", "my-srv"))]
        r = self.package("PyPI", "My-Srv", "1.0", Net(resolve={"uv": "my-srv==1.0\n"}, advisories=advisories))
        self.assertIn("⚠ warn (1): advisories this repo published (2)", en(r))
        self.assertIn("\n  warn repo-advisory GHSA-3333-3333-3333 medium: could not tell whether it affects the package "
                      "My-Srv@1.0 (PyPI)", r["note"])

    def test_without_a_version_only_the_malware_lookup_of_the_package_runs(self):
        net = Net(vulns={("npm", "srv", None): ["GHSA-aaaa-aaaa-aaaa"]})
        r = self.package("npm", "srv", None, net, why="npm registry: HTTP 404")
        self.assertEqual(net.queries, [{"package": {"name": "srv", "ecosystem": "npm"}}])
        self.assertEqual(net.ran, [])
        self.assertEqual(en(r), [
            "? unchecked: advisory lookup for the package srv (npm), the dependencies of srv; malware lookup for the "
            "dependencies of srv (npm registry: HTTP 404)",
            "✓ advisory and malware lookups: nothing found in the rest",
        ])
        self.assertIsNone(r["nothing_found"])


class Ratings(unittest.TestCase):
    def test_the_label_wins_then_the_cvss_3_score(self):
        self.assertEqual(lookups.rating({"database_specific": {"severity": "CRITICAL"}}), "critical")
        # Base scores as NVD gives them: 7.2 (CVE-2021-23337), 9.8, 6.1 (scope changed), 0.
        for vector, want in [("CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H", "high"),
                             ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", "critical"),
                             ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", "moderate"),
                             ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", "low")]:
            self.assertEqual(lookups.rating({"severity": [{"type": "CVSS_V3", "score": vector}]}), want, vector)
        self.assertEqual(lookups.cvss3("CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H"), 7.2)
        self.assertEqual(lookups.cvss3("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N"), 6.1)
        self.assertIsNone(lookups.rating({"severity": [{"type": "CVSS_V4", "score": "CVSS:4.0/AV:N"}]}))

    def test_a_record_and_its_aliases_count_once_with_the_best_known_rating(self):
        records = [{"id": "PYSEC-2026-1872", "aliases": ["GHSA-9hjg-9r4m-mvj7"]},
                   {"id": "GHSA-9hjg-9r4m-mvj7", "aliases": ["PYSEC-2026-1872"], "database_specific": {"severity": "HIGH"}}]
        net = Net(vulns={("PyPI", "requests", "2.19.0"): ["PYSEC-2026-1872", "GHSA-9hjg-9r4m-mvj7"]}, records=records)
        r = check({"uv.lock": 'version = 1\n[[package]]\nname = "requests"\nversion = "2.19.0"\n'
                              'source = { registry = "https://pypi.org/simple" }\n'}, net)
        self.assertEqual(en(r)[0], "✕ danger: requests@2.19.0 (PyPI) has 1 published vulnerability, worst high (GHSA-9hjg-9r4m-mvj7)")


if __name__ == "__main__":
    unittest.main()
