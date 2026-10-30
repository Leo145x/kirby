#!/usr/bin/env python3
"""The pre-install check of an MCP server: the package its install command runs, at the version it pins.

    check_mcp.py owner/repo '<mcp_args as a JSON list>'
    check_mcp.py --read '{"ecosystem": …, "name": …, "version": …, "sha": …, "path": …}'

mcp_args is what follows `claude mcp add --scope <scope>` or `codex mcp add`, for example
["github", "--", "npx", "-y", "@modelcontextprotocol/server-github"]. The repo is read only to learn which
packages it names: those in a server.json, then the name in a package.json, then in a pyproject.toml, at
the root or up to two folders down. Nothing ties such a package to the repo (the MCP registry checks a
package against a server name, not a repo), so the dialog says the repo names it and nobody verified that.

When the command runs one of those packages (through npx, uvx and the like: the package the runner itself runs,
not a later word), the check takes the version the command asks for (for a range, the highest version the
registry has that it matches), else the one server.json gives, else the registry's latest; downloads that version's npm
tarball or PyPI wheel (or sdist), checks it against the registry's hash and unpacks it into a temporary
folder, never installing, importing or running any of it; runs the pattern scan (install_skill.py's) on its
files and the advisory and malware lookups (lookups.check_package) on it and its dependencies; and rewrites
the command to that version (`npx -y pkg@1.2.3`, `uvx pkg==1.2.3`). Only that package is pinned: its
dependencies are resolved at check time and may differ when the server starts (#13).

A container image, a remote server (a URL), or a command that runs none of the packages the repo names is
reported as unchecked, and the command stays as it is. Prints JSON: the dialog's facts (`facts`, each a line
or a key and its values for words.py, which each side words in the dialog's language), the same in English
(`lines`) and for the model (`note`), `blocked`, the command to install (`mcp_args`), the `package` checked, and `review`:
whether the model review runs and which files of the package it reads, with the archive's sha256 (docs/adr/0002).

--read prints one file of such a package for the review (the file tool): the same archive, downloaded again,
checked against the registry's hash and the review's sha256, and unpacked into a temporary folder.
"""
import argparse
import base64
import hashlib
import io
import json
import lzma
import re
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlparse

# -I leaves this folder off the import path; these are kirby's own, next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lookups  # noqa: E402
from install_skill import (NO_REVIEW, UNCHECKED, VALID_REPO, VALID_SHA, check_lines, inside, listing, review, scan,  # noqa: E402
                           scan_note)
from lookups import NPM_NAME, Failed, first_line, package_key, py_name, shown  # noqa: E402
from words import fact, say  # noqa: E402

try:
    import tomllib
except ImportError:  # before Python 3.11: pyproject.toml cannot be read
    tomllib = None

NPM_REGISTRY, PYPI = "https://registry.npmjs.org", "https://pypi.org/pypi"
# The files that name a package, in the order the check prefers them, and how deep in the repo it looks.
PACKAGE_FILES = ("server.json", "package.json", "pyproject.toml")
DEPTH = 3
MAX_PACKAGE_FILES = 30
REGISTRY_TYPES = {"npm": "npm", "pypi": "PyPI"}
# The commands that fetch a package from each registry and run it, and the subcommand that does it, for those
# that need one.
RUNNERS = {"npx": "npm", "bunx": "npm", "pnpx": "npm", "pnpm": "npm", "yarn": "npm", "npm": "npm", "bun": "npm",
           "uvx": "PyPI", "uv": "PyPI", "pipx": "PyPI"}
SUBCOMMANDS = {"pnpm": [["dlx"]], "yarn": [["dlx"]], "npm": [["exec"], ["x"]], "bun": [["x"]], "uv": [["tool", "run"]],
               "pipx": [["run"]]}
# The runners' options that name the package to run, and those that take a value of another kind.
PACKAGE_OPTIONS = {"npm": ("--package", "-p"), "PyPI": ("--from", "--spec")}
VALUE_OPTIONS = {"npm": ("--registry", "--cache", "--userconfig", "--workspace", "-w", "--call", "-c"),
                 "PyPI": ("--python", "-p", "--with", "--index", "--index-url", "--default-index", "--extra-index-url")}
