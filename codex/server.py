#!/usr/bin/env python3
"""kirby for Codex: a stdio MCP server with inhale's searches and its install step.

Codex starts it from the plugin root, outside the sandbox, so the searches reach GitHub without
an approval prompt each time. `install` asks the user through MCP elicitation, first the next
step and then the scope, and installs only after both. The dialogs speak the user's language;
what the tools answer is for the model, in English.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from i18n import TEXT, pick_lang

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "inhale" / "scripts"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SCOPES = ("local", "project", "user")
TIMEOUT = 120
README_MAX = 20000

STRINGS = {"type": "array", "items": {"type": "string"}}
TOOLS = [
    {
        "name": "stars",
        "description": "The user's GitHub stars, one line per repo: `owner/repo ★N · pushed DATE [star lists] — "
                       "description (topics: …)`. match keeps repos matching any term; list keeps one star list "
                       "(name or slug); lists prints only the list names and sizes; refresh skips the 24h cache.",
        "inputSchema": {"type": "object", "properties": {
            "match": STRINGS, "list": {"type": "string"}, "lists": {"type": "boolean"}, "refresh": {"type": "boolean"},
        }},
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
    },
    {
        "name": "detect",
        "description": "Inspect up to 5 repos, as JSON: kinds (marketplace, plugin-without-marketplace, skill, mcp, "
                       "other), a header line, and an install entry per installable unit. match fetches "
                       "descriptions first for skills whose path contains a term.",
        "inputSchema": {"type": "object", "properties": {"repos": STRINGS, "match": STRINGS}, "required": ["repos"]},
    },
    {
        "name": "readme",
        "description": "A repo's README, raw.",
        "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]},
    },
    {
        "name": "install",
        "description": "Install a recommended skill, plugin or MCP server for Codex. The user picks the next step in a "
                       "dialog (install / read the README first / pick another / cancel) and, to install, the scope; "
                       "the result says what they chose. kind=skill needs folder (from detect); kind=plugin needs "
                       "plugin (the marketplace plugin's name; repo is the marketplace); kind=mcp needs mcp_args, "
                       "everything that follows `codex mcp add`, e.g. [\"github\", \"--\", \"npx\", \"-y\", "
                       "\"@modelcontextprotocol/server-github\"]. force replaces an existing skill folder of the same "
                       "name. lang is the language the user writes in (e.g. \"zh-TW\"), for the dialogs.",
        "inputSchema": {"type": "object", "properties": {
            "repo": {"type": "string"},
            "kind": {"type": "string", "enum": ["skill", "plugin", "mcp"]},
            "folder": {"type": "string"},
            "plugin": {"type": "string"},
            "mcp_args": STRINGS,
            "force": {"type": "boolean"},
            "lang": {"type": "string"},
        }, "required": ["repo", "kind"]},
    },
]

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
    return f"{repo} ★{count} · pushed {(pushed or '?')[:10]}" + (" · ARCHIVED" if archived else "")


def preview(t, kind, a, project):
    """What the install would do: dialog lines, the scopes on offer, and anything the command needs."""
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
        lines = [t["kind"].format(f"skill ({c['name']})"), t["commit"].format(c["commit"]), t["files"].format(c["files"])]
        if c["scripts"]:
            lines.append(t["scripts"].format(len(c["scripts"]), ", ".join(c["scripts"][:2])))
        if project and c["exists"]:
            lines.append(t["exists"].format(c["name"], t["exists_force"][a.get("force") is True]))
        return {"lines": lines, "scopes": SCOPES if project else ("user",)}
    if kind == "plugin":
        name = a.get("plugin")
        if not isinstance(name, str) or not name:
            raise Refusal("kind=plugin needs plugin")
        ok, out = script("detect.py", "--agent", "codex", "--", repo)
        if not ok:
            raise Refusal(out)
        units = (json.loads(out)[0] or {}).get("install") or []
        unit = next((u for u in units if u.get("type") == "plugin" and u.get("name") == name), None)
        if not unit:
            raise Refusal(f"{repo} has no marketplace plugin named {name}")
        if not unit.get("marketplace"):
            raise Refusal(f"{repo}'s {unit.get('marketplaceFile')} has no name")
        lines = [t["kind"].format(f"plugin ({name})")]
        if unit.get("description"):
            lines.append(t["about"].format(unit["description"][:160]))
        if unit.get("marketplaceFile", "").startswith(".claude-plugin/"):
            lines.append(t["claude_format"])
        return {"lines": lines, "scopes": ("user",), "marketplace": unit["marketplace"]}
    args = a.get("mcp_args")
    args = [x for x in args if isinstance(x, str)] if isinstance(args, list) else []
    if not args:
        raise Refusal("kind=mcp needs mcp_args")
    return {"lines": [t["kind"].format("MCP server"), t["command"].format(f"codex mcp add {' '.join(args)}")],
            "scopes": ("user",), "mcp_args": args}


def commands(kind, a, scope, plan):
    if kind == "skill":
        argv = [sys.executable, "-I", str(SCRIPTS / "install_skill.py"), a["repo"], a["folder"],
                "--scope", scope, "--agent", "codex"]
        return [argv + ["--force"] if a.get("force") is True else argv]
    if kind == "plugin":
        return [["codex", "plugin", "marketplace", "add", a["repo"]],
                ["codex", "plugin", "add", f"{a['plugin']}@{plan['marketplace']}"]]
    return [["codex", "mcp", "add", *plan["mcp_args"]]]


def install(peer, a, meta):
    repo = a.get("repo")
    kind = a.get("kind") if a.get("kind") in ("skill", "plugin", "mcp") else None
    if not isinstance(repo, str) or not REPO_RE.match(repo):
        return f"not installed: not an owner/repo: {json.dumps(repo)}"
    if not kind:
        return "not installed: kind must be skill, plugin or mcp"
    if not peer.can_elicit:
        return "not installed: this Codex client cannot show dialogs (no MCP elicitation), so the user cannot choose."

    lang = pick_lang(a.get("lang"), os.environ.get("LC_ALL") or os.environ.get("LANG"))
    t = TEXT[lang]
    o = t["options"]
    project = project_dir(meta)

    try:
        header = repo_header(repo)
        plan = preview(t, kind, a, project)
    except Refusal as e:
        return f"not installed: {e}"

    # Cancel comes first so a stray Enter already queued when the dialog opens cancels.
    nxt = peer.ask(f"{header}\n\n" + "\n".join(plan["lines"]) + f"\n\n{t['next']}",
                   [o["cancel"], o["readme"], o["other"], o["install"]])
    log(f"install {repo} ({kind}, {lang}): next step {json.dumps(nxt, ensure_ascii=False)}")
    if nxt == o["readme"]:
        return ("not installed: the user wants to read the README first. Summarise it for them (the readme tool) "
                "and end your turn. Call this tool again only after they reply that they still want it.")
    if nxt == o["other"]:
        return "not installed: the user wants a different one. Ask which of the other recommendations to look at."
    if nxt != o["install"]:
        return f"not installed: the user {'dismissed the dialog' if nxt is None else 'cancelled'}."

    where = "\n".join(f"{s.ljust(8)}{t['where'][kind][s]}" for s in plan["scopes"])
    note = f"\n\n{t['no_project']}" if kind == "skill" and not project else ""
    picked = peer.ask(f"{t['scope']}\n\n{where}{note}", [o["cancel"], *plan["scopes"]])
    log(f"install {repo} ({kind}): scope {json.dumps(picked, ensure_ascii=False)}")
    if picked not in plan["scopes"]:
        return f"not installed: the user {'dismissed the scope dialog' if picked is None else 'cancelled at the scope step'}."

    shown, outs = [], []
    for argv in commands(kind, a, picked, plan):
        ok, out = run(argv, cwd=project or str(Path.home()))
        shown.append(" ".join(json.dumps(x) if " " in x else x for x in argv))
        outs.append(out)
        if not ok:
            return f"install failed (scope {picked}): {shown[-1]}\n{out}"
    after = f"\nnext: {AFTER[kind]}" if kind in AFTER else ""
    return f"installed (scope {picked}): " + "\n".join(shown) + "\n" + "\n".join(outs) + after


# ---- dispatch ------------------------------------------------------------------------------------

SEARCHES = {"stars": stars, "public": public, "detect": detect, "readme": readme}


def call(peer, params):
    name, a = params.get("name"), params.get("arguments") or {}
    if name == "install":
        text, ok = install(peer, a, params.get("_meta")), True
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
