#!/usr/bin/env python3
"""Copy one skill folder from a GitHub repo into a skills directory.

    install_skill.py owner/repo path/to/skill-folder --scope project --check   # what would be installed
    install_skill.py owner/repo path/to/skill-folder --scope local|project|user [--force]

Scopes: project and local install into this project's .claude/skills/ (local also adds the
folder to .gitignore); user installs into ~/.claude/skills/. Use "." as the folder when
SKILL.md is at the repo root. The installed folder is named after the skill's frontmatter
`name` (falling back to the source folder's name). The source commit is recorded in
<skills dir>/<name>/.kirby.json.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DESTS = {"local": Path(".claude/skills"), "project": Path(".claude/skills"), "user": Path.home() / ".claude/skills"}
VALID_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
VALID_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SCRIPT = (".sh", ".bash", ".zsh", ".py", ".rb", ".pl", ".js", ".cjs", ".mjs", ".ts", ".cts", ".mts")


def git(*args, cwd=None):
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout.strip()


def frontmatter_name(skill_md):
    m = re.match(r"^---\s*\n(.*?)\n---", skill_md.read_text(errors="replace"), re.S)
    for line in (m.group(1) if m else "").splitlines():
        k, sep, v = line.partition(":")
        if sep and k.strip() == "name":
            return v.strip().strip("\"'")
    return None


def listing(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts)


def describe(files):
    top = sorted({f.split("/", 1)[0] + ("/" if "/" in f else "") for f in files})
    lines = [f"  top level: {', '.join(top)}"]
    scripts = [f for f in files if f.endswith(SCRIPT)]
    if scripts:
        more = f", … (+{len(scripts) - 5})" if len(scripts) > 5 else ""
        lines.append(f"  contains {len(scripts)} script(s) the skill may run: {', '.join(scripts[:5])}{more}")
    return lines


def ignore(target):
    entry = f"/{target.as_posix()}/"
    path = Path(".gitignore")
    text = path.read_text() if path.exists() else ""
    if entry in text.splitlines():
        return False
    path.write_text(text + ("" if text.endswith("\n") or not text else "\n") + entry + "\n")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("folder")
    ap.add_argument("--scope", choices=DESTS, required=True, help="local, project or user (see above)")
    ap.add_argument("--check", action="store_true", help="say what would be installed, write nothing")
    ap.add_argument("--force", action="store_true", help="replace an existing skill of the same name")
    ap.add_argument("--json", action="store_true", help="with --check, print the summary as JSON")
    args = ap.parse_args()
    if not VALID_REPO.match(args.repo):
        sys.exit(f"not an owner/repo: {args.repo!r}")
    folder = args.folder.strip("/") or "."
    if ".." in folder.split("/"):
        sys.exit(f"folder may not leave the repo: {args.folder!r}")

    with tempfile.TemporaryDirectory() as tmp:
        # No --filter: Claude Code runs a mod's processes with git's lazy fetching off, so a partial
        # clone's checkout fails there.
        git("clone", "--depth", "1", "--sparse", f"https://github.com/{args.repo}.git", tmp)
        if folder == ".":
            git("sparse-checkout", "disable", cwd=tmp)
        else:
            git("sparse-checkout", "set", "--no-cone", f"/{folder}/", cwd=tmp)
        src = Path(tmp) / folder
        if not (src / "SKILL.md").is_file():
            sys.exit(f"{args.repo}:{folder} has no SKILL.md")
        declared = frontmatter_name(src / "SKILL.md")
        fallback = args.repo.split("/")[1] if folder == "." else folder.rsplit("/", 1)[-1]
        name = declared if declared and VALID_NAME.match(declared) else fallback
        target = DESTS[args.scope] / name
        sha = git("rev-parse", "HEAD", cwd=tmp)
        files = listing(src)
        exists = target.exists()

        if args.check and args.json:
            print(json.dumps({
                "repo": args.repo, "folder": folder, "name": name, "commit": sha[:7], "target": str(target),
                "exists": exists, "files": len(files), "scripts": [f for f in files if f.endswith(SCRIPT)],
            }, ensure_ascii=False))
            return
        if args.check:
            replace = " (exists: needs --force, replaces it)" if exists else ""
            print(f"would install {args.repo}:{folder}@{sha[:7]} -> {target}{replace} ({len(files)} files)")
            print("\n".join(describe(files)))
            return
        if exists and not args.force:
            sys.exit(f"{target} already exists; pass --force to replace it")
        if exists:
            shutil.rmtree(target)
        shutil.copytree(src, target, ignore=shutil.ignore_patterns(".git"))

    (target / ".kirby.json").write_text(json.dumps(
        {"repo": args.repo, "folder": folder, "commit": sha}, indent=1) + "\n")
    print(f"installed {args.repo}:{folder}@{sha[:7]} -> {target} ({len(files)} files)")
    print("\n".join(describe(files)))
    if args.scope == "local" and ignore(target):
        print(f"added /{target.as_posix()}/ to .gitignore")
    if declared and name != declared:
        print(f"note: frontmatter name {declared!r} is not a valid folder name; installed as {name!r}")
    print("next: if it does not show up in the / menu, start a new session.")


if __name__ == "__main__":
    main()
