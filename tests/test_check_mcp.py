"""Tests for check_mcp.py, with GitHub, the registries and the lookups faked: python3 -m unittest discover -s tests"""
import base64
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills/inhale/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("check_mcp", SCRIPTS / "check_mcp.py")
assert spec and spec.loader
check_mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_mcp)

import test_lookups  # noqa: E402
from test_lookups import lock  # noqa: E402
from words import say  # noqa: E402

SHA = "d" * 40
NPM, PYPI = "https://registry.npmjs.org", "https://pypi.org/pypi"


def tgz(files, top="package"):
    """A gzipped tarball holding these files (text, or a TarInfo for anything else) under top/."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, body in files.items():
            if isinstance(body, tarfile.TarInfo):
                t.addfile(body)
                continue
            data = body.encode()
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def wheel(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()


def sri(data):
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


class Net(test_lookups.Net):
    """GitHub and the registries as well: repo maps a path in o/r to its text; web maps a URL to what it
    answers (a dict is JSON); anything else is a 404."""

    def __init__(self, repo=None, web=None, **kw):
        super().__init__(**kw)
        self.repo, self.web, self.got = repo or {}, web or {}, []

    def api(self, path):
        if path == "repos/o/r/commits/HEAD":
            return {"sha": SHA}
        if path == f"repos/o/r/git/trees/{SHA}?recursive=1":
            return {"tree": [{"path": p, "type": "blob"} for p in self.repo], "truncated": False}
        raise check_mcp.Failed("gh api: HTTP 404")

    def raw(self, repo, path, ref):
        assert (repo, ref) == ("o/r", SHA), (repo, ref)
        return self.repo[path]

    def get(self, url, limit):
        self.got.append(url)
        if url not in self.web:
            raise check_mcp.Failed(f"{url.split('/')[2]}: HTTP 404")
        body = self.web[url]
        return body if isinstance(body, bytes) else json.dumps(body).encode()


def npm_web(name, version, archive, deps=None, tag=None):
    tarball = f"{NPM}/{name}/-/{name.rsplit('/', 1)[-1]}-{version}.tgz"
    meta = {"name": name, "version": version, "dist": {"tarball": tarball, "integrity": sri(archive)},
            "dependencies": deps or {}}
    escaped = name.replace("/", "%2F")
    return {f"{NPM}/{escaped}/{tag or version}": meta, tarball: archive}


def server_json(*packages):
    return json.dumps({"name": "io.github.o/r", "version": "1.2.3", "packages": list(packages)})


def check(args, net):
    return check_mcp.check("o/r", args, net)


SERVER_TGZ = tgz({"package.json": "{}", "dist/index.js": "const t = process.env.API_TOKEN\nfetch(u)\n"})


class AnNpmServer(unittest.TestCase):
    def test_the_package_server_json_names_is_scanned_looked_up_and_pinned(self):
        net = Net(repo={"server.json": server_json({"registryType": "npm", "identifier": "@o/srv", "version": "1.2.3"}),
                        "src/index.ts": "cat ~/.ssh/id_rsa\n"},
                  web=npm_web("@o/srv", "1.2.3", SERVER_TGZ, deps={"zod": "^3"}),
                  resolve={"npm": lock(("@o/srv", "1.2.3"), ("zod", "3.0.0"))})
        c = check(["srv", "--", "npx", "-y", "@o/srv"], net)
        self.assertEqual(c["mcp_args"], ["srv", "--", "npx", "-y", "@o/srv@1.2.3"])
        self.assertEqual(c["lines"], [
            "package: @o/srv@1.2.3 (npm), named by this repo's server.json; not verified to come from this repo",
            "pinned: only @o/srv, to 1.2.3; its dependencies are not pinned, so they may differ from those checked "
            "when the server starts",
            "⚠ warn (1): may send secrets out",
            "dependencies: @o/srv@1.2.3: 1 npm, versions resolved at check time",
            "✓ advisory and malware lookups: nothing found",
        ])
        # The facts each side words in the dialog's language, beside the English lines.
        self.assertEqual(c["lines"], [say(f, "en") for f in c["facts"]])
        self.assertEqual(say(c["facts"][2], "zh-TW"), "⚠ 警告 1 項：可能外傳密鑰")
        self.assertFalse(c["blocked"])
        self.assertEqual(c["package"], {"ecosystem": "npm", "name": "@o/srv", "version": "1.2.3", "declared_in": "server.json"})
        self.assertTrue(c["note"].startswith(
            "pattern scan: the pattern-scan findings in the npm package @o/srv@1.2.3 (srv-1.2.3.tgz), as paths inside it "
            "(the dialog showed the user the warn ones by name only, without files or lines, and left out the info ones):\n"
            "  warn send-secrets: may send secrets out (network + env-secret)\n"
            "  info env-secret dist/index.js:1\n  info network dist/index.js:2\nlookups: "), c["note"])
        self.assertTrue(c["note"].endswith(
            f"\npackage: the command runs @o/srv@1.2.3 (npm), which this repo's server.json names at commit {SHA}; "
            "nobody verified that the repo publishes it. kirby pinned the command to that version; its dependencies "
            "are not pinned."), c["note"])
        # The warn combination asks for a model review of the package's files, named by the archive's sha256.
        self.assertEqual(c["review"], {"needed": True, "package": {"ecosystem": "npm", "name": "@o/srv", "version": "1.2.3"},
                                       "sha": hashlib.sha256(SERVER_TGZ).hexdigest(), "files": ["dist/index.js", "package.json"]})


    def test_in_a_monorepo_the_package_the_command_runs_is_found_in_its_folder(self):
        everything = tgz({"package.json": "{}", "dist/index.js": "console.log(1)\n"})
        net = Net(repo={"package.json": json.dumps({"name": "@o/servers", "private": True, "workspaces": ["src/*"]}),
                        "src/everything/package.json": json.dumps({"name": "@o/server-everything"}),
                        "src/time/pyproject.toml": "[project]\nname = 'o-time'\n",
                        "src/deep/er/package.json": json.dumps({"name": "@o/too-deep"}),
                        "node_modules/x/package.json": json.dumps({"name": "x"})},
                  web=npm_web("@o/server-everything", "2.1.0", everything, tag="latest"),
                  resolve={"npm": lock(("@o/server-everything", "2.1.0"))})
        c = check(["e2e", "--", "npx", "-y", "@o/server-everything@latest"], net)
        self.assertEqual(c["mcp_args"], ["e2e", "--", "npx", "-y", "@o/server-everything@2.1.0"])
        self.assertEqual(c["lines"][0], "package: @o/server-everything@2.1.0 (npm), named by this repo's "
                                        "src/everything/package.json; not verified to come from this repo")
        self.assertEqual(c["lines"][2:], ["✓ check: nothing found (2 files, 0 npm dependencies, advisory and malware lookups)"])

    def test_a_version_the_command_names_is_the_one_checked(self):
        old = tgz({"index.js": ""})
        net = Net(repo={"package.json": json.dumps({"name": "srv"})}, web=npm_web("srv", "1.0.0", old),
                  resolve={"npm": lock(("srv", "1.0.0"))})
        c = check(["srv", "npx", "srv@1.0.0", "--port", "1"], net)
        self.assertEqual(net.got[0], f"{NPM}/srv/1.0.0")
        self.assertEqual(c["mcp_args"], ["srv", "npx", "srv@1.0.0", "--port", "1"])
        self.assertEqual(c["package"]["version"], "1.0.0")

    PACKUMENT = {"name": "srv", "dist-tags": {"latest": "2.0.0"},
                 "versions": {v: {} for v in ("1.1.0", "1.2.0", "1.3.0-beta.1", "1.10.0", "2.0.0")}}

    def test_a_range_is_resolved_to_the_highest_version_it_matches_which_is_checked_and_pinned(self):
        net = Net(repo={"package.json": json.dumps({"name": "srv"})},
                  web={f"{NPM}/srv": self.PACKUMENT, **npm_web("srv", "1.10.0", tgz({"i.js": ""}))},
                  resolve={"npm": lock(("srv", "1.10.0"))})
        c = check(["srv", "--", "npx", "-y", "srv@^1.2"], net)
        # 1.10.0, not 1.2.0 (a version is not a string), nor the pre-release, nor 2.0.0 outside the range.
        self.assertEqual(net.got[:2], [f"{NPM}/srv", f"{NPM}/srv/1.10.0"])
        self.assertEqual(c["mcp_args"], ["srv", "--", "npx", "-y", "srv@1.10.0"])
        self.assertEqual(c["lines"][:3], [
            "package: srv@1.10.0 (npm), named by this repo's package.json; not verified to come from this repo",
            "pinned: only srv, to 1.10.0, the highest version matching ^1.2; its dependencies are not pinned, so they "
            "may differ from those checked when the server starts",
            "✓ check: nothing found (1 file, 0 npm dependencies, advisory and malware lookups)",
        ])

    def test_the_facts_are_kirbys_wording_of_the_lines_with_names_versions_and_ranges_as_they_are(self):
        net = Net(repo={"package.json": json.dumps({"name": "srv"})},
                  web={f"{NPM}/srv": self.PACKUMENT, **npm_web("srv", "1.10.0", tgz({"i.js": ""}))},
                  resolve={"npm": lock(("srv", "1.10.0"))})
        c = check(["srv", "--", "npx", "-y", "srv@^1.2"], net)
        self.assertEqual([say(f, "en") for f in c["facts"]], c["lines"])
        self.assertEqual([say(f, "zh-TW") for f in c["facts"][:2]], [
            "套件：srv@1.10.0（npm），由這個 repo 的 package.json 指名；沒有驗證它來自這個 repo",
            "已鎖定：只有 srv，鎖定在符合 ^1.2 的最高版本 1.10.0；它的相依套件沒有鎖定，server 啟動時可能和檢查過的不同",
        ])
        net = Net(repo={"package.json": json.dumps({"name": "srv"})}, web={f"{NPM}/srv": self.PACKUMENT})
        c = check(["srv", "--", "npx", "-y", "srv@^9"], net)
        self.assertEqual([say(f, "en") for f in c["facts"]], c["lines"])
        self.assertEqual([say(f, "zh-CN") for f in c["facts"][:2]], [
            "包：srv（npm），由这个 repo 的 package.json 指定；没有验证它来自这个 repo",
            "未锁定：kirby 无法确定命令会安装 srv 的哪个版本（no version of srv matches ^9）；会按原样安装",
        ])

    def test_a_range_no_version_matches_or_kirby_cannot_read_is_not_pinned(self):
        for word, why in [("srv@^9", "no version of srv matches ^9"),
                          ("srv@>=1 <2 || ~~3", "the command asks for srv@>=1 <2 || ~~3, a range kirby does not resolve")]:
            net = Net(repo={"package.json": json.dumps({"name": "srv"})}, web={f"{NPM}/srv": self.PACKUMENT})
            c = check(["srv", "--", "npx", "-y", word], net)
            self.assertEqual(c["mcp_args"], ["srv", "--", "npx", "-y", word])
            self.assertEqual(c["lines"][:3], [
                "package: srv (npm), named by this repo's package.json; not verified to come from this repo",
                f"not pinned: kirby could not tell which version of srv the command installs ({why}); it installs as given",
                f"? unchecked: pattern scan ({why})",
            ])
            self.assertEqual(net.queries[-1:], [{"package": {"name": "srv", "ecosystem": "npm"}}])
        # kirby's own reason is worded in the dialog's language; the registry's answer above stays as it is.
        self.assertEqual(say(c["facts"][1], "zh-TW"),
                         "未鎖定：kirby 無法確定指令會安裝 srv 的哪個版本（指令要求 srv@>=1 <2 || ~~3，kirby 不解析這種範圍）；會照原樣安裝")

    def test_npm_ranges(self):
        versions = ["0.1.0", "0.1.5", "0.2.0", "1.0.0", "1.2.3", "1.2.9", "1.3.0", "1.10.0", "2.0.0-rc.1", "2.0.0", "2.1.0"]
        for spec, want in [("^1.2.3", "1.10.0"), ("~1.2.3", "1.2.9"), ("^0.1.2", "0.1.5"), ("1.x", "1.10.0"), ("1.2.*", "1.2.9"),
                           ("1", "1.10.0"), (">=1.2.3 <1.3", "1.2.9"), ("<=1.2", "1.2.9"), (">1.2", "2.1.0"), ("1.0.0 - 1.2", "1.2.9"),
                           ("^3 || 0.2.x", "0.2.0"), ("*", "2.1.0"), ("=1.0.0", "1.0.0"), ("^2.0.0-rc.0", "2.1.0"),
                           ("2.0.0-rc.0 - 2.0.0-rc.5", "2.0.0-rc.1"), ("<2.0.0", "1.10.0"), ("^4", None)]:
            self.assertEqual(check_mcp.highest("npm", versions, spec), want, spec)

    def test_pypi_ranges(self):
        versions = ["0.9", "1.0", "1.0.post1", "1.4.2", "1.5", "1.6rc1", "2.0", "2.0.1"]
        for spec, want in [(">=1.0,<2", "1.5"), ("~=1.4", "1.5"), ("~=1.4.0", "1.4.2"), ("==1.*", "1.5"), ("!=2.0.1", "2.0"),
                           ("<1.5", "1.4.2"), (">1.0", "2.0.1"), ("<=1.0", "1.0"), (">=1.6rc1,<2", "1.6rc1"), (">=3", None)]:
            self.assertEqual(check_mcp.highest("PyPI", versions, spec), want, spec)
        with self.assertRaises(check_mcp.Failed):
            check_mcp.highest("PyPI", versions, ">=1.0;<2")

    def test_dependencies_from_outside_the_registry_are_looked_up_by_name_without_running_npm(self):
        # npm fetches a git dependency to resolve it, and may run its prepare script; kirby does not let it.
        net = Net(repo={"package.json": json.dumps({"name": "srv"})},
                  web=npm_web("srv", "1.0.0", tgz({"i.js": ""}), tag="latest", deps={"zod": "^3", "evil": "github:o/evil"}),
                  resolve={"npm": lock(("srv", "1.0.0"), ("zod", "3.0.0"))})
        c = check(["srv", "--", "npx", "-y", "srv"], net)
        self.assertEqual(net.ran, [])
        self.assertIn("dependencies: srv@1.0.0: 2 npm, names only", c["lines"])
        self.assertIn("? unchecked: advisory lookup for the dependencies of srv@1.0.0 (some dependencies come from outside "
                      "the npm registry, so versions were not resolved)", c["lines"])
        self.assertEqual(c["mcp_args"][-1], "srv@1.0.0")

    def test_a_registry_that_does_not_answer_leaves_it_unpinned(self):
        net = Net(repo={"server.json": server_json({"registryType": "npm", "identifier": "srv", "version": "9.9.9"})})
        c = check(["srv", "--", "npx", "-y", "srv"], net)
        self.assertEqual(net.got, [f"{NPM}/srv/9.9.9"])
        self.assertEqual(c["mcp_args"], ["srv", "--", "npx", "-y", "srv"])
        self.assertIn("? unchecked: pattern scan (registry.npmjs.org: HTTP 404)", c["lines"])
        self.assertTrue(c["note"].endswith("kirby could not pin it (registry.npmjs.org: HTTP 404), so the command installs as given."))


class APythonServer(unittest.TestCase):
    WHEEL = wheel({"mcp_server_time/__init__.py": "import os\nos.system(cmd)\n", "mcp_server_time-1.0.dist-info/METADATA": ""})

    def web(self, files=None, path="mcp-server-time/json"):
        whl = {"packagetype": "bdist_wheel", "filename": "mcp_server_time-1.0-py3-none-any.whl",
               "url": "https://files.example/t.whl", "digests": {"sha256": hashlib.sha256(self.WHEEL).hexdigest()}}
        sdist = {"packagetype": "sdist", "filename": "mcp_server_time-1.0.tar.gz", "url": "https://files.example/t.tar.gz",
                 "digests": {"sha256": "0" * 64}}
        meta = {"info": {"version": "1.0", "requires_dist": ["mcp>=1", "pytest; extra == 'dev'"]},
                "urls": files if files is not None else [sdist, whl]}
        return {f"{PYPI}/{path}": meta, "https://files.example/t.whl": self.WHEEL}

    def test_uvx_is_pinned_with_equals_and_the_wheel_for_every_platform_is_scanned(self):
        net = Net(repo={"pyproject.toml": "[project]\nname = 'mcp-server-time'\n"}, web=self.web(),
                  resolve={"uv": "mcp-server-time==1.0\nmcp==1.2.0\n"})
        c = check(["time", "--", "uvx", "mcp-server-time", "--local-timezone=UTC"], net)
        self.assertEqual(c["mcp_args"], ["time", "--", "uvx", "mcp-server-time==1.0", "--local-timezone=UTC"])
        # The info finding is left out of the dialog; the model gets it.
        self.assertEqual(c["lines"][2:5], ["✓ pattern scan: no danger or warn findings",
                                           "dependencies: mcp-server-time@1.0: 1 PyPI, versions resolved at check time",
                                           "✓ advisory and malware lookups: nothing found"])
        self.assertIn("\n  info exec mcp_server_time/__init__.py:2", c["note"])

    def test_a_range_is_resolved_among_the_releases_that_have_files_and_pinned_with_equals(self):
        whl = {"filename": "w.whl", "url": "https://files.example/w.whl"}
        latest = self.web()[f"{PYPI}/mcp-server-time/json"]
        web = {**self.web(path="mcp-server-time/1.0/json"),
               f"{PYPI}/mcp-server-time/json": {**latest, "releases": {"0.9": [whl], "1.0": [whl], "1.1": [{**whl, "yanked": True}],
                                                                      "1.2": [], "2.0": [whl]}}}
        net = Net(repo={"pyproject.toml": "[project]\nname = 'mcp-server-time'\n"}, web=web, resolve={"uv": "mcp-server-time==1.0\n"})
        c = check(["time", "--", "uvx", "mcp-server-time>=0.9,<2"], net)
        self.assertEqual(c["mcp_args"], ["time", "--", "uvx", "mcp-server-time==1.0"])
        self.assertEqual(c["lines"][1], "pinned: only mcp-server-time, to 1.0, the highest version matching >=0.9,<2; its "
                                        "dependencies are not pinned, so they may differ from those checked when the server starts")

    def test_the_from_option_and_extras_keep_their_shape(self):
        net = Net(repo={"pyproject.toml": "[project]\nname = 'MCP_Server_Time'\n"}, web=self.web(), tools=())
        c = check(["time", "--", "uvx", "--from", "mcp-server-time[cli]", "mcp-server-time"], net)
        self.assertEqual(c["mcp_args"][4:], ["mcp-server-time[cli]==1.0", "mcp-server-time"])
        # Without uv, the names it depends on (not those of an extra) are looked up.
        self.assertIn("dependencies: MCP_Server_Time@1.0: 1 PyPI, names only", c["lines"])

    def test_an_sdist_is_scanned_when_there_is_no_wheel_for_every_platform(self):
        sdist = tgz({"PKG-INFO": "", "src/t.py": "x = 1\n"}, top="mcp_server_time-1.0")
        files = [{"packagetype": "bdist_wheel", "filename": "t-1.0-cp312-cp312-manylinux_x86_64.whl", "url": "https://files.example/p.whl",
                  "digests": {"sha256": "0" * 64}},
                 {"packagetype": "sdist", "filename": "mcp_server_time-1.0.tar.gz", "url": "https://files.example/s.tgz",
                  "digests": {"sha256": hashlib.sha256(sdist).hexdigest()}}]
        net = Net(repo={"pyproject.toml": "[project]\nname = 'mcp-server-time'\n"},
                  web={**self.web(files), "https://files.example/s.tgz": sdist}, resolve={"uv": "mcp-server-time==1.0\n"})
        c = check(["time", "--", "uvx", "mcp-server-time"], net)
        self.assertEqual(c["lines"][2], "✓ check: nothing found (2 files, 0 PyPI dependencies, advisory and malware lookups)")


class Unchecked(unittest.TestCase):
    def test_nothing_to_review_when_nothing_was_checked(self):
        c = check(["e", "--url", "https://x.example/mcp"], Net())
        self.assertEqual(c["review"], {"needed": False, "files": []})

    def assert_unchecked(self, args, why, repo=None, pinned=True):
        """why is kirby's reason, in English and in 繁體中文."""
        en, zh = why
        c = check(args, Net(repo=repo if repo is not None else {"package.json": json.dumps({"name": "srv"})}))
        self.assertEqual(c["lines"], [f"? unchecked: pattern scan, advisory lookup and malware lookup ({en})"
                                      + ("; not pinned" if pinned else "")])
        self.assertEqual(say(c["facts"][0], "zh-TW"), f"？未檢查：pattern 掃描、漏洞查詢和惡意套件查詢（{zh}）"
                         + ("；未鎖定版本" if pinned else ""))
        # The model reads the reason in English.
        self.assertTrue(c["note"].endswith(f": {en}"), c["note"])
        self.assertEqual(c["mcp_args"], args)
        self.assertFalse(c["blocked"])
        self.assertIsNone(c["package"])

    def test_a_remote_server_is_unchecked(self):
        why = ("a remote server at a URL; its code does not install here", "URL 上的遠端 server；它的程式碼不會安裝在這裡")
        self.assert_unchecked(["srv", "--transport", "http", "https://mcp.example/mcp"], why, pinned=False)
        self.assert_unchecked(["srv", "--url", "https://mcp.example/mcp"], why, pinned=False)

    def test_a_container_image_is_unchecked(self):
        self.assert_unchecked(["srv", "--", "docker", "run", "-i", "--rm", "ghcr.io/o/srv"],
                              ("the command runs a container image, which kirby does not check",
                               "指令執行的是 container image，kirby 不檢查它"))

    def test_a_repo_that_names_no_package_is_unchecked(self):
        self.assert_unchecked(["srv", "--", "npx", "-y", "srv"],
                              ("this repo names no npm or PyPI package in a server.json, package.json or pyproject.toml",
                               "這個 repo 的 server.json、package.json 或 pyproject.toml 沒有寫任何 npm 或 PyPI 套件"), repo={})

    def test_a_command_that_runs_another_package_is_unchecked(self):
        why = ("the command runs none of the packages this repo names: srv", "指令執行的不是這個 repo 寫的任何套件：srv")
        self.assert_unchecked(["srv", "--", "npx", "-y", "someone-elses-srv"], why)
        self.assert_unchecked(["srv", "--", "node", "dist/index.js"], why)

    def test_only_the_package_the_runner_runs_counts_not_a_later_word(self):
        # npx runs other-pkg; srv is only an argument to it, so checking srv would check the wrong code.
        why = ("the command runs none of the packages this repo names: srv", "指令執行的不是這個 repo 寫的任何套件：srv")
        self.assert_unchecked(["srv", "--", "npx", "-y", "other-pkg", "srv"], why)
        self.assert_unchecked(["srv", "--", "uvx", "other-pkg", "srv"], why,
                              repo={"pyproject.toml": "[project]\nname = 'srv'\n"})
        # A runner's subcommand that does not fetch a package runs none either.
        self.assert_unchecked(["srv", "--", "npm", "run", "srv"], why)

    def test_the_runners_package_option_and_subcommand_name_the_package(self):
        for args, index in [(["srv", "--", "npx", "--package", "srv", "srv-cli"], 4),
                            (["srv", "--", "npx", "-y", "-p=srv", "srv-cli"], 4),
                            (["srv", "--", "pnpm", "dlx", "srv"], 4),
                            (["srv", "--", "npm", "exec", "--yes", "--", "srv"], 6)]:
            net = Net(repo={"package.json": json.dumps({"name": "srv"})}, web=npm_web("srv", "1.0.0", tgz({"i.js": ""}), tag="latest"),
                      resolve={"npm": lock(("srv", "1.0.0"))})
            c = check(args, net)
            self.assertEqual(c["package"]["name"], "srv", args)
            want = list(args)
            want[index] = want[index].replace("srv", "srv@1.0.0", 1)
            self.assertEqual(c["mcp_args"], want, args)