CONTAINERS = ("docker", "podman")
NPM_EXACT = re.compile(r"^v?\d+\.\d+\.\d+([-+][0-9A-Za-z.+-]*)?$")
NPM_TAG = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
PY_WORD = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?(?:(==|@)(.+)|(.*))$")
PY_EXACT = re.compile(r"^[0-9][0-9A-Za-z.!+-]*$")
MAX_ARCHIVE = 50_000_000
MAX_UNPACKED = 200_000_000
MAX_FILES = 10_000


class Net(lookups.Net):
    """GitHub and the registries as well, inside the lookups' time budget; the tests put a fake in its place."""

    def api(self, path):
        ok, out = self.run(["gh", "api", path])
        if not ok:
            raise Failed(f"gh api: {first_line(out)}")
        try:
            return json.loads(out)
        except ValueError:
            raise Failed("gh api: not JSON") from None

    def raw(self, repo, path, ref):
        ok, out = self.run(["gh", "api", f"repos/{repo}/contents/{quote(path)}?ref={ref}", "-H", "Accept: application/vnd.github.raw"])
        if not ok:
            raise Failed(f"gh api: {first_line(out)}")
        return out

    def get(self, url, limit):
        host = urlparse(url).hostname or "?"
        if urlparse(url).scheme != "https":
            raise Failed(f"{shown(host, 60)}: not an https URL")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "kirby"}), timeout=self.timeout()) as r:
                data = r.read(limit + 1)
        except (OSError, ValueError) as e:
            raise Failed(f"{shown(host, 60)}: {first_line(str(e)) if str(e) else type(e).__name__}") from None
        if len(data) > limit:
            raise Failed(f"{shown(host, 60)}: larger than {limit // 1_000_000} MB, more than kirby downloads")
        return data


# ---- which package ----------------------------------------------------------------------------------

def declarations(repo, net):
    """The commit read and the packages the repo names, best first: [{ecosystem, name, version (server.json's,
    or None), file}]."""
    sha = (net.api(f"repos/{repo}/commits/HEAD") or {}).get("sha")
    if not isinstance(sha, str) or not VALID_SHA.match(sha):
        raise Failed("gh api: no commit")
    tree = net.api(f"repos/{repo}/git/trees/{sha}?recursive=1") or {}
    paths = [t["path"] for t in tree.get("tree") or [] if isinstance(t, dict) and t.get("type") == "blob"
             and isinstance(t.get("path"), str)]
    wanted = sorted((p for p in paths if p.rsplit("/", 1)[-1] in PACKAGE_FILES and p.count("/") < DEPTH
                     and not any(s.startswith(".") or s == "node_modules" for s in p.split("/")[:-1])),
                    key=lambda p: (PACKAGE_FILES.index(p.rsplit("/", 1)[-1]), p.count("/"), p))[:MAX_PACKAGE_FILES]
    with ThreadPoolExecutor(max_workers=8) as pool:
        texts = list(pool.map(lambda p: net.raw(repo, p, sha), wanted))
    found, seen = [], set()
    for path, text in zip(wanted, texts):
        for eco, name, version in named(path.rsplit("/", 1)[-1], text):
            key = (eco, package_key(eco, name))
            if key not in seen:
                seen.add(key)
                found.append({"ecosystem": eco, "name": name, "version": version, "file": path})
    return sha, found


def named(kind, text):
    """The (ecosystem, name, version or None) packages one manifest names."""
    try:
        if kind == "pyproject.toml":
            name = ((tomllib.loads(text) if tomllib else {}).get("project") or {}).get("name")
            return [("PyPI", name, None)] if isinstance(name, str) and PY_WORD.match(name) else []
        data = json.loads(text)
    except (ValueError, AttributeError, TypeError):  # TOMLDecodeError is a ValueError
        return []
    if not isinstance(data, dict):
        return []
    if kind == "package.json":
        # A private package cannot be published, so it is not what a command fetches.
        name = data.get("name")
        return [("npm", name, None)] if isinstance(name, str) and NPM_NAME.match(name) and data.get("private") is not True else []
    out = []
    for p in data.get("packages") if isinstance(data.get("packages"), list) else []:
        if isinstance(p, dict) and p.get("registryType") in REGISTRY_TYPES and isinstance(p.get("identifier"), str):
            version = p.get("version") if isinstance(p.get("version"), str) and p["version"] else None
            out.append((REGISTRY_TYPES[p["registryType"]], p["identifier"], version))
    return out


def command_of(args):
    """Where the command the server starts begins in args, and its words: those after the first --, else the
    ones after the name (`claude mcp add <name> <command> [args…]`)."""
    start = args.index("--") + 1 if "--" in args else 1
    return start, args[start:]


