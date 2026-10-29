#!/usr/bin/env python3
"""The pre-install check of an MCP server: the package its install command runs, at the version it pins.

    check_mcp.py owner/repo '<mcp_args as a JSON list>'
    check_mcp.py --read '{"ecosystem": …, "name": …, "version": …, "sha": …, "path": …}'

mcp_args is what follows `claude mcp add --scope <scope>` or `codex mcp add`, for example
["github", "--", "npx", "-y", "@modelcontextprotocol/server-github"]. The repo is read only to learn which
packages it names: those in a server.json, then the name in a package.json, then in a pyproject.toml, at
the root or up to two folders down. Nothing ties such a package to the repo (the MCP registry checks a
package against a server name, not a repo), so the dialog says the repo names it and nobody verified that.

When the command runs one of those packages (through npx, uvx and the like), the check takes the version the
command asks for, else the one server.json gives, else the registry's latest; downloads that version's npm
tarball or PyPI wheel (or sdist), checks it against the registry's hash and unpacks it into a temporary
folder, never installing, importing or running any of it; runs the pattern scan (install_skill.py's) on its
files and the advisory and malware lookups (lookups.check_package) on it and its dependencies; and rewrites
the command to that version (`npx -y pkg@1.2.3`, `uvx pkg==1.2.3`). Only that package is pinned: its
dependencies are resolved at check time and may differ when the server starts (#13).

A container image, a remote server (a URL), or a command that runs none of the packages the repo names is
reported as unchecked, and the command stays as it is. Prints JSON: the dialog's facts (`lines`), the same
for the model (`note`), `blocked`, the command to install (`mcp_args`), the `package` checked, and `review`:
whether the model review runs and which files of the package it reads, with the archive's sha256 (docs/adr/0002).

--read prints one file of such a package for the review (the file tool): the same archive, downloaded again,
checked against the registry's hash and the review's sha256, and unpacked into a temporary folder.
"""
import argparse
import base64
import hashlib
import io
import json
import re
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlparse

# -I leaves this folder off the import path; these are kirby's own, next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lookups  # noqa: E402
from install_skill import VALID_REPO, VALID_SHA, check_lines, listing, review, scan, scan_note  # noqa: E402
from lookups import Failed, first_line, py_name, shown  # noqa: E402

try:
    import tomllib
except ImportError:  # before Python 3.11: pyproject.toml cannot be read
    tomllib = None

NPM_REGISTRY, PYPI = "https://registry.npmjs.org", "https://pypi.org/pypi"
# The files that name a package, in the order the check prefers them, and how deep in the repo it looks.
MANIFESTS = ("server.json", "package.json", "pyproject.toml")
DEPTH = 3
MAX_MANIFESTS = 30
REGISTRY_TYPES = {"npm": "npm", "pypi": "PyPI"}
# The commands that fetch a package from each registry and run it.
RUNNERS = {"npx": "npm", "bunx": "npm", "pnpx": "npm", "pnpm": "npm", "yarn": "npm", "npm": "npm", "bun": "npm",
           "uvx": "PyPI", "uv": "PyPI", "pipx": "PyPI"}
CONTAINERS = ("docker", "podman")
NPM_NAME = re.compile(r"^(@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9._~-]+$", re.I)
NPM_EXACT = re.compile(r"^v?\d+\.\d+\.\d+([-+][0-9A-Za-z.+-]*)?$")
NPM_TAG = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
PY_WORD = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?(?:(==|@)(.+)|(.*))$")
PY_EXACT = re.compile(r"^[0-9][0-9A-Za-z.!+-]*$")
MAX_ARCHIVE = 50_000_000
MAX_UNPACKED = 200_000_000
MAX_FILES = 10_000

