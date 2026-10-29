#!/usr/bin/env python3
"""The pre-install check of a marketplace plugin: what it would install, at which commit.

    check_plugin.py owner/repo plugin [--agent claude|codex] [--commit SHA]

owner/repo is the marketplace. The check fetches it at its default branch, or at --commit (the full
sha of a marketplace the agent already added, so the check describes what it holds), reads the
plugin's entry in its marketplace file and follows the entry's source: a folder of the marketplace
repo, or another GitHub repo, at the entry's sha when it gives one and as it stands otherwise. It runs
the pattern scan (install_skill.py's) and the advisory and malware lookups (lookups.py) on the
plugin's files, and prints JSON: the dialog's facts (`lines`), the same for the model (`note`),
`blocked`, the marketplace's name and commit, and the source. Nothing is installed.

A source kirby cannot fetch from GitHub (an npm package, an archive, a command, another git host) is
reported as unchecked. Without a sha in the entry, the source is not pinned and may differ at install time.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# -I leaves this folder off the import path; these are kirby's own, next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lookups  # noqa: E402
from detect import MARKETPLACES  # noqa: E402
from install_skill import SCRIPT, VALID_REPO, VALID_SHA, listing, scan, scan_lines, scan_note  # noqa: E402
from lookups import shown  # noqa: E402

GITHUB_URL = re.compile(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$", re.I)
MANIFESTS = (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "plugin.json")


class Refusal(Exception):
    """Why there is nothing to show the user; the message is for the model."""


def fetch(url, ref, dest):
    """A shallow checkout of url at ref (a full sha, a branch or a tag; None for the default branch) in
    dest; returns its commit. No --filter: Claude Code runs a mod's processes with git's lazy fetching off."""
    for args in (["init", "-q", str(dest)], ["-C", str(dest), "fetch", "-q", "--depth", "1", url, ref or "HEAD"],
                 ["-C", str(dest), "checkout", "-q", "FETCH_HEAD"]):
        r = subprocess.run(["git", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise Refusal(f"git {' '.join(args[2:] if args[0] == '-C' else args)} failed: {r.stderr.strip()}")
    return subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def github_repo(url):
    """owner/repo for a GitHub URL or owner/repo shorthand, else None."""
    if not isinstance(url, str):
        return None
    if VALID_REPO.match(url):
        return url
    m = GITHUB_URL.match(url.strip())
    return m.group(1) if m else None


def inside(path):
    """A relative folder of a repo, normalised ("." for the root), or None if it leaves the repo."""
    parts = [p for p in path.strip().split("/") if p not in ("", ".")]
    return None if ".." in parts or path.startswith("/") or "\\" in path else "/".join(parts) or "."


def source_of(entry, doc):
    """Where an entry's plugin comes from: {"in": "marketplace", "path"}, {"in": "repo", "repo", "path",
    "ref", "sha"}, or {"in": None, "what"} for a source kirby cannot fetch from GitHub."""
    src = entry.get("source")
    if isinstance(src, dict) and src.get("source") == "local":  # Codex's form of a relative path
        src = src.get("path")
    if isinstance(src, str):
        root = ((doc.get("metadata") or {}).get("pluginRoot") or "") if isinstance(doc.get("metadata"), dict) else ""
        if src.startswith("./") or src == ".":
            path = inside(src)
        elif "/" not in src and isinstance(root, str) and root:
            path = inside(f"{root}/{src}")
        else:
            path = None
        return {"in": "marketplace", "path": path} if path else {"in": None, "what": f"the path {shown(src, 80)!r}, which is not inside the repo"}
    if not isinstance(src, dict):
        return {"in": None, "what": "an entry with no source"}
    kind = src.get("source")
    repo = github_repo(src.get("repo") if kind == "github" else src.get("url")) if kind in ("github", "url", "git-subdir") else None
    if not repo:
        where = f"a {shown(str(kind), 20)} source" if kind not in ("url", "git-subdir") else "a git repo outside GitHub"
        return {"in": None, "what": where}
    path = inside(src.get("path") or ".") if kind == "git-subdir" else "."
    if not path:
        return {"in": None, "what": f"the path {shown(str(src.get('path')), 80)!r}, which is not inside {repo}"}
    sha = src.get("sha") if isinstance(src.get("sha"), str) and VALID_SHA.match(src["sha"]) else None
    ref = src.get("ref") if isinstance(src.get("ref"), str) and src["ref"] else None
    return {"in": "repo", "repo": repo, "path": path, "ref": ref, "sha": sha}


def brings_mcp(entry, root, files):
    """Whether the plugin declares an MCP server, in its entry, a .mcp.json or its manifest."""
    if "mcpServers" in entry or ".mcp.json" in files:
        return True
    for m in MANIFESTS:
        if m in files:
            try:
                return "mcpServers" in json.loads((root / m).read_text(errors="replace"))
            except (ValueError, AttributeError, TypeError):
                return False
    return False


def check(repo, name, agent="claude", commit=None, fetch=fetch, net=None):
    with tempfile.TemporaryDirectory() as tmp:
        mk_root = Path(tmp) / "marketplace"
        sha = fetch(f"https://github.com/{repo}.git", commit, mk_root)
        if commit and sha != commit:
            raise Refusal(f"{repo} gave commit {sha[:7]}, not {commit[:7]}")
        mk_file = next((f for f in MARKETPLACES[agent] if (mk_root / f).is_file()), None)
        if not mk_file:
            raise Refusal(f"{repo} has no marketplace file at commit {sha[:7]}")
        try:
            doc = json.loads((mk_root / mk_file).read_text(errors="replace"))
        except ValueError:
            raise Refusal(f"{repo}'s {mk_file} is not JSON") from None
        plugins = doc.get("plugins") if isinstance(doc, dict) and isinstance(doc.get("plugins"), list) else []
        entry = next((p for p in plugins if isinstance(p, dict) and p.get("name") == name), None)
        if not entry:
            raise Refusal(f"{repo} has no marketplace plugin named {name}")
        if not isinstance(doc.get("name"), str) or not doc["name"]:
            raise Refusal(f"{repo}'s {mk_file} has no name")

        src = source_of(entry, doc)
        out = {"repo": repo, "plugin": name, "marketplace": doc["name"], "marketplace_file": mk_file,
               "commit": sha[:7], "sha": sha, "source": src}
        if src["in"] == "marketplace":
            src_repo, src_sha, base = repo, sha, mk_root
        elif src["in"] == "repo":
            src_repo, base = src["repo"], Path(tmp) / "source"
            src_sha = fetch(f"https://github.com/{src_repo}.git", src["sha"] or src["ref"], base)
        root = (base / src["path"]) if src["in"] else None
        if root is not None and not root.is_dir():
            raise Refusal(f"{repo}'s plugin {name} has no folder {src['path']} at commit {src_sha[:7]}")
        files = listing(root) if root is not None else []

        lines = [f"plugin: {shown(name, 60)} · marketplace {shown(doc['name'], 60)} · commit {sha[:7]}"
                 + (f" · {len(files)} files" if root is not None else "")]
        if isinstance(entry.get("description"), str) and entry["description"]:
            lines.append(f"description: {shown(entry['description'], 160)}")
        lines.append(source_line(src, src_sha if root is not None else None))
        if root is None:
            why = f"its source is {src['what']}, which kirby does not fetch"
            lines.append(f"unchecked: pattern scan, advisory lookup and malware lookup ({why})")
            out.update(files=0, scripts=[], mcp_servers=None, blocked=False, lines=lines,
                       note=f"scan: the dialog showed the user that the pattern scan and the lookups did not run on "
                            f"plugin {shown(name, 60)}: {why}")
            return out
        scripts = [shown(f) for f in files if f.endswith(SCRIPT)]
        if scripts:
            lines.append(f"scripts: {len(scripts)}, e.g. {', '.join(scripts[:2])}")
        hits, unread = scan(root, files)
        looked = lookups.check(src_repo, src_sha, root, files, net)
        lines += scan_lines(hits, unread, len(files) - len(unread)) + looked["lines"]
        note = f"{scan_note(src_repo, src['path'], src_sha, hits)}\n{looked['note']}"
        if src["in"] == "repo" and not src["sha"]:
            note += (f"\nsource: not pinned; the marketplace entry gives no sha, so {src_repo} may be at a later "
                     "commit than the one checked when the plugin installs")
        out.update(files=len(files), scripts=scripts, mcp_servers=brings_mcp(entry, root, files),
                   blocked=looked["blocked"], lines=lines, note=note, source={**src, "commit": src_sha})
        return out


def source_line(src, commit):
    if src["in"] is None:
        return f"source: {src['what']}"
    if src["in"] == "marketplace":
        return "source: the root of this repo" if src["path"] == "." else f"source: {shown(src['path'])}/ in this repo"
    named = src["repo"] if src["path"] == "." else f"{src['repo']}:{shown(src['path'])}"
    if src["sha"]:
        return f"source: {named} at commit {commit[:7]}, pinned by the marketplace entry"
    return (f"source: {named} at commit {commit[:7]} ({shown(src['ref'], 40) if src['ref'] else 'default branch'}); "
            "not pinned: the marketplace entry gives no sha, so what installs may differ from what was checked")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", help="the marketplace, owner/repo")
    ap.add_argument("plugin", help="the plugin's name in the marketplace")
    ap.add_argument("--agent", choices=MARKETPLACES, default="claude", help="whose marketplace file to read (default claude)")
    ap.add_argument("--commit", metavar="SHA", help="check the marketplace at this commit (full sha)")
    args = ap.parse_args()
    if not VALID_REPO.match(args.repo):
        sys.exit(f"not an owner/repo: {args.repo!r}")
    if args.commit is not None and not VALID_SHA.match(args.commit):
        sys.exit(f"--commit needs a full 40-character sha: {args.commit!r}")
    try:
        print(json.dumps(check(args.repo, args.plugin, args.agent, args.commit), ensure_ascii=False))
    except Refusal as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