class Findings(unittest.TestCase):
    REPO = {"package.json": json.dumps({"name": "srv"})}

    def test_a_known_malicious_package_blocks(self):
        net = Net(repo=self.REPO, web=npm_web("srv", "1.0.0", tgz({"i.js": ""}), tag="latest"),
                  resolve={"npm": lock(("srv", "1.0.0"))}, vulns={("npm", "srv", "1.0.0"): ["MAL-2026-7"]})
        c = check(["srv", "--", "npx", "-y", "srv"], net)
        self.assertTrue(c["blocked"])
        self.assertIn("✕ danger: srv@1.0.0 (npm) is listed as malicious (MAL-2026-7)", c["lines"])
        # Install is not offered, so there is nothing to review for.
        self.assertFalse(c["review"]["needed"])

    def test_a_blocked_package_that_was_not_scanned_needs_no_review_either(self):
        web = npm_web("srv", "1.0.0", tgz({"i.js": ""}), tag="latest")
        web[f"{NPM}/srv/-/srv-1.0.0.tgz"] = tgz({"i.js": "eval(x)\n"})
        net = Net(repo=self.REPO, web=web, resolve={"npm": lock(("srv", "1.0.0"))}, vulns={("npm", "srv", "1.0.0"): ["MAL-2026-7"]})
        c = check(["srv", "--", "npx", "-y", "srv"], net)
        self.assertTrue(c["blocked"])
        self.assertEqual(c["review"], {"needed": False, "files": []})

    def test_a_download_that_does_not_match_the_registrys_hash_is_not_scanned(self):
        web = npm_web("srv", "1.0.0", tgz({"i.js": ""}), tag="latest")
        web[f"{NPM}/srv/-/srv-1.0.0.tgz"] = tgz({"i.js": "eval(x)\n"})
        c = check(["srv", "--", "npx", "-y", "srv"], Net(repo=self.REPO, web=web, resolve={"npm": lock(("srv", "1.0.0"))}))
        self.assertEqual(c["lines"][2], "? unchecked: pattern scan (the download does not match the registry's hash)")
        self.assertEqual(c["mcp_args"][-1], "srv@1.0.0")
        # Nothing was unpacked, so a review would have nothing to read.
        self.assertEqual(c["review"], {"needed": False, "files": []})

    def test_a_lookup_finding_asks_for_a_review_even_when_nothing_was_unpacked(self):
        web = npm_web("srv", "1.0.0", tgz({"i.js": ""}), tag="latest")
        web[f"{NPM}/srv/-/srv-1.0.0.tgz"] = b"not the archive"
        net = Net(repo=self.REPO, web=web, resolve={"npm": lock(("srv", "1.0.0"), ("lodash", "4.17.20"))},
                  vulns={("npm", "lodash", "4.17.20"): ["GHSA-35jh-r3h4-6jhm"]})
        self.assertEqual(check(["srv", "--", "npx", "-y", "srv"], net)["review"], {"needed": True, "files": []})