UNCHECKED = "unchecked: pattern scan, advisory lookup and malware lookup"


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
    wanted = sorted((p for p in paths if p.rsplit("/", 1)[-1] in MANIFESTS and p.count("/") < DEPTH
                     and not any(s.startswith(".") or s == "node_modules" for s in p.split("/")[:-1])),
                    key=lambda p: (MANIFESTS.index(p.rsplit("/", 1)[-1]), p.count("/"), p))[:MAX_MANIFESTS]
    with ThreadPoolExecutor(max_workers=8) as pool:
        texts = list(pool.map(lambda p: net.raw(repo, p, sha), wanted))
    found, seen = [], set()
    for path, text in zip(wanted, texts):
        for eco, name, version in named(path.rsplit("/", 1)[-1], text):
            key = (eco, py_name(name) if eco == "PyPI" else name.lower())
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
    """A command word as (name, how, spec): how is "exact", "latest", "tag" or "range"; None if the word is not
    a package of that ecosystem."""
    if eco == "npm":
        at = word.find("@", 1)
        name, spec = (word[:at], word[at + 1:]) if at > 0 else (word, "")
        if not NPM_NAME.match(name):
            return None
        how = ("latest" if spec in ("", "latest") else "exact" if NPM_EXACT.match(spec) else "tag" if NPM_TAG.match(spec)
               else "range")
        return name, how, spec
    m = PY_WORD.match(word)
    if not m:
        return None
    spec = m.group(4) or ""
    how = ("range" if m.group(5) else "latest" if spec in ("", "latest") else "exact" if PY_EXACT.match(spec) else "range")
    return m.group(1), how, spec


def find(args, declared):
    """The declared package the command runs: (package, index of its word in args, how, spec), or None."""
    start, words = command_of(args)
    eco = next((RUNNERS[runner(w)] for w in words[:3] if runner(w) in RUNNERS), None)
    if eco is None:
        return None
    by_key = {(d["ecosystem"], py_name(d["name"]) if d["ecosystem"] == "PyPI" else d["name"].lower()): d for d in declared}
    for i, word in enumerate(words):
        split = split_word(eco, word) if not word.startswith("-") else None
        if split:
            d = by_key.get((eco, py_name(split[0]) if eco == "PyPI" else split[0].lower()))
            if d:
                return d, start + i, split[1], split[2]
    return None


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
        direct = sorted({n for field in ("dependencies", "optionalDependencies")
                         for n in (meta.get(field) if isinstance(meta.get(field), dict) else {}) if NPM_NAME.match(n)})
        return {"version": meta["version"], "url": dist["tarball"], "file": dist["tarball"].rsplit("/", 1)[-1],
                "hash": hashed, "direct": direct}
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
            "hash": ("sha256", (f.get("digests") or {}).get("sha256")), "direct": sorted(lookups.requirement_names(reqs))}


def verified(data, hashed):
    algo, digest = hashed
    if not isinstance(digest, str) or not digest:
        raise Failed("the registry gives no hash for it")
    got = hashlib.new(algo, data)
    if digest not in (got.hexdigest(), base64.b64encode(got.digest()).decode()):
        raise Failed("the download does not match the registry's hash")
    return data


# ---- unpacking --------------------------------------------------------------------------------------

def inside(name):
    """An archive member's path as a relative path, or None if it would leave the folder."""
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or name.startswith("/") or "\\" in name or ".." in parts or ":" in parts[0]:
        return None
    return "/".join(parts)