def remote(args):
    """Whether args add a remote server, reached at a URL, rather than a command."""
    if any(a == "--url" or a.startswith("--url=") for a in args):
        return True
    for i, a in enumerate(args):
        kind = a.split("=", 1)[1] if a.startswith("--transport=") else args[i + 1] if a in ("--transport", "-t") and i + 1 < len(args) else None
        if kind in ("http", "sse"):
            return True
    return "--" not in args and any(re.match(r"^https?://", a) for a in args[1:])


def runner(word):
    return re.sub(r"\.(cmd|exe)$", "", word.replace("\\", "/").rsplit("/", 1)[-1].lower())


def split_word(eco, word):
    """A command word as (name, how, spec): how is "exact", "latest", "tag" or "range" (spec is then the range, as
    the registry's package manager reads it); None if the word is not a package of that ecosystem."""
    if eco == "npm":
        at = word.find("@", 1)
        name, spec = (word[:at], word[at + 1:]) if at > 0 else (word, "")
        if not NPM_NAME.match(name):
            return None
        how = ("latest" if spec in ("", "latest") else "exact" if NPM_EXACT.match(spec)
               else "tag" if NPM_TAG.match(spec) and spec not in ("x", "X") else "range")
        return name, how, spec
    m = PY_WORD.match(word)
    if not m:
        return None
    if m.group(5):
        return m.group(1), "range", m.group(5)
    spec = m.group(4) or ""
    if spec in ("", "latest"):
        return m.group(1), "latest", ""
    if PY_EXACT.match(spec):
        return m.group(1), "exact", spec
    return m.group(1), "range", f"=={spec}" if m.group(3) == "==" else spec


def package_word(name, words):
    """Where the package a runner (name) runs is among the words after it: (index, prefix, word), where prefix is
    the option the word is joined to (`--from=`), or None. That is the value of the runner's package option, else
    the first word that is not an option: the words after it are the server's own arguments."""
    eco, i = RUNNERS[name], 0
    if name in SUBCOMMANDS:
        sub = next((s for s in SUBCOMMANDS[name] if words[:len(s)] == s), None)
        if sub is None:  # `npm run`, `uv run` and the like run nothing from the registry
            return None
        i = len(sub)
    found = None
    while i < len(words):
        word = words[i]
        if word == "--":
            return found or ((i + 1, "", words[i + 1]) if i + 1 < len(words) else None)
        if not word.startswith("-"):
            return found or (i, "", word)
        option, eq, value = word.partition("=")
        if option in PACKAGE_OPTIONS[eco]:
            if found:  # two packages: which one runs is not clear
                return None
            found = (i, option + "=", value) if eq else (i + 1, "", words[i + 1]) if i + 1 < len(words) else None
            i += 1 if eq else 2
        else:
            i += 2 if option in VALUE_OPTIONS[eco] and not eq else 1
    return found


def find(args, declared):
    """The declared package the command runs: (package, index of its word in args, the option the word is joined
    to, the word, how, spec), or None."""
    start, words = command_of(args)
    at = next((i for i, w in enumerate(words[:3]) if runner(w) in RUNNERS), None)
    if at is None:
        return None
    name = runner(words[at])
    found = package_word(name, words[at + 1:])
    split = split_word(RUNNERS[name], found[2]) if found else None
    if not split:
        return None
    eco = RUNNERS[name]
    d = next((d for d in declared if (d["ecosystem"], package_key(d["ecosystem"], d["name"])) == (eco, package_key(eco, split[0]))), None)
    if not d:
        return None
    index, prefix, word = found
    return d, start + at + 1 + index, prefix, word, split[1], split[2]


def pinned(eco, word, version):
    """The command word asking for exactly this version."""
    if eco == "npm":
        at = word.find("@", 1)
        return f"{word[:at] if at > 0 else word}@{version}"
    m = PY_WORD.match(word)
    return f"{m.group(1)}{m.group(2) or ''}=={version}"


# ---- the registries --------------------------------------------------------------------------------

def registry(net, url):
    try:
        data = json.loads(net.get(url, MAX_ARCHIVE))
    except ValueError:
        raise Failed(f"{urlparse(url).hostname}: not JSON") from None
    if not isinstance(data, dict):
        raise Failed(f"{urlparse(url).hostname}: not JSON")
    return data


