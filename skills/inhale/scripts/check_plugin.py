#!/usr/bin/env python3
"""The pre-install check of a marketplace plugin: what it would install, at which commit.

    check_plugin.py owner/repo plugin [--agent claude|codex] [--commit SHA]

owner/repo is the marketplace. The check fetches it at its default branch, or at --commit (the full
sha of a marketplace the agent already added, so the check describes what it holds), reads the
plugin's entry in its marketplace file and follows the entry's source: a folder of the marketplace
repo, or another GitHub repo, at the entry's sha when it gives one and as it stands otherwise. It runs
the pattern scan (install_skill.py's) and the advisory and malware lookups (lookups.py) on the
plugin's files, and prints JSON: the dialog's facts (`facts`, each a line or a key and its values for
words.py, which each side words in the dialog's language; the check's part summarised by severity), the
same in English (`lines`), every finding for the model (`note`),
`blocked`, the marketplace's name and commit, the source, and `review`: whether the model review runs
and which files it reads, in which repo at which commit (docs/adr/0002). Nothing is installed.

A source kirby cannot fetch from GitHub (an npm package, an archive, a command, another git host) is
reported as unchecked. Without a sha in the entry, the source is not pinned and may differ at install time.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

# -I leaves this folder off the import path; these are kirby's own, next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lookups  # noqa: E402
from detect import GITHUB_URL, MARKETPLACES  # noqa: E402
from install_skill import (NO_REVIEW, SCRIPT, VALID_REPO, VALID_SHA, GitFailed, check_facts, checkout,  # noqa: E402
                           inside, listing, review, scan, scan_note)
from lookups import shown  # noqa: E402
from words import fact, in_english, say  # noqa: E402

# The files a plugin declares itself in.
PLUGIN_MANIFESTS = (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "plugin.json")


class Refusal(Exception):
    """Why there is nothing to show the user; the message is for the model."""


def github_repo(url):
    """owner/repo for a GitHub URL or owner/repo shorthand, else None."""
    if not isinstance(url, str):
        return None
    if VALID_REPO.match(url):
        return url
    m = GITHUB_URL.match(url.strip())
    return m.group(1) if m else None


def source_of(entry, doc):
    """Where an entry's plugin comes from: {"in": "marketplace", "path"}, {"in": "repo", "repo", "path",
    "ref", "sha"}, or {"in": None, "what"} for a source kirby cannot fetch from GitHub, what being a fact (words.py)."""
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
        return ({"in": "marketplace", "path": path} if path else
                {"in": None, "what": fact("source_path_outside_repo", path=repr(shown(src, 80)))})
    if not isinstance(src, dict):
        return {"in": None, "what": fact("source_none")}
    kind = src.get("source")
    repo = github_repo(src.get("repo") if kind == "github" else src.get("url")) if kind in ("github", "url", "git-subdir") else None
    if not repo:
        where = fact("source_kind", kind=shown(str(kind), 20)) if kind not in ("url", "git-subdir") else fact("source_outside_github")
        return {"in": None, "what": where}
    path = inside(src.get("path") or ".") if kind == "git-subdir" else "."
    if not path:
        return {"in": None, "what": fact("source_path_outside", path=repr(shown(str(src.get("path")), 80)), repo=repo)}
    sha = src.get("sha") if isinstance(src.get("sha"), str) and VALID_SHA.match(src["sha"]) else None
    ref = src.get("ref") if isinstance(src.get("ref"), str) and src["ref"] else None
    return {"in": "repo", "repo": repo, "path": path, "ref": ref, "sha": sha}


def brings_mcp(entry, root, files):
    """Whether the plugin declares an MCP server, in its entry, a .mcp.json or its manifest."""
    if "mcpServers" in entry or ".mcp.json" in files:
        return True
    for m in PLUGIN_MANIFESTS:
        if m in files:
            try:
                return "mcpServers" in json.loads((root / m).read_text(errors="replace"))
            except (ValueError, AttributeError, TypeError):
                return False
    return False


def depends_on(entry, root, files):
    """The plugins the agent CLI installs along with this one, from its entry and its manifest: "name" or
    "name@marketplace"."""
    declared = list(entry.get("dependencies") or []) if isinstance(entry.get("dependencies"), list) else []
    manifest = next((m for m in PLUGIN_MANIFESTS if m in files), None)
    if manifest:
        try:
            deps = json.loads((root / manifest).read_text(errors="replace")).get("dependencies")
            declared += deps if isinstance(deps, list) else []
        except (ValueError, AttributeError):
            pass
    names = []
    for d in declared:
        if isinstance(d, dict) and isinstance(d.get("name"), str):
            d = d["name"] + (f"@{d['marketplace']}" if isinstance(d.get("marketplace"), str) else "")
        if isinstance(d, str) and d and shown(d, 80) not in names:
            names.append(shown(d, 80))
    return names


def check(repo, name, agent="claude", commit=None, git=checkout, net=None):
    """git: how a repo is checked out (install_skill.checkout); the tests put a fake in its place."""
    with tempfile.TemporaryDirectory() as tmp:
        mk_root = Path(tmp) / "marketplace"
        try:
            sha = git(f"https://github.com/{repo}.git", commit, mk_root)
        except GitFailed as e:
            raise Refusal(str(e)) from None
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
        title = {"name": shown(name, 60), "marketplace": shown(doc["name"], 60), "commit": sha[:7]}
        described = ([fact("plugin_description", text=shown(entry["description"], 160))]
                     if isinstance(entry.get("description"), str) and entry["description"] else [])

        def unchecked(source, why):
            """why: kirby's own reason (a fact) or git's error; the model reads it in English."""
            out.update(files=0, scripts=[], mcp_servers=None, blocked=False,
                       note=f"pattern scan: the dialog showed the user that the pattern scan and the lookups did not run on "
                            f"plugin {shown(name, 60)}: {say(why, 'en')}", review=dict(NO_REVIEW))
            return worded(out, [fact("plugin", **title), *described, source, fact("check_unchecked", why=why)])

        # Three kinds of source: one kirby does not fetch, a folder of the marketplace repo, another GitHub repo.
        if src["in"] is None:
            return unchecked(fact("plugin_source_other", what=src["what"]), fact("why_source_other", what=src["what"]))
        if src["in"] == "marketplace":
            src_repo, src_sha, base = repo, sha, mk_root
        else:
            src_repo, base = src["repo"], Path(tmp) / "source"
            try:
                src_sha = git(f"https://github.com/{src_repo}.git", src["sha"] or src["ref"], base)
            except GitFailed as e:
                return unchecked(fact("plugin_source_unfetched", source=named(src)), shown(str(e), 300))
        root = base / src["path"]
        if not root.is_dir():
            raise Refusal(f"{repo}'s plugin {name} has no folder {src['path']} at commit {src_sha[:7]}")
        files = listing(root)
        facts = [fact("plugin_files", **title, files=len(files)), *described, source_line(src, src_sha)]
        deps = depends_on(entry, root, files)
        if deps:
            facts.append(fact("plugin_dependencies", plugins=deps))
        scripts = [shown(f) for f in files if f.endswith(SCRIPT)]
        if scripts:
            facts.append(fact("scripts", count=len(scripts), names=scripts[:2]))
        hits, unread = scan(root, files)
        looked = lookups.check(src_repo, src_sha, root, files, net)
        facts += check_facts(hits, unread, len(files) - len(unread), looked)
        note = f"{scan_note(src_repo, src['path'], src_sha, hits)}\n{looked['note']}"
        if src["in"] == "repo" and not src["sha"]:
            note += (f"\nsource: not pinned; the marketplace entry gives no sha, so {src_repo} may be at a later "
                     "commit than the one checked when the plugin installs")
        if deps:
            note += f"\nplugins: the dialog showed the user that installing also installs these plugins, which were not checked: {', '.join(deps)}"
        out.update(files=len(files), scripts=scripts, mcp_servers=brings_mcp(entry, root, files),
                   blocked=looked["blocked"], note=note, source={**src, "commit": src_sha},
                   review=review({"repo": src_repo, "sha": src_sha}, files, hits, looked,
                                 prefix="" if src["path"] == "." else f"{src['path']}/"))
        return worded(out, facts)


def worded(out, facts):
    """out with the dialog's facts (each a line or a fact for words.say, which each side words in the dialog's
    language) and the same in English as lines."""
    out.update(facts=facts, lines=in_english(facts))
    return out


def named(src):
    """A source in another repo, as the dialog names it: owner/repo, or owner/repo:folder."""
    return src["repo"] if src["path"] == "." else f"{src['repo']}:{shown(src['path'])}"


def source_line(src, commit):
    """The dialog's source: line for a source that was fetched, at commit, as a fact for words.say."""
    if src["in"] == "marketplace":
        return fact("plugin_source_root") if src["path"] == "." else fact("plugin_source_folder", path=shown(src["path"]))
    if src["sha"]:
        return fact("plugin_source_pinned", source=named(src), commit=commit[:7])
    if src["ref"]:
        return fact("plugin_source_unpinned", source=named(src), commit=commit[:7], ref=shown(src["ref"], 40))
    return fact("plugin_source_unpinned_default", source=named(src), commit=commit[:7])


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