class ReadForTheReview(unittest.TestCase):
    """The file tool's way into an MCP server's package: one file of the same archive the check unpacked, which
    the review names by its sha256."""

    ARCHIVE = tgz({"package.json": "{}", "dist/index.js": "fetch(u)\n"})
    PACKAGE = {"ecosystem": "npm", "name": "srv", "version": "1.0.0"}

    def read(self, path, sha=None, archive=None):
        web = npm_web("srv", "1.0.0", archive or self.ARCHIVE)
        return check_mcp.read({**self.PACKAGE, "sha": sha or hashlib.sha256(self.ARCHIVE).hexdigest(), "path": path},
                              Net(web=web))

    def test_a_file_of_the_checked_archive_is_read(self):
        self.assertEqual(self.read("dist/index.js"), "fetch(u)\n")

    def test_another_archive_a_missing_file_or_a_path_outside_is_refused(self):
        other = tgz({"package.json": "{}", "dist/index.js": "eval(x)\n"})
        for path, archive, why in [
            ("dist/index.js", other, "the registry now gives another archive than the one checked"),
            ("dist/nope.js", None, "srv@1.0.0 has no file dist/nope.js"),
            ("../package.json", None, "not a path inside the package: '../package.json'"),
        ]:
            with self.assertRaises(check_mcp.Failed) as e:
                self.read(path, archive=archive)
            self.assertEqual(str(e.exception), why)