def release(eco, name, spec, net):
    """The version the registry gives for spec (a version, a tag, or None for the latest), and the archive to
    scan: {version, url, file, hash: (algorithm, digest), direct: the names it depends on}."""
    if eco == "npm":
        meta = registry(net, f"{NPM_REGISTRY}/{quote(name, safe='@')}/{quote(spec or 'latest', safe='')}")
        dist = meta.get("dist") if isinstance(meta.get("dist"), dict) else {}
        if not isinstance(meta.get("version"), str) or not isinstance(dist.get("tarball"), str):
            raise Failed("npm registry: no version with a tarball")
        integrity = dist.get("integrity") if isinstance(dist.get("integrity"), str) else ""
        algo, _, digest = integrity.partition("-")
        hashed = (algo, digest) if algo in ("sha512", "sha256") else ("sha1", dist.get("shasum"))
        deps = {field: meta[field] for field in ("dependencies", "optionalDependencies", "peerDependencies")
                if isinstance(meta.get(field), dict)}
        direct = sorted({n for field in ("dependencies", "optionalDependencies") for n in deps.get(field, {}) if NPM_NAME.match(n)})
        # npm fetches a git, URL or path dependency to resolve it, and may run its prepare script (lookups.read).
        elsewhere = any(isinstance(v, str) and lookups.NOT_REGISTRY.match(v.strip()) for d in deps.values() for v in d.values())
        return {"version": meta["version"], "url": dist["tarball"], "file": dist["tarball"].rsplit("/", 1)[-1],
                "hash": hashed, "direct": direct, "elsewhere": elsewhere}
    project = quote(py_name(name))
    meta = registry(net, f"{PYPI}/{project}/{quote(spec)}/json" if spec else f"{PYPI}/{project}/json")
    info = meta.get("info") if isinstance(meta.get("info"), dict) else {}
    files = [f for f in meta.get("urls") or [] if isinstance(f, dict) and isinstance(f.get("url"), str)
             and isinstance(f.get("filename"), str) and not f.get("yanked")]
    # A wheel for every platform is what an installer picks; then the sdist; then any wheel.
    ranked = sorted(files, key=lambda f: (0 if f["filename"].endswith("-none-any.whl") else 1 if f.get("packagetype") == "sdist" else 2))
    if not isinstance(info.get("version"), str) or not ranked:
        raise Failed("PyPI: no version with a file")
    f = ranked[0]
    reqs = [r.split(";", 1)[0] for r in info.get("requires_dist") or [] if isinstance(r, str) and "extra ==" not in r]
    return {"version": info["version"], "url": f["url"], "file": f["filename"],
            "hash": ("sha256", (f.get("digests") or {}).get("sha256")), "direct": sorted(lookups.requirement_names(reqs)),
            "elsewhere": False}


def matching(eco, name, spec, net):
    """The highest version of a package the registry has that the range spec matches."""
    if eco == "npm":
        versions = list((registry(net, f"{NPM_REGISTRY}/{quote(name, safe='@')}").get("versions") or {}))
    else:
        releases = registry(net, f"{PYPI}/{quote(py_name(name))}/json").get("releases") or {}
        # A version with no files, or only yanked ones, is not one an installer picks.
        versions = [v for v, files in releases.items() if isinstance(files, list)
                    and any(isinstance(f, dict) and not f.get("yanked") for f in files)]
    version = highest(eco, versions, spec)
    if version is None:
        raise Failed(f"no version of {shown(name, 80)} matches {shown(spec, 80)}")
    return version


# ---- version ranges ----------------------------------------------------------------------------------

class Unreadable(Failed):
    """A range written in a way kirby does not read."""


def highest(eco, versions, spec):
    """The highest of versions that the range spec matches, as npm (node-semver) or pip (PEP 440) reads it; None
    if none does. A pre-release counts only where the range names one (npm: of the same version), as both do.
    Unreadable if kirby does not read spec."""
    if eco == "npm":
        sets = [npm_set(s) for s in spec.split("||")]
        parsed = [(v, semver(v)) for v in versions]
        ok = [(order(key), v) for v, key in parsed if key and any(npm_matches(key, s) for s in sets)]
    else:
        specs = [pep440_spec(s) for s in spec.split(",")]
        parsed = [(v, pep440(v)) for v in versions]
        found = [(p, v) for v, p in parsed if p and all(pep440_matches(p, s) for s in specs)]
        explicit = any(s[1]["pre"] for s in specs if s[0] in ("==", ">=", "<=", "~=", "==="))
        finals = [(p, v) for p, v in found if not p["pre"]]
        # pip takes a pre-release when the range names one, or when nothing else matches.
        ok = [(p["key"], v) for p, v in (found if explicit or not finals else finals)]
    return max(ok)[1] if ok else None


SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")
PARTIAL = re.compile(r"^v?(\d+|[xX*])(?:\.(\d+|[xX*])(?:\.(\d+|[xX*])(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?)?)?$")
NPM_OPERATOR = re.compile(r"^(<=|>=|<|>|=|~>|~|\^)?(.*)$")
# The lowest pre-release of a version: npm's upper bounds stop before it, so they leave out its pre-releases too.
LOWEST = ((0, 0, ""),)


def pre_key(pre):
    """npm's order of pre-release identifiers: numbers by value, before words; more of them come later."""
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")) if pre else None


def semver(text):
    """A version as (major, minor, patch) and its pre-release key (None for a release), or None."""
    m = SEMVER.match(text)
    return ((int(m.group(1)), int(m.group(2)), int(m.group(3))), pre_key(m.group(4))) if m else None


def order(key):
    release, pre = key
    return (release, 1, ()) if pre is None else (release, 0, pre)


def npm_set(text):
    """One `||` part of a range as (the comparators every match meets, the versions whose pre-releases it names)."""
    text = re.sub(r"(<=|>=|<|>|=|~>|~|\^)\s+", r"\1", text.strip())
    hyphen = re.fullmatch(r"(\S+)\s+-\s+(\S+)", text)
    parts = [(">=", hyphen.group(1)), ("<=", hyphen.group(2))] if hyphen else \
        [NPM_OPERATOR.match(p).groups() for p in text.split()]
    comparators, named = [], set()
    for op, word in parts:
        m = PARTIAL.match(word)
        if not m:
            raise Unreadable(f"not a range kirby reads: {word!r}")
        major, minor, patch = (None if g in (None, "x", "X", "*") else int(g) for g in m.groups()[:3])
        pre = pre_key(m.group(4)) if major is not None and minor is not None and patch is not None else None
        if pre:
            named.add((major, minor, patch))
        comparators += desugar(op or "", major, minor, patch, pre)
    return comparators, named


def desugar(op, major, minor, patch, pre):
    """A comparator as plain (operator, version key) bounds, as node-semver reads it."""
    if major is None:
        return [("<", ((0, 0, 0), LOWEST))] if op in ("<", ">") else []
    full = minor is not None and patch is not None
    low = ((major, minor or 0, patch or 0), pre)

    def below(*release):
        return ("<", (release, LOWEST))
    if op in ("", "="):
        if full:
            return [("=", low)]
        return [(">=", low), below(major + 1, 0, 0) if minor is None else below(major, minor + 1, 0)]
    if op in ("~", "~>"):
        return [(">=", low), below(major + 1, 0, 0) if minor is None else below(major, minor + 1, 0)]
    if op == "^":
        top = (below(major + 1, 0, 0) if major > 0 or minor is None else below(0, minor + 1, 0) if minor > 0 or patch is None
               else below(0, 0, patch + 1))
        return [(">=", low), top]
    if op == ">":
        return [(">", low)] if full else [(">=", ((major + 1, 0, 0) if minor is None else (major, minor + 1, 0), None))]
    if op == ">=":
        return [(">=", low)]
    if op == "<":
        return [("<", low)] if full else [below(major, minor or 0, 0)]
    return [("<=", low)] if full else [below(major + 1, 0, 0) if minor is None else below(major, minor + 1, 0)]


def npm_matches(key, comparator_set):
    comparators, named = comparator_set
    if key[1] is not None and key[0] not in named:
        return False
    k = order(key)
    test = {"=": lambda b: k == b, "<": lambda b: k < b, "<=": lambda b: k <= b, ">": lambda b: k > b, ">=": lambda b: k >= b}
    return all(test[op](order(bound)) for op, bound in comparators)


PEP440 = re.compile(r"^v?(?:(\d+)!)?(\d+(?:\.\d+)*)(?:[-_.]?(a|b|c|rc|alpha|beta|pre|preview)[-_.]?(\d*))?"
                    r"(?:-(\d+)|[-_.]?(?:post|rev|r)[-_.]?(\d*))?(?:[-_.]?dev[-_.]?(\d*))?(?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?$", re.I)
