#!/usr/bin/env python3
"""Copy one skill folder from a GitHub repo into a skills directory.

    install_skill.py owner/repo path/to/skill-folder --scope project --check   # what would be installed
    install_skill.py owner/repo path/to/skill-folder --scope local|project|user [--commit SHA] [--force]
    install_skill.py owner/repo path/to/skill-folder --scope user --agent codex

Scopes: project and local install into this project's .claude/skills/ (local also adds the
folder to .gitignore); user installs into ~/.claude/skills/, or $CLAUDE_CONFIG_DIR/skills/ when
that is set. With --agent codex the directories are .agents/skills/ and ~/.agents/skills/
instead. Use "." as the folder when
SKILL.md is at the repo root. The installed folder is named after the skill's frontmatter
`name` (falling back to the source folder's name). The source commit is recorded in
<skills dir>/<name>/.kirby.json. With --commit (the full sha --check --json reported) nothing is
installed unless the repo's HEAD is still that commit, so the user gets what they were shown.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

# Claude Code reads user skills from $CLAUDE_CONFIG_DIR/skills when that is set; Codex has no such variable.
CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
DESTS = {
    "claude": {"local": Path(".claude/skills"), "project": Path(".claude/skills"), "user": CLAUDE_HOME / "skills"},
    "codex": {"local": Path(".agents/skills"), "project": Path(".agents/skills"), "user": Path.home() / ".agents/skills"},
}
SCOPES = ("local", "project", "user")
NEXT = {
    "claude": "next: if it does not show up in the / menu, start a new session.",
    "codex": "next: if Codex does not list it, start a new session.",
}
VALID_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
VALID_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
VALID_SHA = re.compile(r"^[0-9a-f]{40}$")
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


def shown(path, limit=100):
    """A repo path as text for the dialog and the model. The repo's author picks file names, so
    invisible, control and line-breaking characters become ? and a long name is cut."""
    text = "".join("?" if unicodedata.category(ch)[0] == "C" or (ch.isspace() and ch != " ") else ch for ch in path)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def describe(files):
    top = sorted({shown(f.split("/", 1)[0]) + ("/" if "/" in f else "") for f in files})
    lines = [f"  top level: {', '.join(top)}"]
    scripts = [shown(f) for f in files if f.endswith(SCRIPT)]
    if scripts:
        more = f", … (+{len(scripts) - 5})" if len(scripts) > 5 else ""
        lines.append(f"  contains {len(scripts)} script(s) the skill may run: {', '.join(scripts[:5])}{more}")
    return lines


# The pattern scan. A hit is a fact for the user to weigh, not a verdict: plenty of honest skills
# fetch URLs or run shell commands. Rules are (name, pattern, which files: all, md or script).
RULES = [
    # Characters a reader cannot see but the model reads: zero-width, bidi controls, Unicode tags.
    ("hidden-unicode", re.compile(
        "[\U0000200b-\U0000200d\U00002060\U0000feff\U0000202a-\U0000202e\U00002066-\U00002069\U000e0000-\U000e007f]"), "all"),
    ("injection-phrase", re.compile(
        r"\bignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts?)\b"
        r"|\b(do not|don't|never) (tell|inform|show|mention)\b[^.\n]{0,20}\buser\b", re.I), "all"),
    ("agent-config", re.compile(
        r"\.claude/settings|settings\.local\.json|\.mcp\.json|\bCLAUDE\.md|\bAGENTS\.md|\.codex/config\.toml"), "all"),
    ("credentials", re.compile(
        r"\.ssh/|\bid_(rsa|ed25519)\b|\.aws/|\.netrc\b|\.git-credentials|\.config/gh\b|\.npmrc\b|\.pypirc\b"), "all"),
    ("long-base64", re.compile(r"[A-Za-z0-9+/]{200,}={0,2}"), "all"),
    ("broad-tools", re.compile(r"^allowed-tools:.*\bBash(?!\()|^allowed-tools:.*\bBash\(\*\)"), "md"),
    ("html-comment", re.compile(r"<!--"), "md"),
    ("network", re.compile(
        r"\b(curl|wget|Invoke-WebRequest|urlopen|urllib|http\.client|axios|XMLHttpRequest)\b"
        r"|\brequests\.(get|post|put|patch)\b|\bfetch\(|\bsocket\.(socket|create_connection)\("), "script"),
    ("exec", re.compile(
        r"\beval\s*\(|\beval\s+[\"'$]|\bexec\s*\(|\bos\.system\b|shell=True|\bchild_process\b|\|\s*(ba|z)?sh\b"
        r"|Invoke-Expression"), "script"),
    ("decode", re.compile(r"base64 +(-d|--decode)\b|\bb64decode\b|\batob\(|Buffer\.from\([^)]*base64"), "script"),
    ("env-secret", re.compile(
        r"(environ|getenv|process\.env|\$\{?)[^\n]{0,20}(TOKEN|SECRET|API_KEY|PASSWORD)"), "script"),
    ("startup-files", re.compile(r"\.(bashrc|zshrc|bash_profile|profile)\b|\bcrontab\b|\blaunchctl\b"), "script"),
]
SCAN_MAX_BYTES = 2_000_000
SHOWN_RULES = 6
NOTED_HITS = 30


def scan(root, files):
    """Pattern hits per file and line, and the files that could not be read as text."""
    hits, unread = [], []
    for rel in files:
        path = root / rel
        data = path.read_bytes() if path.stat().st_size <= SCAN_MAX_BYTES else None
        if data is None or b"\0" in data[:8192]:
            unread.append(rel)
            continue
        kind = "md" if rel.lower().endswith((".md", ".mdx", ".markdown")) else "script" if rel.endswith(SCRIPT) else ""
        text = data.decode("utf-8", errors="replace").removeprefix("\N{BYTE ORDER MARK}")
        for n, line in enumerate(text.splitlines(), 1):
            for name, pattern, where in RULES:
                if where in ("all", kind) and pattern.search(line):
                    hits.append({"rule": name, "file": rel, "line": n})
    return hits, unread


def scan_lines(hits, unread, scanned):
    """The scan as dialog facts: what was covered, then each flagged rule with where it hit."""
    lines = [f"scan: {scanned} files, the ones installed; a pattern match, not a safety review"
             + (f"; not scanned: {len(unread)} binary or large files" if unread else "")]
    if not hits:
        return lines + ["flagged: nothing"]
    by_rule = {}
    for h in hits:
        by_rule.setdefault(h["rule"], []).append(f"{shown(h['file'])}:{h['line']}")
    for rule, where in list(by_rule.items())[:SHOWN_RULES]:
        more = f", … (+{len(where) - 2})" if len(where) > 2 else ""
        lines.append(f"flagged: {rule} ×{len(where)} ({', '.join(where[:2])}{more})")
    rest = list(by_rule.items())[SHOWN_RULES:]
    if rest:
        lines.append("flagged also: " + ", ".join(f"{rule} ×{len(where)}" for rule, where in rest))
    return lines


def scan_note(repo, folder, sha, hits):
    """The scan for the model, so it can read and explain a hit: repo paths at the scanned commit."""
    if not hits:
        return f"scan: the dialog showed the user no pattern hits in {repo} at commit {sha} (a pattern match, not a safety review)"
    prefix = "" if folder == "." else f"{folder}/"
    lines = [f"scan: the dialog showed the user these pattern hits in {repo} at commit {sha}:"]
    lines += [f"  {h['rule']} {shown(prefix + h['file'], 160)}:{h['line']}" for h in hits[:NOTED_HITS]]
    if len(hits) > NOTED_HITS:
        lines.append(f"  … (+{len(hits) - NOTED_HITS} more)")
    return "\n".join(lines)


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
    ap.add_argument("--scope", choices=SCOPES, required=True, help="local, project or user (see above)")
    ap.add_argument("--agent", choices=DESTS, default="claude", help="whose skills directories to use (default claude)")
    ap.add_argument("--check", action="store_true", help="say what would be installed, write nothing")
    ap.add_argument("--commit", metavar="SHA", help="install only if HEAD is still this commit (full sha)")
    ap.add_argument("--force", action="store_true", help="replace an existing skill of the same name")
    ap.add_argument("--json", action="store_true", help="with --check, print the summary as JSON")
    args = ap.parse_args()
    if not VALID_REPO.match(args.repo):
        sys.exit(f"not an owner/repo: {args.repo!r}")
    folder = args.folder.strip("/") or "."
    if ".." in folder.split("/"):
        sys.exit(f"folder may not leave the repo: {args.folder!r}")
    if args.commit is not None and not VALID_SHA.match(args.commit):
        sys.exit(f"--commit needs a full 40-character sha: {args.commit!r}")

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
        target = DESTS[args.agent][args.scope] / name
        sha = git("rev-parse", "HEAD", cwd=tmp)
        if args.commit and sha != args.commit:
            sys.exit(f"{args.repo} has moved on: HEAD is now {sha[:7]}, not {args.commit[:7]} as shown to the user; "
                     "nothing installed")
        files = listing(src)
        exists = target.exists()
        hits, unread = scan(src, files)
        summary = scan_lines(hits, unread, len(files) - len(unread))

        if args.check and args.json:
            print(json.dumps({
                "repo": args.repo, "folder": folder, "name": name, "commit": sha[:7], "sha": sha, "target": str(target),
                "exists": exists, "files": len(files), "scripts": [shown(f) for f in files if f.endswith(SCRIPT)],
                "scan": {"hits": hits, "unread": unread}, "scan_lines": summary,
                "scan_note": scan_note(args.repo, folder, sha, hits),
            }, ensure_ascii=False))
            return
        if args.check:
            replace = " (exists: needs --force, replaces it)" if exists else ""
            print(f"would install {args.repo}:{folder}@{sha[:7]} -> {target}{replace} ({len(files)} files)")
            print("\n".join(describe(files)))
            print("\n".join(f"  {s}" for s in summary))
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
    print(NEXT[args.agent])


if __name__ == "__main__":
    main()
