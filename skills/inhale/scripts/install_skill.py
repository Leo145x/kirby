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
<skills dir>/<name>/.kirby.json. With --commit (the full sha --check --json reported) that commit
is installed, even if the repo has moved on since, so the user gets what they were shown; if it can
no longer be fetched (after a force-push, say), nothing is installed. --check also runs the advisory
and malware lookups (lookups.py) on the skill's dependency files. With --json, `facts` are the check's part of
the dialog, summarised by severity (one line when nothing was found), as words.py facts each side words in the
dialog's language, and `lines` the same in English; `note` gives the model every finding, and `review` says whether
the model review runs and which files it reads, at which commit (docs/adr/0002).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# -I leaves this folder off the import path; lookups.py is kirby's own, next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lookups  # noqa: E402
from lookups import shown  # noqa: E402
from words import counted, fact, in_english  # noqa: E402

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


class GitFailed(Exception):
    """A git step that failed: step is what ran after `git`, err what git said."""

    def __init__(self, step, err):
        super().__init__(f"git {step} failed: {err}")
        self.step, self.err = step, err


def checkout(url, ref, dest, folder="."):
    """A shallow checkout of url at ref (a full sha, a branch or a tag; None for the default branch as it stands)
    in dest, of only folder; returns its commit. Only that commit and only that folder: a sparse checkout of a
    depth-1 fetch. No --filter: Claude Code runs a mod's processes with git's lazy fetching off, so a partial
    clone's checkout fails there."""
    dest = str(dest)
    steps = [["init", "-q", dest]]
    if folder != ".":
        steps.append(["-C", dest, "sparse-checkout", "set", "--no-cone", f"/{folder}/"])
    steps += [["-C", dest, "fetch", "-q", "--depth", "1", url, ref or "HEAD"], ["-C", dest, "checkout", "-q", "FETCH_HEAD"],
              ["-C", dest, "rev-parse", "HEAD"]]
    for args in steps:
        r = subprocess.run(["git", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise GitFailed(" ".join(args[2:] if args[0] == "-C" else args), r.stderr.strip())
    return r.stdout.strip()


def inside(path):
    """A path inside a folder (a repo, an archive), normalised ("." for the folder itself), or None if it would
    leave it: absolute, with a drive, a backslash or a .. part."""
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if path.startswith("/") or "\\" in path or ".." in parts or (parts and ":" in parts[0]):
        return None
    return "/".join(parts) or "."


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
    top = sorted({shown(f.split("/", 1)[0]) + ("/" if "/" in f else "") for f in files})
    lines = [f"  top level: {', '.join(top)}"]
    scripts = [shown(f) for f in files if f.endswith(SCRIPT)]
    if scripts:
        more = f", … (+{len(scripts) - 5})" if len(scripts) > 5 else ""
        lines.append(f"  contains {len(scripts)} script(s) the skill may run: {', '.join(scripts[:5])}{more}")
    return lines


# The pattern scan. A hit is a fact for the user to weigh, not a verdict: plenty of honest skills
# fetch URLs or run shell commands, so no hit blocks an install (docs/adr/0001). Rules are (name,
# severity, pattern, which files: all, md or script); warn marks the rules whose hits are rarer in
# honest skills, info the rest.
RULES = [
    # Characters a reader cannot see but the model reads: zero-width, bidi controls, Unicode tags.
    ("hidden-unicode", "warn", re.compile(
        "[\U0000200b-\U0000200d\U00002060\U0000feff\U0000202a-\U0000202e\U00002066-\U00002069\U000e0000-\U000e007f]"), "all"),
    ("injection-phrase", "warn", re.compile(
        r"\bignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts?)\b"
        r"|\b(do not|don't|never) (tell|inform|show|mention)\b[^.\n]{0,20}\buser\b", re.I), "all"),
    ("agent-config", "info", re.compile(
        r"\.claude/settings|settings\.local\.json|\.mcp\.json|\bCLAUDE\.md|\bAGENTS\.md|\.codex/config\.toml"), "all"),
    ("credentials", "warn", re.compile(
        r"\.ssh/|\bid_(rsa|ed25519)\b|\.aws/|\.netrc\b|\.git-credentials|\.config/gh\b|\.npmrc\b|\.pypirc\b"), "all"),
    ("long-base64", "info", re.compile(r"[A-Za-z0-9+/]{200,}={0,2}"), "all"),
    ("broad-tools", "info", re.compile(r"^allowed-tools:.*\bBash(?!\()|^allowed-tools:.*\bBash\(\*\)"), "md"),
    ("html-comment", "info", re.compile(r"<!--"), "md"),
    ("network", "info", re.compile(
        r"\b(curl|wget|Invoke-WebRequest|urlopen|urllib|http\.client|axios|XMLHttpRequest)\b"
        r"|\brequests\.(get|post|put|patch)\b|\bfetch\(|\bsocket\.(socket|create_connection)\("), "script"),
    ("exec", "info", re.compile(
        r"\beval\s*\(|\beval\s+[\"'$]|\bexec\s*\(|\bos\.system\b|shell=True|\bchild_process\b|\|\s*(ba|z)?sh\b"
        r"|Invoke-Expression"), "script"),
    ("decode", "info", re.compile(r"base64 +(-d|--decode)\b|\bb64decode\b|\batob\(|Buffer\.from\([^)]*base64"), "script"),
    ("env-secret", "info", re.compile(
        r"(environ|getenv|process\.env|\$\{?)[^\n]{0,20}(TOKEN|SECRET|API_KEY|PASSWORD)"), "script"),
    ("startup-files", "warn", re.compile(r"\.(bashrc|zshrc|bash_profile|profile)\b|\bcrontab\b|\blaunchctl\b"), "script"),
]
# Combination findings: one tool hitting `network` together with one of these rules, wherever in its
# files, is warn although each rule alone is info, so that the classic read-a-secret-and-send-it tool is
# not all info (docs/adr/0005). They are (name, severity, the pair of rules, what it may do).
COMBINATIONS = [
    ("send-secrets", "warn", ("network", "env-secret"), "may send secrets out"),
    ("download-run", "warn", ("network", "exec"), "may download and run code"),
    ("download-decode", "warn", ("network", "decode"), "may download and decode a payload"),
]
SEVERITY = {name: severity for name, severity, _, _ in RULES + COMBINATIONS}
RANK = {"danger": 0, "warn": 1, "info": 2}
SCAN_MAX_BYTES = 2_000_000
NOTED_HITS = 30


def by_severity(hits):
    """Hits with the weightier rules first, otherwise in the order they were found."""
    return sorted(hits, key=lambda h: RANK[SEVERITY[h["rule"]]])


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
            for name, _, pattern, where in RULES:
                if where in ("all", kind) and pattern.search(line):
                    hits.append({"rule": name, "file": rel, "line": n})
    return hits, unread


def combinations(hits):
    """The combination findings these hits make, as one line each: "<name>: <what> (<rule> + <rule>)"."""
    found = {h["rule"] for h in hits}
    return [(name, f"{name}: {what} ({' + '.join(pair)})") for name, _, pair, what in COMBINATIONS if set(pair) <= found]


def warn_names(hits):
    """The scan's warn findings as the dialog names them: the combinations, then each warn rule, in the order of
    their first hit. Info rules are left out of the dialog."""
    names = [name for name, _ in combinations(hits)]
    names += dict.fromkeys(h["rule"] for h in hits if SEVERITY[h["rule"]] != "info")
    return [fact("scan_" + name.replace("-", "_")) for name in names]


def check_facts(hits, unread, scanned, looked, why=None):
    """The pre-install check's part of the dialog, as facts (words.py): one line when the pattern scan and the
    lookups (looked, lookups.check's result) found nothing and nothing went unscanned or unchecked (docs/adr/0005);
    otherwise the summary by severity (lookups.summary), with the scan's warn findings named on the warn line, and
    its own line when it found no danger or warn finding, left files unscanned or (why) did not run."""
    if why is None and not hits and not unread and looked["nothing_found"] is not None:
        files = counted("check_files", scanned)
        deps = looked["nothing_found"]
        return [fact("check_nothing_deps", files=files, deps=deps) if deps else fact("check_nothing", files=files)]
    warn = [] if why else warn_names(hits)
    scan_facts = ([fact("scan_unchecked", why=why)] if why else
                  [*([] if warn else [fact("scan_no_warn")]), *([fact("scan_unread", count=len(unread))] if unread else [])])
    return lookups.summary(looked, warn, scan_facts)


def scan_note(repo, folder, sha, hits, place=None):
    """The pattern scan for the model, so it can read and explain a finding: repo paths at the scanned commit, or,
    with place (an MCP server's package), paths inside it. The dialog showed the user only a summary."""
    where = place or f"{repo} at commit {sha}"
    if not hits:
        return f"pattern scan: the dialog showed the user no pattern-scan findings in {where} (a pattern match, not a safety review)"
    prefix = "" if folder == "." else f"{folder}/"
    lines = [f"pattern scan: the pattern-scan findings in {where}" + (", as paths inside it" if place else "")
             + " (the dialog showed the user the warn ones by name only, without files or lines, and left out the info ones):"]
    lines += [f"  {SEVERITY[name]} {line}" for name, line in combinations(hits)]
    lines += [f"  {SEVERITY[h['rule']]} {h['rule']} {shown(prefix + h['file'], 160)}:{h['line']}"
              for h in by_severity(hits)[:NOTED_HITS]]
    if len(hits) > NOTED_HITS:
        lines.append(f"  … (+{len(hits) - NOTED_HITS} more)")
    return "\n".join(lines)


SCRIPTS_NOTED = 10


def scripts_note(files):
    """The skill's scripts for the model, by name: the dialog's skill line only counts them. None without any."""
    scripts = [shown(f) for f in files if f.endswith(SCRIPT)]
    if not scripts:
        return None
    names = ", ".join(lookups.items(scripts, SCRIPTS_NOTED))
    return f"scripts: the dialog showed the user only how many scripts the skill may run ({len(scripts)}): {names}"


# A check that read no files gives the model review nothing to read.
NO_REVIEW = {"needed": False, "files": []}


def review(where, files, hits, looked, prefix=""):
    """What the model review needs (docs/adr/0002): whether it runs, which is only when another part of the check
    found a danger or warn finding, a combination finding included, and the install is not blocked (Install is not
    offered then, so a review would only cost time and tokens); where it reads the files (where: {"repo",
    "sha"} for a commit, or {"package", "sha"} for an MCP server's package, as the file tool takes them); and
    the files there, the ones the check covered, as paths there (prefix: the folder they are in)."""
    found = any(SEVERITY[h["rule"]] != "info" for h in hits) or bool(combinations(hits)) or looked["found"]
    needed = found and not looked["blocked"]
    return {"needed": needed, **where, "files": [shown(prefix + f, 200) for f in files]}


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
    ap.add_argument("--commit", metavar="SHA", help="install this commit (full sha), not the default branch")
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
        # The commit the dialog showed, even if the repo has moved on since (docs/adr/0005).
        url = f"https://github.com/{args.repo}.git"
        try:
            sha = checkout(url, args.commit, tmp, folder)
        except GitFailed as e:
            if e.step.startswith("fetch") and args.commit:
                sys.exit(f"could not fetch {args.repo} at commit {args.commit[:7]}, the one shown to the user; nothing "
                         f"installed (a force-push can remove a commit). git: {e.err}")
            sys.exit(f"git fetch {url} failed: {e.err}" if e.step.startswith("fetch") else str(e))
        src = Path(tmp) / folder
        if not (src / "SKILL.md").is_file():
            sys.exit(f"{args.repo}:{folder} has no SKILL.md")
        declared = frontmatter_name(src / "SKILL.md")
        fallback = args.repo.split("/")[1] if folder == "." else folder.rsplit("/", 1)[-1]
        name = declared if declared and VALID_NAME.match(declared) else fallback
        target = DESTS[args.agent][args.scope] / name
        files = listing(src)
        exists = target.exists()
        hits, unread = scan(src, files)
        looked = lookups.check(args.repo, sha, src, files) if args.check else None

        if args.check:
            facts = check_facts(hits, unread, len(files) - len(unread), looked)
            summary = in_english(facts)
            if args.json:
                print(json.dumps({
                    "repo": args.repo, "folder": folder, "name": name, "commit": sha[:7], "sha": sha,
                    "target": str(target), "exists": exists, "files": len(files),
                    "scripts": [shown(f) for f in files if f.endswith(SCRIPT)],
                    "scan": {"hits": hits, "unread": unread, "combinations": [c for c, _ in combinations(hits)]},
                    "facts": facts, "lines": summary,
                    "note": "\n".join(filter(None, [scan_note(args.repo, folder, sha, hits), scripts_note(files), looked["note"]])),
                    "blocked": looked["blocked"],
                    "review": review({"repo": args.repo, "sha": sha}, files, hits, looked,
                                     prefix="" if folder == "." else f"{folder}/"),
                }, ensure_ascii=False))
                return
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