PRE_LETTERS = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
PY_OPERATOR = re.compile(r"^\s*(~=|===|==|!=|<=|>=|<|>)\s*(\S+?)\s*$")


def pep440(text):
    """A version as PEP 440 orders it: {key, base: (epoch, release), pre: whether it is a pre-release, post}, or None."""
    m = PEP440.match(text.strip())
    if not m:
        return None
    epoch, release, letter, pre_n, post_dash, post_n, dev_n = m.groups()
    parts = [int(p) for p in release.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    # A part that is there with no number (`1.0.post`, `1.0.dev`) matches as "", one that is not as None.
    post, dev = post_dash if post_dash is not None else post_n, dev_n
    pre = (PRE_LETTERS[letter.lower()], int(pre_n or 0)) if letter else None
    # Infinities as (0,) below and (2,) above any value, as the packaging library orders them.
    pre_order = (0,) if pre is None and post is None and dev is not None else (2,) if pre is None else (1, *pre)
    key = (int(epoch or 0), tuple(parts), pre_order, (0,) if post is None else (1, int(post or 0)),
           (2,) if dev is None else (1, int(dev or 0)))
    return {"key": key, "base": (int(epoch or 0), tuple(parts)), "release": [int(p) for p in release.split(".")],
            "pre": pre is not None or dev is not None, "post": post is not None, "plain": pre is None and post is None and dev is None}


def pep440_spec(text):
    m = PY_OPERATOR.match(text)
    if not m:
        raise Unreadable(f"not a range kirby reads: {text!r}")
    op, word = m.groups()
    wildcard = op in ("==", "!=") and word.endswith(".*")
    v = pep440(word[:-2] if wildcard else word)
    if v is None or (wildcard and not v["plain"]) or (op == "~=" and len(v["release"]) < 2):
        raise Unreadable(f"not a range kirby reads: {text!r}")
    return op, v, wildcard, word


def pep440_matches(p, spec):
    op, v, wildcard, word = spec
    if op == "===":
        return False  # arbitrary equality compares text; a release on PyPI is never written that way here
    if wildcard or op == "~=":
        prefix = v["release"][:-1] if op == "~=" else v["release"]
        padded = list(p["base"][1]) + [0] * len(prefix)
        same = p["base"][0] == v["base"][0] and padded[:len(prefix)] == prefix
        if op == "~=":
            return same and p["key"] >= v["key"]
        return same if op == "==" else not same
    if op in ("==", "!="):
        return (p["key"] == v["key"]) == (op == "==")
    if op == ">=":
        return p["key"] >= v["key"]
    if op == "<=":
        return p["key"] <= v["key"]
    if op == ">":
        return p["key"] > v["key"] and not (p["post"] and not v["post"] and p["base"] == v["base"])
    return p["key"] < v["key"] and not (p["pre"] and not v["pre"] and p["base"] == v["base"])


def verified(data, hashed):
    algo, digest = hashed
    if not isinstance(digest, str) or not digest:
        raise Failed("the registry gives no hash for it")
    got = hashlib.new(algo, data)
    if digest not in (got.hexdigest(), base64.b64encode(got.digest()).decode()):
        raise Failed("the download does not match the registry's hash")
    return data


# ---- unpacking --------------------------------------------------------------------------------------

def unpack(data, filename, dest):
    """Unpack an archive into dest, an empty folder: regular files only (links, devices and paths that leave dest
    are left out), within MAX_FILES and MAX_UNPACKED. Returns the folder to scan: an archive's one top folder
    (npm's package/, an sdist's name-version/) or dest."""
    dest = Path(dest)
    total, count = 0, 0

    def member():
        nonlocal count
        count += 1
        if count > MAX_FILES:
            raise Failed(f"more than {MAX_FILES} files, more than kirby unpacks")

    def charge(size):
        nonlocal total
        total += size
        if total > MAX_UNPACKED:
            raise Failed(f"it unpacks to more than {MAX_UNPACKED // 1_000_000} MB, more than kirby unpacks")

    def write(rel, read, charged=False):
        """Write one member's body, read with read(limit); charged: its whole size already counts against the limit."""
        rel = inside(rel)
        if rel in (None, "."):
            return
        if charged:
            body = read()
        else:
            body = read(MAX_UNPACKED - total + 1)
            charge(len(body))
        target = dest / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Nothing written here is a link, so a path inside dest stays inside it.
            with open(target, "xb") as out:
                out.write(body)
        except OSError:  # a name taken twice, or by a folder
            pass

    try:
        if filename.endswith((".whl", ".zip")):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    member()
                    # Unix file-type bits, when the archive has them: anything but a regular file (a link) is left out.
                    kind = stat.S_IFMT(info.external_attr >> 16)
                    if info.is_dir() or (kind and kind != stat.S_IFREG):
                        continue
                    with z.open(info) as f:
                        write(info.filename, f.read)
            return dest
        # A stream, read once. Going on to the next member reads through this one's data, whether it was unpacked or
        # not, so every member's size counts against the limit before anything is read.
        with tarfile.open(fileobj=io.BytesIO(data), mode="r|*") as t:
            for m in t:
                member()
                charge(m.size)
                if m.isfile():
                    write(m.name, t.extractfile(m).read, charged=True)
    # RuntimeError: an encrypted zip member; NotImplementedError: a compression zipfile does not have.
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError, ValueError, RuntimeError, NotImplementedError,
            zlib.error, lzma.LZMAError) as e:
        raise Failed(f"could not unpack {shown(filename, 80)} ({type(e).__name__})") from None
    tops = list(dest.iterdir())
    return tops[0] if len(tops) == 1 and tops[0].is_dir() else dest