def unpack(data, filename, dest):
    """Unpack an archive into dest, an empty folder: regular files only (links, devices and paths that leave dest
    are left out), within MAX_FILES and MAX_UNPACKED. Returns the folder to scan: an archive's one top folder
    (npm's package/, an sdist's name-version/) or dest."""
    dest = Path(dest)
    total, count = 0, 0

    def write(rel, read):
        nonlocal total, count
        count += 1
        if count > MAX_FILES:
            raise Failed(f"more than {MAX_FILES} files, more than kirby unpacks")
        rel = inside(rel)
        if rel is None:
            return
        body = read(MAX_UNPACKED - total + 1)
        total += len(body)
        if total > MAX_UNPACKED:
            raise Failed(f"it unpacks to more than {MAX_UNPACKED // 1_000_000} MB, more than kirby unpacks")
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
                    # Unix file-type bits, when the archive has them: anything but a regular file (a link) is left out.
                    kind = stat.S_IFMT(info.external_attr >> 16)
                    if info.is_dir() or (kind and kind != stat.S_IFREG):
                        count += 1
                        continue
                    with z.open(info) as f:
                        write(info.filename, f.read)
            return dest
        # A stream, read once: the sizes the headers claim cannot make it read more than the limits allow.
        with tarfile.open(fileobj=io.BytesIO(data), mode="r|*") as t:
            for m in t:
                if not m.isfile():
                    count += 1
                    continue
                f = t.extractfile(m)
                write(m.name, f.read)
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError, ValueError) as e:
        raise Failed(f"could not unpack {shown(filename, 80)} ({type(e).__name__})") from None
    tops = list(dest.iterdir())
    return tops[0] if len(tops) == 1 and tops[0].is_dir() else dest


# ---- the check ---------------------------------------------------------------------------------------

def check(repo, args, net=None):
    net = net or Net()
    out = {"repo": repo, "mcp_args": list(args), "package": None, "blocked": False}

    def unchecked(why, pin=True):
        out.update(lines=[f"{UNCHECKED} ({why})" + ("; not pinned" if pin else "")],
                   note=f"scan: the dialog showed the user that the pattern scan and the lookups did not run on this MCP "
                        f"server{', and that its command is not pinned' if pin else ''}: {why}",
                   review={"needed": False, "files": []})
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

    pkg, index, how, spec = found
    eco, name = pkg["ecosystem"], pkg["name"]
    # The version the command asks for, else the one server.json gives, else (None) the registry's latest.
    asked = {"exact": spec, "tag": spec, "latest": pkg["version"]}
    rel, why = None, None
    if how == "range":
        why = f"the command asks for {shown(args[index], 80)}, a range kirby does not resolve"
    else:
        try:
            rel = release(eco, name, asked[how], net)
        except Failed as e:
            why = str(e)
    version = rel["version"] if rel else None
    out["package"] = {"ecosystem": eco, "name": name, "version": version, "declared_in": pkg["file"]}
    what = f"{shown(name, 80)}@{shown(version, 40)}" if version else shown(name, 80)
    lines = [f"package: {what} ({eco}), named by this repo's {shown(pkg['file'])}; not verified to come from this repo"]
    if rel:
        out["mcp_args"][index] = pinned(eco, args[index], version)
        lines.append(f"pinned: only {shown(name, 80)}, to {shown(version, 40)}; its dependencies are not pinned, so they "
                     "may differ from those checked when the server starts")
    else:
        lines.append(f"not pinned: kirby could not tell which version of {shown(name, 80)} the command installs ({why}); "
                     "it installs as given")

    looked = lookups.check_package(repo, eco, name, version, rel["direct"] if rel else [], net, why)
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
        lines += check_lines(hits, unread, len(files) - len(unread), looked, covered=f"those in {shown(rel['file'], 80)}")
        scan_text = scan_note(repo, ".", None, hits, place=place)
        # The review reads the same archive, which the file tool finds by the package and checks by its sha256.
        out["review"] = review({"package": {"ecosystem": eco, "name": name, "version": version}, "sha": digest},
                               files, hits, looked)
    else:
        lines += [f"unchecked: pattern scan ({why})", *looked["lines"]]
        scan_text = f"scan: the dialog showed the user that the pattern scan did not run on {place}: {why}"
        out["review"] = {"needed": looked["found"] and not looked["blocked"], "files": []}
    pin = ("kirby pinned the command to that version; its dependencies are not pinned." if rel else
           f"kirby could not pin it ({why}), so the command installs as given.")
    out.update(lines=lines, blocked=looked["blocked"], note="\n".join([
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
    if path is None:
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
