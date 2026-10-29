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
            "scan: 2 files, those in srv-1.2.3.tgz; a pattern match, not a safety review",
            "warn: send-secrets: may send secrets out (network + env-secret)",
            "info: env-secret ×1 (dist/index.js:1)",
            "info: network ×1 (dist/index.js:2)",
            "dependencies: @o/srv@1.2.3: 1 npm, versions resolved at check time",
            "advisory lookup: nothing found",
            "malware lookup: nothing found",
        ])
        self.assertFalse(c["blocked"])
        self.assertEqual(c["package"], {"ecosystem": "npm", "name": "@o/srv", "version": "1.2.3", "declared_in": "server.json"})
        self.assertTrue(c["note"].startswith(
            "scan: the dialog showed the user these pattern hits in the npm package @o/srv@1.2.3 (srv-1.2.3.tgz), "
            "as paths inside it:\n  warn send-secrets: may send secrets out (network + env-secret)\n"
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
        self.assertEqual(c["lines"][2:], ["check: nothing found (2 files, 0 npm dependencies, advisory and malware lookups)"])

    def test_a_version_the_command_names_is_the_one_checked(self):
        old = tgz({"index.js": ""})
        net = Net(repo={"package.json": json.dumps({"name": "srv"})}, web=npm_web("srv", "1.0.0", old),
                  resolve={"npm": lock(("srv", "1.0.0"))})
        c = check(["srv", "npx", "srv@1.0.0", "--port", "1"], net)
        self.assertEqual(net.got[0], f"{NPM}/srv/1.0.0")
        self.assertEqual(c["mcp_args"], ["srv", "npx", "srv@1.0.0", "--port", "1"])
        self.assertEqual(c["package"]["version"], "1.0.0")

    def test_a_range_is_not_resolved_so_nothing_is_pinned_or_scanned(self):
        net = Net(repo={"package.json": json.dumps({"name": "srv"})})
        c = check(["srv", "--", "npx", "-y", "srv@^1.2"], net)
        self.assertEqual(net.got, [])
        self.assertEqual(c["mcp_args"], ["srv", "--", "npx", "-y", "srv@^1.2"])
        why = "the command asks for srv@^1.2, a range kirby does not resolve"
        self.assertEqual(c["lines"][:3], [
            "package: srv (npm), named by this repo's package.json; not verified to come from this repo",
            f"not pinned: kirby could not tell which version of srv the command installs ({why}); it installs as given",
            f"unchecked: pattern scan ({why})",
        ])
        self.assertEqual(net.queries, [{"package": {"name": "srv", "ecosystem": "npm"}}])

    def test_a_registry_that_does_not_answer_leaves_it_unpinned(self):
        net = Net(repo={"server.json": server_json({"registryType": "npm", "identifier": "srv", "version": "9.9.9"})})
        c = check(["srv", "--", "npx", "-y", "srv"], net)
        self.assertEqual(net.got, [f"{NPM}/srv/9.9.9"])
        self.assertEqual(c["mcp_args"], ["srv", "--", "npx", "-y", "srv"])
        self.assertIn("unchecked: pattern scan (registry.npmjs.org: HTTP 404)", c["lines"])
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
        self.assertEqual(c["lines"][2:5], ["scan: 2 files, those in mcp_server_time-1.0-py3-none-any.whl; a pattern match, "
                                           "not a safety review", "info: exec ×1 (mcp_server_time/__init__.py:2)",
                                           "dependencies: mcp-server-time@1.0: 1 PyPI, versions resolved at check time"])

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
        self.assertEqual(c["lines"][2], "check: nothing found (2 files, 0 PyPI dependencies, advisory and malware lookups)")


class Unchecked(unittest.TestCase):
    def test_nothing_to_review_when_nothing_was_checked(self):
        c = check(["e", "--url", "https://x.example/mcp"], Net())
        self.assertEqual(c["review"], {"needed": False, "files": []})

    def assert_unchecked(self, args, why, repo=None, pinned=True):
        c = check(args, Net(repo=repo if repo is not None else {"package.json": json.dumps({"name": "srv"})}))
        self.assertEqual(c["lines"], [f"unchecked: pattern scan, advisory lookup and malware lookup ({why})"
                                      + ("; not pinned" if pinned else "")])
        self.assertEqual(c["mcp_args"], args)
        self.assertFalse(c["blocked"])
        self.assertIsNone(c["package"])

    def test_a_remote_server_is_unchecked(self):
        why = "a remote server at a URL; its code does not install here"
        self.assert_unchecked(["srv", "--transport", "http", "https://mcp.example/mcp"], why, pinned=False)
        self.assert_unchecked(["srv", "--url", "https://mcp.example/mcp"], why, pinned=False)

    def test_a_container_image_is_unchecked(self):
        self.assert_unchecked(["srv", "--", "docker", "run", "-i", "--rm", "ghcr.io/o/srv"],
                              "the command runs a container image, which kirby does not check")

    def test_a_repo_that_names_no_package_is_unchecked(self):
        self.assert_unchecked(["srv", "--", "npx", "-y", "srv"],
                              "this repo names no npm or PyPI package in a server.json, package.json or pyproject.toml", repo={})

    def test_a_command_that_runs_another_package_is_unchecked(self):
        self.assert_unchecked(["srv", "--", "npx", "-y", "someone-elses-srv"],
                              "the command runs none of the packages this repo names: srv")
        self.assert_unchecked(["srv", "--", "node", "dist/index.js"], "the command runs none of the packages this repo names: srv")


class Findings(unittest.TestCase):
    REPO = {"package.json": json.dumps({"name": "srv"})}

    def test_a_known_malicious_package_blocks(self):
        net = Net(repo=self.REPO, web=npm_web("srv", "1.0.0", tgz({"i.js": ""}), tag="latest"),
                  resolve={"npm": lock(("srv", "1.0.0"))}, vulns={("npm", "srv", "1.0.0"): ["MAL-2026-7"]})
        c = check(["srv", "--", "npx", "-y", "srv"], net)
        self.assertTrue(c["blocked"])
        self.assertIn("danger: the package srv@1.0.0 (npm) is listed as malicious (MAL-2026-7)", c["lines"])
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
        self.assertEqual(c["lines"][2], "unchecked: pattern scan (the download does not match the registry's hash)")
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

    def test_an_archive_too_large_unpacked_is_refused(self):
        limit = check_mcp.MAX_UNPACKED
        check_mcp.MAX_UNPACKED = 10
        try:
            with self.assertRaises(check_mcp.Failed):
                self.unpack(tgz({"big.js": "x" * 11}), "srv-1.0.0.tgz")
        finally:
            check_mcp.MAX_UNPACKED = limit


if __name__ == "__main__":
    unittest.main()