# ---- the check ---------------------------------------------------------------------------------------

def check(repo, args, net=None):
    net = net or Net()
    out = {"repo": repo, "mcp_args": list(args), "package": None, "blocked": False}

    def unchecked(why, pin=True):
        line = f"{UNCHECKED} ({why})" + ("; not pinned" if pin else "")
        out.update(facts=[line], lines=[line],
                   note=f"pattern scan: the dialog showed the user that the pattern scan and the lookups did not run on this MCP "
                        f"server{', and that its command is not pinned' if pin else ''}: {why}",
                   review=dict(NO_REVIEW))
        return out

    _, words = command_of(args)
    if remote(args):
        return unchecked("a remote server at a URL; its code does not install here", pin=False)
    if any(runner(w) in CONTAINERS for w in words[:2]):
        return unchecked("the command runs a container image, which kirby does not check")
    try:
        sha, declared = declarations(repo, net)
    except Failed as e:
        return unchecked(f"could not read this repo's package files: {e}")
    if not declared:
        return unchecked("this repo names no npm or PyPI package in a server.json, package.json or pyproject.toml")
    found = find(args, declared)
    if not found:
        names = ", ".join(shown(d["name"], 60) for d in declared[:3]) + (f", … (+{len(declared) - 3})" if len(declared) > 3 else "")
        return unchecked(f"the command runs none of the packages this repo names: {names}")

    pkg, index, prefix, word, how, spec = found
    eco, name = pkg["ecosystem"], pkg["name"]
    rel, why = None, None
    try:
        # The version the command asks for (the highest a range matches), else the one server.json gives, else
        # (None) the registry's latest.
        asked = matching(eco, name, spec, net) if how == "range" else spec if how in ("exact", "tag") else pkg["version"]
        rel = release(eco, name, asked, net)
    except Unreadable:
        why = f"the command asks for {shown(word, 80)}, a range kirby does not resolve"
    except Failed as e:
        why = str(e)
    version = rel["version"] if rel else None
    out["package"] = {"ecosystem": eco, "name": name, "version": version, "declared_in": pkg["file"]}
    what = f"{shown(name, 80)}@{shown(version, 40)}" if version else shown(name, 80)
    # The dialog's facts, each a line or a fact for words.say; lines is the same in English.
    facts = [fact("mcp_package", package=what, ecosystem=eco, file=shown(pkg["file"]))]
    if rel:
        out["mcp_args"][index] = prefix + pinned(eco, word, version)
        if how == "range":
            facts.append(fact("mcp_pinned_range", name=shown(name, 80), version=shown(version, 40), range=shown(spec, 80)))
        else:
            facts.append(fact("mcp_pinned", name=shown(name, 80), version=shown(version, 40)))
    else:
        facts.append(fact("mcp_not_pinned", name=shown(name, 80), why=why))

    looked = lookups.check_package(repo, eco, name, version, rel["direct"] if rel else [], net, why,
                                   elsewhere=bool(rel and rel["elsewhere"]))
    place = f"the {eco} package {what}" + (f" ({shown(rel['file'], 80)})" if rel else "")
    scanned = None
    if rel:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                data = verified(net.get(rel["url"], MAX_ARCHIVE), rel["hash"])
                root = unpack(data, rel["file"], tmp)
                files = listing(root)
                hits, unread = scan(root, files)
                scanned = (hits, unread, files, hashlib.sha256(data).hexdigest())
            except Failed as e:
                why = str(e)
    if scanned:
        hits, unread, files, digest = scanned
        facts += check_lines(hits, unread, len(files) - len(unread), looked, covered=f"those in {shown(rel['file'], 80)}")
        scan_text = scan_note(repo, ".", None, hits, place=place)
        # The review reads the same archive, which the file tool finds by the package and checks by its sha256.
        out["review"] = review({"package": {"ecosystem": eco, "name": name, "version": version}, "sha": digest},
                               files, hits, looked)
    else:
        facts += [f"unchecked: pattern scan ({why})", *looked["lines"]]
        scan_text = f"pattern scan: the dialog showed the user that the pattern scan did not run on {place}: {why}"
        out["review"] = {"needed": looked["found"] and not looked["blocked"], "files": []}
    pin = ("kirby pinned the command to that version; its dependencies are not pinned." if rel else
           f"kirby could not pin it ({why}), so the command installs as given.")
    out.update(facts=facts, lines=[say(f, "en") for f in facts], blocked=looked["blocked"], note="\n".join([
        scan_text, looked["note"],
        f"package: the command runs {what} ({eco}), which this repo's {shown(pkg['file'])} names at commit {sha}; "
        f"nobody verified that the repo publishes it. {pin}"]))
    return out


