#!/usr/bin/env python3
"""kirby for Codex: a stdio MCP server with inhale's searches and its install step.

Codex starts it from the plugin root, outside the sandbox, so the searches reach GitHub without
an approval prompt each time. `install` asks the user through MCP elicitation, first the next
step and then the scope, and installs only after both. Where `user` is the only scope (plugins and
MCP servers), the first dialog says where it installs and the scope dialog's install option says it
again in the server's words. The dialogs show the facts the server found, worded by kirby in the
language the model picked (skills/inhale/scripts/words.py, docs/adr/0006), and the model's wording in
the user's language (see dialog.py); what the tools answer is for the model, in English.

`check` runs install's pre-install check without a dialog, so that when it found a danger or warn
finding a subagent can review the files it covered through `file` (docs/adr/0002); install then takes
the review's result, and decides from its own check whether one was needed.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from dialog import CANCEL, SCOPES, next_options, read_dialog, read_review, review_note

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "inhale" / "scripts"
sys.path.insert(0, str(SCRIPTS))
# A marketplace source on GitHub, as `codex plugin marketplace list` gives it (owner/repo is added as an https URL).
from detect import GITHUB_URL  # noqa: E402
from words import fact, say  # noqa: E402

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PACKAGE_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
TIMEOUT = 120
README_MAX = 20000

STRINGS = {"type": "array", "items": {"type": "string"}}
# The searches only read GitHub (stars and public keep a cache of the user's stars, which is not the user's
# setup). install writes files and runs codex commands; with force it replaces a skill folder.
READS = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
INSTALLS = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}
TOOLS = [
    {
        "name": "stars",
        "description": "The user's GitHub stars, one line per repo: `owner/repo ★N · pushed DATE [star lists] — "
                       "description (topics: …)`. match keeps repos matching any term; list keeps one star list "
                       "(name or slug); lists prints only the list names and sizes; refresh skips the 24h cache.",
        "inputSchema": {"type": "object", "properties": {
            "match": STRINGS, "list": {"type": "string"}, "lists": {"type": "boolean"}, "refresh": {"type": "boolean"},
        }},
        "annotations": READS,
    },
    {
        "name": "public",
        "description": "Search public GitHub repos tagged with an agent-tooling topic, sorted by stars. query is "
                       "GitHub search syntax: words are ANDed, use OR for synonyms (\"diagram OR flowchart\").",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"},
            "kind": {"type": "string", "enum": ["any", "skill", "plugin", "mcp"]},
            "min_stars": {"type": "integer"},
            "limit": {"type": "integer"},
        }, "required": ["query"]},
        "annotations": READS,
    },
    {
        "name": "detect",
        "description": "Inspect up to 5 repos, as JSON: kinds (marketplace, plugin-without-marketplace, skill, mcp, "
                       "other), a header line, and an install entry per installable unit. match fetches "
                       "descriptions first for skills whose path contains a term.",
        "inputSchema": {"type": "object", "properties": {"repos": STRINGS, "match": STRINGS}, "required": ["repos"]},
        "annotations": READS,
    },
    {
        "name": "readme",
        "description": "A repo's README, raw.",
        "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]},
        "annotations": READS,
    },
    {
        "name": "file",
        "description": "One file at the commit or package the pre-install check covered, raw: for reading a pattern-scan "
                       "finding, or for the model review. For a repo, pass repo and ref, the full commit sha. For "
                       "an MCP server's package, pass package and ref as the check tool's read gives them (ref is the "
                       "sha256 of the archive checked) and path inside the package.",
        "inputSchema": {"type": "object", "properties": {
            "repo": {"type": "string"}, "path": {"type": "string"}, "ref": {"type": "string"},
            "package": {"type": "object", "properties": {
                "ecosystem": {"type": "string", "enum": ["npm", "PyPI"]}, "name": {"type": "string"},
                "version": {"type": "string"},
            }},
        }, "required": ["path", "ref"]},
        "annotations": READS,
    },
    {
        "name": "check",
        "description": "Run the pre-install check of what install would install, without a dialog, as JSON: review "
                       "(needed, not needed, or not possible), read (what to pass the file tool, with each path) and "
                       "files (the files the check covered) when a review is needed, findings (the dialog's facts, in "
                       "English) and blocked. Takes the same repo, kind and folder, plugin or mcp_args as install. When review is "
                       "needed, the inhale skill says how to have the files reviewed.",
        "inputSchema": {"type": "object", "properties": {
            "repo": {"type": "string"},
            "kind": {"type": "string", "enum": ["skill", "plugin", "mcp"]},
            "folder": {"type": "string"},
            "plugin": {"type": "string"},
            "mcp_args": STRINGS,
        }, "required": ["repo", "kind"]},
        "annotations": READS,
    },
    {
        "name": "install",
        "description": "Install a recommended skill, plugin or MCP server for Codex. The user picks the next step in a "
                       "dialog (install / read the README first / pick another / cancel) and, to install, the scope; "
                       "the result says what they chose. kind=skill needs folder (from detect); kind=plugin needs "
                       "plugin (the marketplace plugin's name; repo is the marketplace); kind=mcp needs mcp_args, "
                       "everything that follows `codex mcp add`, e.g. [\"github\", \"--\", \"npx\", \"-y\", "
                       "\"@modelcontextprotocol/server-github\"]. force replaces an existing skill folder of the same "
                       "name. dialog is the wording of both dialogs in the user's language, in the format the "
                       "inhale skill gives (about at most 120 characters); without it they are in English. "
                       "dialog.lang (en, zh-TW or zh-CN) is the language kirby words the facts in; any other is "
                       "English. When the check tool said a review is needed, pass the model review's result as "
                       "review and the check's read.ref as sha.",
        "inputSchema": {"type": "object", "properties": {
            "repo": {"type": "string"},
            "kind": {"type": "string", "enum": ["skill", "plugin", "mcp"]},
            "folder": {"type": "string"},
            "plugin": {"type": "string"},
            "mcp_args": STRINGS,
            "force": {"type": "boolean"},
            "sha": {"type": "string"},
            "review": {"type": "object", "properties": {
                "findings": {"type": "array", "items": {"type": "object", "properties": {
                    "file": {"type": "string"}, "line": {"type": "integer"}, "reason": {"type": "string"},
                }}},
                "could_not_run": {"type": "string"},
            }},
            "dialog": {"type": "object", "properties": {
                "about": {"type": "string"},
                "next": {"type": "string"},
                "options": STRINGS,
                "scope": {"type": "string"},
                "lang": {"type": "string", "description": "en, zh-TW or zh-CN; any other value is en"},
            }},
        }, "required": ["repo", "kind"]},
        "annotations": INSTALLS,
    },
]

# Where user is the only scope, the first dialog says where it goes, and the scope dialog's install option
# says it again in the server's own words: a mislabelled first dialog cannot install without the user seeing it.
USER_ONLY = fact("installs_at_user")
SKILL_USER_ONLY = fact("installs_at_user_skill")
USER_OPTION = "install at user (~/.codex/config.toml, every project)"
SKILL_USER_OPTION = "install at user (~/.agents/skills/)"

# install_skill.py prints its own next: line.
AFTER = {
    "plugin": "The user starts a new Codex session to use it.",
    "mcp": "The user starts a new Codex session to use it.",
}


class Refusal(Exception):
    pass


# ---- JSON-RPC over stdio -------------------------------------------------------------------------

class Peer:
    def __init__(self):
        self.backlog = []  # requests that arrived while a dialog was open
        self.next_id = 0
        self.can_elicit = False

    def send(self, msg):
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def read(self):
        line = sys.stdin.readline()
        if not line:
            sys.exit(0)
        return json.loads(line)

    def ask(self, question, options):
        """The option the user picked, or None if they dismissed the dialog."""
        self.next_id += 1
        rid = f"kirby-{self.next_id}"
        self.send({"jsonrpc": "2.0", "id": rid, "method": "elicitation/create", "params": {
            "message": question,
            "requestedSchema": {
                "type": "object",
                "properties": {"choice": {"type": "string", "title": "kirby", "enum": list(options)}},
                "required": ["choice"],
            },
        }})
        while True:
            m = self.read()
            if m.get("id") == rid and "method" not in m:
                break
            if "method" in m and "id" in m:
                self.backlog.append(m)
        res = m.get("result") or {}
        if res.get("action") != "accept":
            return None
        return (res.get("content") or {}).get("choice")


def log(text):
    print(f"kirby: {text}", file=sys.stderr, flush=True)


def run(argv, cwd=None):
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    return r.returncode == 0, "\n".join(s for s in (r.stdout.strip(), r.stderr.strip()) if s)


def script(name, *args, cwd=None):
    return run([sys.executable, "-I", str(SCRIPTS / name), *args], cwd=cwd)


def terms(value):
    # Terms go after an option that takes several values; one starting with "-" would end it.
    return [t for t in value if isinstance(t, str) and t and not t.startswith("-")] if isinstance(value, list) else []


# ---- searches --------------------------------------------------------------------------------------

def stars(a):
    argv = []
    if a.get("lists") is True:
        argv.append("--lists")
    if isinstance(a.get("list"), str) and a["list"]:
        argv += ["--list", a["list"]]
    if terms(a.get("match")):
        argv += ["--match", *terms(a.get("match"))]
    if a.get("refresh") is True:
        argv.append("--refresh")
    return script("stars.py", *argv)


def public(a):
    query = a.get("query")
    if not isinstance(query, str) or not query.strip():
        return False, "query is required"
    argv = []
    if a.get("kind") in ("any", "skill", "plugin", "mcp"):
        argv += ["--kind", a["kind"]]
    for key, flag in (("min_stars", "--min-stars"), ("limit", "--limit")):
        if isinstance(a.get(key), int) and not isinstance(a.get(key), bool):
            argv += [flag, str(a[key])]
    return script("public.py", *argv, "--", query)


def detect(a):
    repos = [r for r in a.get("repos") or [] if isinstance(r, str) and REPO_RE.match(r)]
    if not repos:
        return False, "repos must be a list of owner/repo"
    if len(repos) > 5:
        return False, "at most 5 repos at a time"
    match = terms(a.get("match"))
    return script("detect.py", "--agent", "codex", *(["--match", *match] if match else []), "--", *repos)


def readme(a):
    repo = a.get("repo")
    if not isinstance(repo, str) or not REPO_RE.match(repo):
        return False, f"not an owner/repo: {json.dumps(repo)}"
    ok, out = run(["gh", "api", f"repos/{repo}/readme", "-H", "Accept: application/vnd.github.raw"])
    if ok and len(out) > README_MAX:
        out = out[:README_MAX] + f"\n\n[truncated at {README_MAX} characters]"
    return ok, out


def file(a):
    repo, path, ref, package = a.get("repo"), a.get("path"), a.get("ref"), a.get("package")
    if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
        return False, f"not a path inside the {'package' if package is not None else 'repo'}: {json.dumps(path)}"
    if package is not None:
        # An MCP server's package, read from the archive the check unpacked, which ref names by its sha256.
        if repo is not None:
            return False, "give repo or package, not both"
        if (not isinstance(package, dict) or set(package) != {"ecosystem", "name", "version"}
                or package["ecosystem"] not in ("npm", "PyPI")
                or not all(isinstance(package[k], str) and package[k] for k in ("name", "version"))):
            return False, 'package must be {"ecosystem": "npm" or "PyPI", "name", "version"}, as the check tool gives it'
        if not isinstance(ref, str) or not PACKAGE_SHA_RE.match(ref):
            return False, "ref must be the sha256 the check tool gave for the package"
        ok, out = script("check_mcp.py", "--read", json.dumps({**package, "sha": ref, "path": path}))
    else:
        if not isinstance(repo, str) or not REPO_RE.match(repo):
            return False, f"not an owner/repo: {json.dumps(repo)}"
        if not isinstance(ref, str) or not SHA_RE.match(ref):
            return False, "ref must be the full 40-character commit sha"
        ok, out = run(["gh", "api", f"repos/{repo}/contents/{quote(path)}?ref={ref}", "-H", "Accept: application/vnd.github.raw"])
    if ok and len(out) > README_MAX:
        out = out[:README_MAX] + f"\n\n[truncated at {README_MAX} characters]"
    return ok, out


# ---- install -----------------------------------------------------------------------------------------

def project_dir(meta):
    # Codex names the session's workspaces in the call's metadata; the server itself runs in the plugin root.
    workspaces = ((meta or {}).get("x-codex-turn-metadata") or {}).get("workspaces") or {}
    dirs = [d for d in workspaces if isinstance(d, str) and os.path.isdir(d)]
    return dirs[0] if len(dirs) == 1 else None


def repo_header(repo):
    ok, out = run(["gh", "api", f"repos/{repo}", "--jq", "[.stargazers_count, .pushed_at, .archived] | @json"])
    if not ok:
        raise Refusal(f"gh api repos/{repo} failed: {out}")
    count, pushed, archived = json.loads(out)
    return fact("repo_archived" if archived else "repo", repo=repo, stars=count, pushed=(pushed or "?")[:10])


def added_marketplace(repo):
    """The marketplace Codex already has from this GitHub repo, as `codex plugin marketplace list` gives it
    ({name, root, …}), or None."""
    ok, out = run(["codex", "plugin", "marketplace", "list", "--json"])
    if not ok:
        raise Refusal(f"codex plugin marketplace list failed: {out}")
    try:
        # run() joins stdout and stderr, and codex can print a warning on either side of the JSON.
        listed = json.JSONDecoder().raw_decode(out[out.index("{"):])[0].get("marketplaces") or []
    except (ValueError, AttributeError):
        raise Refusal("codex plugin marketplace list --json did not give JSON") from None
    for m in listed:
        source = (m.get("marketplaceSource") or {}).get("source") if isinstance(m, dict) else None
        found = GITHUB_URL.match(source.strip()) if isinstance(source, str) else None
        if found and found.group(1).lower() == repo.lower() and isinstance(m.get("name"), str) and isinstance(m.get("root"), str):
            return m
    return None


def marketplace_head(added):
    """The commit an added marketplace is at."""
    ok, out = run(["git", "-C", added["root"], "rev-parse", "HEAD"])
    if not ok or not SHA_RE.match(out):
        raise Refusal(f"could not read it in {added['root']}: {out}")
    return out


# When kirby cannot tell which commit Codex installs from, the check goes ahead on the repo as it stands, and the
# install keeps the plugin only if it can read that commit afterwards (docs/adr/0005); hooks/plugin.ts says the same.
AS_IT_STANDS = ("the check is of its repo as it stands, and the plugin is removed again if kirby cannot tell it installs "
                "from that commit")


def not_listed(why):
    return f"unchecked: whether this marketplace is already added ({why}); {AS_IT_STANDS}"


def preview(kind, a, project):
    """What the install would do: the facts for the dialog (lines, then where it installs, each a line or a
    fact for words.say), the scopes on offer, what the model review reads and whether it is needed (review,
    the check's own), and anything the command needs."""
    repo = a["repo"]
    if kind == "skill":
        folder = a.get("folder")
        if not isinstance(folder, str) or not folder:
            raise Refusal("kind=skill needs folder")
        ok, out = script("install_skill.py", repo, folder, "--scope", "project", "--agent", "codex",
                         "--check", "--json", cwd=project or str(Path.home()))
        if not ok:
            raise Refusal(out)
        c = json.loads(out)
        lines = [fact("skill", name=c["name"], commit=c["commit"], files=c["files"])]
        if c["scripts"]:
            lines.append(fact("scripts", count=len(c["scripts"]), names=c["scripts"][:2]))
        if project and c["exists"]:
            exists = "exists_replaces" if a.get("force") is True else "exists_fails"
            lines.append(fact(exists, path=f".agents/skills/{c['name']}/"))
        lines += c["lines"]
        # The commit shown is the one installed.
        return {"lines": lines, "where": [] if project else [SKILL_USER_ONLY], "scopes": SCOPES if project else ("user",),
                "scan": c["note"], "commit": c["sha"], "blocked": c["blocked"] is True,
                "review": c["review"]}
    if kind == "plugin":
        name = a.get("plugin")
        if not isinstance(name, str) or not name:
            raise Refusal("kind=plugin needs plugin")
        # `codex plugin add` does not refresh a marketplace already added, so the check is of the commit it is
        # at, which is the one Codex installs from (docs/adr/0003).
        about, head = [], None
        try:
            added = added_marketplace(repo)
        except Refusal as e:
            added = None
            about.append(not_listed(e))
        if added:
            try:
                head = marketplace_head(added)
            except Refusal as e:
                about.append(f"unchecked: which commit the marketplace {added['name']}, already added, is at ({e}); {AS_IT_STANDS}")
        ok, out = script("check_plugin.py", "--agent", "codex", *(["--commit", head] if head else []), "--", repo, name)
        if not ok:
            raise Refusal(out)
        c = json.loads(out)
        if head:
            about.append(f"marketplace: already added as {added['name']}, at commit {c['commit']}; installs from it as it is")
        scan = [c["note"], *about]
        if c["marketplace_file"].startswith(".claude-plugin/"):
            about.append(f"marketplace: {c['marketplace_file']} (Claude Code format)")
        return {"lines": [c["lines"][0], *about, *c["lines"][1:]], "where": [USER_ONLY], "scopes": ("user",),
                "scan": "\n".join(scan), "commit": c["sha"], "blocked": c["blocked"] is True, "review": c["review"],
                "marketplace": added["name"] if added else c["marketplace"], "added": added}
    args = a.get("mcp_args")
    args = [x for x in args if isinstance(x, str)] if isinstance(args, list) else []
    if not args:
        raise Refusal("kind=mcp needs mcp_args")
    # The check gives back the command with the package it checked pinned to the version checked.
    ok, out = script("check_mcp.py", "--", repo, json.dumps(args))
    if not ok:
        raise Refusal(out)
    c = json.loads(out)
    return {"lines": [f"MCP server: codex mcp add {' '.join(c['mcp_args'])}", *c["lines"]], "where": [USER_ONLY],
            "scopes": ("user",), "scan": c["note"], "mcp_args": c["mcp_args"], "blocked": c["blocked"] is True,
            "review": c["review"]}


def commands(kind, a, scope, plan):
    if kind == "skill":
        argv = [sys.executable, "-I", str(SCRIPTS / "install_skill.py"), a["repo"], a["folder"],
                "--scope", scope, "--agent", "codex", "--commit", plan["commit"]]
        return [argv + ["--force"] if a.get("force") is True else argv]
    if kind == "plugin":
        # No --ref, so `codex plugin marketplace upgrade` keeps working; install() checks the commit afterwards
        # (docs/adr/0003).
        add = [] if plan["added"] else [["codex", "plugin", "marketplace", "add", a["repo"]]]
        return add + [["codex", "plugin", "add", f"{a['plugin']}@{plan['marketplace']}"]]
    return [["codex", "mcp", "add", *plan["mcp_args"]]]


def target(a):
    """The repo and the kind asked for; a Refusal if either is not one."""
    repo = a.get("repo")
    if not isinstance(repo, str) or not REPO_RE.match(repo):
        raise Refusal(f"not an owner/repo: {json.dumps(repo)}")
    if a.get("kind") not in ("skill", "plugin", "mcp"):
        raise Refusal("kind must be skill, plugin or mcp")
    return repo, a["kind"]


FILES_SHOWN = 200
NO_FILES = "not possible: kirby has no files of it to read; call install without review"


def check(a, meta):
    """The pre-install check that install runs, without a dialog, for the model review (docs/adr/0002): whether
    a review is needed, what the file tool reads it from and which files, and the dialog's facts."""
    try:
        _, kind = target(a)
        plan = preview(kind, a, project_dir(meta))
    except Refusal as e:
        return False, f"not checked: {e}"
    r = plan["review"]
    out = {"review": "not needed" if not r["needed"] else "needed" if r["files"] else NO_FILES}
    if out["review"] == "needed":
        out["read"] = {"repo": r["repo"], "ref": r["sha"]} if "repo" in r else {"package": r["package"], "ref": r["sha"]}
        out["files"] = r["files"][:FILES_SHOWN]
        if len(r["files"]) > FILES_SHOWN:
            out["more_files"] = len(r["files"]) - FILES_SHOWN
    # The model reads the facts in English, whatever language the dialog shows them in.
    out.update(findings=[say(f, "en") for f in [*plan["lines"], *plan["where"]]], blocked=plan["blocked"])
    return True, json.dumps(out, ensure_ascii=False)


def install(peer, a, meta):
    try:
        repo, kind = target(a)
    except Refusal as e:
        return f"not installed: {e}"
    if not peer.can_elicit:
        return "not installed: this Codex client cannot show dialogs (no MCP elicitation), so the user cannot choose."

    d, problem = read_dialog(a.get("dialog"))
    cancel, readme_, other, go = d["options"]
    # Tells the model why its wording was not used, so the next call can fix it.
    note = f"\nnote: the dialogs were in English because {problem}; pass dialog as the inhale skill describes." if problem else ""

    project = project_dir(meta)
    try:
        header = repo_header(repo)
        plan = preview(kind, a, project)
    except Refusal as e:
        return f"not installed: {e}{note}"
    # Whether a review was needed is the check's own finding, not the model's (docs/adr/0002).
    reviewed, bad_review = read_review(a.get("review"), a.get("sha"), plan["review"])
    if bad_review:
        return f"not installed: {bad_review}; call this tool again with review as the inhale skill describes.{note}"

    # Every answer from here on also tells the model what the pre-install check showed the user.
    tail = f"\n{plan['scan']}" + (f"\n{review_note(reviewed)}" if reviewed else "") + note

    # Cancel comes first so a stray Enter already queued when the dialog opens cancels.
    about = f"\n\n{d['about']}" if d["about"] else ""
    facts = [say(f, d["lang"]) for f in [header, *plan["lines"], *reviewed, *plan["where"]]]
    nxt = peer.ask("\n".join(facts) + f"{about}\n\n{d['next']}", next_options(d, plan.get("blocked", False)))
    log(f"install {repo} ({kind}): next step {json.dumps(nxt, ensure_ascii=False)}" + (f" (English: {problem})" if problem else ""))
    if nxt == readme_:
        return ("not installed: the user wants to read the README first. Summarise it for them (the readme tool) "
                "and end your turn. Call this tool again only after they reply that they still want it." + tail)
    if nxt == other:
        return "not installed: the user wants a different one. Ask which of the other recommendations to look at." + tail
    # A blocked install was not offered, whatever the answer says.
    if nxt != go or plan.get("blocked"):
        return f"not installed: the user {'dismissed the dialog' if nxt is None else 'cancelled'}.{tail}"

    # The scope dialog's options are the server's own, whatever the model wrote above.
    if plan["scopes"] == ("user",):
        labels = {"user": SKILL_USER_OPTION if kind == "skill" else USER_OPTION}
    else:
        labels = {s: s for s in plan["scopes"]}
    answer = peer.ask(d["scope"], [CANCEL, *labels.values()])
    picked = next((s for s, label in labels.items() if label == answer), None)
    log(f"install {repo} ({kind}): scope {json.dumps(answer, ensure_ascii=False)}")
    if picked is None:
        return f"not installed: the user {'dismissed the scope dialog' if answer is None else 'cancelled at the scope step'}.{tail}"

    shown, outs = [], []

    def do(argv):
        ok, out = run(argv, cwd=project or str(Path.home()))
        shown.append(" ".join(json.dumps(x) if " " in x else x for x in argv))
        outs.append(out)
        return ok

    for argv in commands(kind, a, picked, plan):
        if not do(argv):
            return f"install failed (scope {picked}): {shown[-1]}\n{outs[-1]}{tail}"
    if kind == "plugin":
        # The plugin stays only if it came from the commit the dialog showed (docs/adr/0003).
        try:
            added = plan["added"] or added_marketplace(repo)
            head = marketplace_head(added) if added else None
        except Refusal:
            head = None
        if head != plan["commit"]:
            do(["codex", "plugin", "remove", f"{a['plugin']}@{plan['marketplace']}"])
            why = (f"the marketplace {plan['marketplace']} has moved on: it is at commit {head[:7] if head else 'unknown'} "
                   f"after the install, not {plan['commit'][:7]} as shown to the user; the plugin was removed again")
            return f"install failed (scope {picked}): " + "\n".join([*shown, *filter(None, outs), why]) + tail
    after = f"\nnext: {AFTER[kind]}" if kind in AFTER else ""
    return f"installed (scope {picked}): " + "\n".join(shown) + "\n" + "\n".join(outs) + after + tail


# ---- dispatch ------------------------------------------------------------------------------------

SEARCHES = {"stars": stars, "public": public, "detect": detect, "readme": readme, "file": file}


def call(peer, params):
    name, a = params.get("name"), params.get("arguments") or {}
    if name == "install":
        text, ok = install(peer, a, params.get("_meta")), True
    elif name == "check":
        ok, text = check(a, params.get("_meta"))
    elif name in SEARCHES:
        ok, text = SEARCHES[name](a)
    else:
        return {"content": [{"type": "text", "text": f"no tool {name}"}], "isError": True}
    return {"content": [{"type": "text", "text": text or "(no output)"}], "isError": not ok}


def main():
    peer = Peer()
    while True:
        m = peer.backlog.pop(0) if peer.backlog else peer.read()
        method, mid = m.get("method"), m.get("id")
        if mid is None or method is None:
            continue  # notifications, and replies nobody waits for
        if method == "initialize":
            p = m.get("params") or {}
            peer.can_elicit = "elicitation" in (p.get("capabilities") or {})
            result = {"protocolVersion": p.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                      "serverInfo": {"name": "kirby", "version": "0.1.0"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = call(peer, m.get("params") or {})
        elif method == "ping":
            result = {}
        else:
            peer.send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}})
            continue
        peer.send({"jsonrpc": "2.0", "id": mid, "result": result})


if __name__ == "__main__":
    main()