class Unpacking(unittest.TestCase):
    """unpack: what an untrusted archive can hold never lands outside the folder."""

    def unpack(self, data, filename):
        tmp = tempfile.mkdtemp()
        dest = Path(tmp) / "out"
        dest.mkdir()
        root = check_mcp.unpack(data, filename, dest)
        return Path(tmp), root, sorted(str(p.relative_to(tmp)) for p in Path(tmp).rglob("*") if not p.is_dir())

    def member(self, name, kind, target=""):
        info = tarfile.TarInfo(name)
        info.type, info.linkname = kind, target
        return info

    def test_traversal_absolute_paths_and_links_in_a_tarball_are_left_out(self):
        data = tgz({"package/ok.js": "1", "../escape.js": "x", "/abs.js": "x", "package/../../up.js": "x",
                    "link": self.member("package/link", tarfile.SYMTYPE, "/etc/passwd"),
                    "hard": self.member("package/hard", tarfile.LNKTYPE, "package/ok.js"),
                    "dev": self.member("package/dev", tarfile.CHRTYPE)}, top=None)
        tmp, root, files = self.unpack(data, "srv-1.0.0.tgz")
        self.assertEqual(files, ["out/package/ok.js"])
        self.assertEqual(root, tmp / "out" / "package")

    def test_traversal_and_links_in_a_wheel_are_left_out(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("pkg/ok.py", "1")
            z.writestr("../escape.py", "x")
            z.writestr("/abs.py", "x")
            link = zipfile.ZipInfo("pkg/link")
            link.external_attr = (0o120777 << 16)
            z.writestr(link, "/etc/passwd")
        tmp, root, files = self.unpack(buf.getvalue(), "p-1.0-py3-none-any.whl")
        self.assertEqual(files, ["out/pkg/ok.py"])

    def test_what_a_tarball_skips_counts_against_the_limit_too(self):
        # A stream skips a member by reading through it, so a member left out still costs its size in decompression.
        for info in [tarfile.TarInfo("package/odd"), tarfile.TarInfo("../escape.js")]:
            if info.name == "package/odd":
                info.type = b"Z"  # a type tarfile does not know, whose data it still reads past
            info.size = 11
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as t:
                t.addfile(info, io.BytesIO(b"x" * 11))
            limit = check_mcp.MAX_UNPACKED
            check_mcp.MAX_UNPACKED = 10
            try:
                with self.assertRaises(check_mcp.Failed, msg=info.name):
                    self.unpack(buf.getvalue(), "srv-1.0.0.tgz")
            finally:
                check_mcp.MAX_UNPACKED = limit

    def test_an_encrypted_or_oddly_compressed_wheel_is_a_failure_not_a_crash(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("pkg/a.py", "1")
        plain = buf.getvalue()
        # The encryption flag, in the local header (offset 6) and the central directory (offset 8).
        encrypted = bytearray(plain)
        for sig, at in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            encrypted[plain.index(sig) + at] |= 1
        # A compression method zipfile does not have, in the same two places (offsets 8 and 10).
        odd = bytearray(plain)
        for sig, at in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
            odd[plain.index(sig) + at] = 99
        for data in (bytes(encrypted), bytes(odd)):
            with self.assertRaises(check_mcp.Failed) as e:
                self.unpack(data, "p-1.0-py3-none-any.whl")
            self.assertTrue(str(e.exception).startswith("could not unpack p-1.0-py3-none-any.whl ("), str(e.exception))

    def test_an_archive_too_large_unpacked_is_refused(self):
        limit = check_mcp.MAX_UNPACKED
        check_mcp.MAX_UNPACKED = 10
        try:
            with self.assertRaises(check_mcp.Failed):
                self.unpack(tgz({"big.js": "x" * 11}), "srv-1.0.0.tgz")
            # Right at the limit, the file is unpacked whole.
            _, root, _ = self.unpack(tgz({"big.js": "x" * 10}), "srv-1.0.0.tgz")
            self.assertEqual((root / "big.js").read_text(), "x" * 10)
        finally:
            check_mcp.MAX_UNPACKED = limit


if __name__ == "__main__":
    unittest.main()