def read(want, net=None):
    """One file of the package the check unpacked, for the model review (the file tool). want is {ecosystem, name,
    version, sha: the archive's sha256 as the check's review gave it, path: a path inside the package}. The archive
    is downloaded again, checked against the registry's hash and that sha256, and unpacked into a temporary folder;
    nothing in it is installed or run. Returns the file's text."""
    net = net or Net()
    path = inside(want["path"])
    if path in (None, "."):
        raise Failed(f"not a path inside the package: {shown(want['path'], 160)!r}")
    name, version = want["name"], want["version"]
    rel = release(want["ecosystem"], name, version, net)
    data = verified(net.get(rel["url"], MAX_ARCHIVE), rel["hash"])
    if hashlib.sha256(data).hexdigest() != want["sha"]:
        raise Failed("the registry now gives another archive than the one checked")
    with tempfile.TemporaryDirectory() as tmp:
        target = unpack(data, rel["file"], tmp) / path
        if not target.is_file():
            raise Failed(f"{shown(name, 80)}@{shown(version, 40)} has no file {shown(path, 160)}")
        body = target.read_bytes()
    if b"\0" in body[:8192]:
        raise Failed(f"{shown(path, 160)} is a binary file")
    return body.decode("utf-8", errors="replace")


READ_KEYS = {"ecosystem", "name", "version", "sha", "path"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", nargs="?", help="the repo the server comes from, owner/repo")
    ap.add_argument("mcp_args", nargs="?", help="the install command's arguments, as a JSON list of strings")
    ap.add_argument("--read", metavar="JSON", help="print one file of a checked package instead: "
                    '{"ecosystem", "name", "version", "sha", "path"}, as the check\'s review gives them')
    args = ap.parse_args()
    if args.read is not None:
        try:
            want = json.loads(args.read)
        except ValueError:
            want = None
        if (not isinstance(want, dict) or set(want) != READ_KEYS or not all(isinstance(v, str) and v for v in want.values())
                or want["ecosystem"] not in REGISTRY_TYPES.values() or not re.fullmatch(r"[0-9a-f]{64}", want["sha"])):
            sys.exit('--read needs {"ecosystem": "npm" or "PyPI", "name", "version", "sha": 64 hex, "path"}')
        try:
            sys.stdout.write(read(want))
        except Failed as e:
            sys.exit(str(e))
        return
    if args.repo is None or args.mcp_args is None:
        ap.error("needs owner/repo and mcp_args, or --read")
    if not VALID_REPO.match(args.repo):
        sys.exit(f"not an owner/repo: {args.repo!r}")
    try:
        mcp_args = json.loads(args.mcp_args)
    except ValueError:
        mcp_args = None
    if not isinstance(mcp_args, list) or not mcp_args or not all(isinstance(a, str) for a in mcp_args):
        sys.exit("mcp_args must be a JSON list of strings")
    print(json.dumps(check(args.repo, mcp_args), ensure_ascii=False))


if __name__ == "__main__":
    main()
