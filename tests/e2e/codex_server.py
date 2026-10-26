#!/usr/bin/env python3
"""Drive codex/server.py's install() and file() with a fake peer in place of Codex's dialogs.

    python3 -I tests/e2e/codex_server.py FIXTURE_DIR PROJECT_DIR

FIXTURE_DIR is a fresh `fixture.py init` directory; this script points git at it itself, because Codex
does not pass a GIT_CONFIG_* redirect on to kirby's MCP server. PROJECT_DIR is an empty git repo the
skill installs land in. Commands that would install at user scope (plugins, MCP servers, a skill with
no project) are recorded instead of run (see Held), so nothing outside PROJECT_DIR changes. Needs a
logged-in gh (the repo header and the plugin lookup still go to GitHub). Prints PASS or FAIL per case
and exits 1 if any case failed.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "codex"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture  # noqa: E402
import server  # noqa: E402

REPO, FOLDER = fixture.REPO, fixture.FOLDER
ENGLISH = ["Cancel", "Read README first", "Pick another", "Install"]
ZH = {"about": "測試用。", "next": "下一步？", "options": ["取消", "先讀 README", "換一個", "安裝"], "scope": "裝在哪個範圍？"}
NO_DIALOG = "\nnote: the dialogs were in English because no dialog was given; pass dialog as the inhale skill describes."
failures = []


class Peer:
    """Answers each dialog from a list; an answer may be a function of the options, run when asked."""
    can_elicit = True

    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def ask(self, question, options):
        self.asked.append((question, list(options)))
        a = self.answers.pop(0)
        return a(options) if callable(a) else a


class Held:
    """In place of server.run: records the commands that would install at user scope (codex plugin/mcp,
    install_skill.py --scope user) and runs the rest."""

    def __init__(self):
        self.argv, self.run = [], server.run

    def __enter__(self):
        server.run = self
        return self

    def __exit__(self, *_):
        server.run = self.run

    def __call__(self, argv, cwd=None):
        if argv[0] == "codex" or ("--scope" in argv and argv[argv.index("--scope") + 1] == "user"
                                  and "--check" not in argv):
            self.argv.append(list(argv))
            return True, "(held)"
        return self.run(argv, cwd=cwd)


def check(case, ok, detail: object = ""):
    print(f"{'PASS' if ok else 'FAIL'}  {case}" + (f"\n      {detail}" if not ok and detail else ""))
    if not ok:
        failures.append(case)


def preview(cwd):
    out = subprocess.run([sys.executable, "-I", str(ROOT / "skills/inhale/scripts/install_skill.py"), REPO, FOLDER,
                          "--scope", "project", "--agent", "codex", "--check", "--json"],
                         cwd=cwd, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    fx, project = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    os.environ.update(fixture.redirect(fx))
    meta = {"x-codex-turn-metadata": {"workspaces": {str(project): {}}}}
    skill = {"repo": REPO, "kind": "skill", "folder": FOLDER}

    # H1: the dialog shows the tool's facts and scan; without wording it is English and the result says why.
    c = preview(project)
    p = Peer("Cancel")
    r = server.install(p, skill, meta)
    q, opts = p.asked[0]
    check("H1 dialog lists commit and every scan line",
          f"skill: security-audit · commit {c['commit']} · {c['files']} files" in q
          and all(line in q for line in c["scan_lines"]), q)
    check("H1 English options", opts == ENGLISH, opts)
    check("H1 result = cancelled + scan note + English note",
          r == "not installed: the user cancelled.\n" + c["scan_note"] + NO_DIALOG, r)
    check("H1 fixture fires all 12 rules", len({h["rule"] for h in c["scan"]["hits"]}) == 12)
    check("H1 file names are cleaned", "we?ird.py" in c["scan_note"] and "​" not in q + r)

    # H2: the model's wording is used; each choice in the first dialog gives its result.
    for answer, start in [("先讀 README", "not installed: the user wants to read the README first. Summarise it for "
                                         "them (the readme tool)"),
                          ("換一個", "not installed: the user wants a different one."),
                          (None, "not installed: the user dismissed the dialog.")]:
        p = Peer(answer)
        r = server.install(p, {**skill, "dialog": ZH}, meta)
        q, opts = p.asked[0]
        check(f"H2 {answer!r}: wording, options and result",
              q.endswith("\n\n測試用。\n\n下一步？") and opts == ZH["options"] and r.startswith(start)
              and r.endswith("\n" + c["scan_note"]) and "note:" not in r, f"{opts}\n      {r}")

    # H3: unusable wording falls back to English and names the problem.
    p = Peer("Cancel")
    r = server.install(p, {**skill, "dialog": {**ZH, "options": ZH["options"][:3]}}, meta)
    check("H3 bad options -> English + note", p.asked[0][1] == ENGLISH and r.endswith(
        "note: the dialogs were in English because dialog.options must be 4 distinct labels of at most 40 "
        "characters; pass dialog as the inhale skill describes."), r)

    # H4: the scope dialog: its options, cancel and dismiss.
    for answer, end in [("cancel", "cancelled at the scope step."), (None, "dismissed the scope dialog.")]:
        p = Peer("安裝", answer)
        r = server.install(p, {**skill, "dialog": ZH}, meta)
        check(f"H4 scope {answer!r}", p.asked[1] == ("裝在哪個範圍？", ["cancel", "local", "project", "user"])
              and r == f"not installed: the user {end}\n" + c["scan_note"], f"{p.asked[1]}\n      {r}")

    # H5: no project from Codex -> only user: the first dialog says so and why, the scope dialog's one
    # install option says where, and picking it installs there.
    p = Peer("安裝", server.SKILL_USER_OPTION)
    with Held() as held:
        r = server.install(p, {**skill, "dialog": ZH}, None)
    check("H5 no project -> only user", server.SKILL_USER_ONLY in p.asked[0][0]
          and p.asked[1] == ("裝在哪個範圍？", ["cancel", server.SKILL_USER_OPTION])
          and r.startswith("installed (scope user): ") and len(held.argv) == 1
          and held.argv[0][-6:] == ["--scope", "user", "--agent", "codex", "--commit", c["sha"]], f"{p.asked}\n      {r}")

    # H6: a commit pushed while the scope dialog is open -> nothing installed.
    shown = c["sha"]
    p = Peer("安裝", lambda _options: (subprocess.run([sys.executable, "-I", str(Path(__file__).parent / "fixture.py"),
                                                  "advance", str(fx)], check=True, capture_output=True), "local")[1])
    r = server.install(p, {**skill, "dialog": ZH}, meta)
    now = fixture.head(fx)
    check("H6 moved on -> refused, nothing written",
          r.startswith("install failed (scope local): ") and f"--commit {shown}" in r
          and f"has moved on: HEAD is now {now[:7]}, not {shown[:7]} as shown to the user; nothing installed" in r
          and not (project / ".agents").exists(), r)

    # H7: install at local: the shown commit lands, .gitignore gets the folder.
    c = preview(project)
    r = server.install(Peer("安裝", "local"), {**skill, "dialog": ZH}, meta)
    rec = project / ".agents/skills/security-audit/.kirby.json"
    gi = (project / ".gitignore").read_text() if (project / ".gitignore").exists() else ""
    check("H7 local install", r.startswith("installed (scope local): ") and f"--commit {c['sha']}" in r
          and rec.exists() and json.loads(rec.read_text())["commit"] == c["sha"]
          and "/.agents/skills/security-audit/" in gi.splitlines() and r.endswith("\n" + c["scan_note"]), r)

    # H8: the folder exists: the dialog says so; without force the install fails, with force it replaces.
    p = Peer("取消")
    server.install(p, {**skill, "dialog": ZH}, meta)
    check("H8 exists line", "exists: .agents/skills/security-audit/ (installing at local or project fails)"
          in p.asked[0][0], p.asked[0][0])
    r = server.install(Peer("安裝", "project"), {**skill, "dialog": ZH}, meta)
    check("H8 without force -> fails", r.startswith("install failed (scope project): ") and "already exists" in r, r)
    p = Peer("安裝", "project")
    r = server.install(p, {**skill, "force": True, "dialog": ZH}, meta)
    check("H8 force -> replaces", "(installing at local or project replaces it)" in p.asked[0][0]
          and r.startswith("installed (scope project): ") and r.count("--force") == 1, r)
    check("H8 project scope leaves .gitignore alone",
          (project / ".gitignore").read_text().splitlines().count("/.agents/skills/security-audit/") == 1)

    # H9: a plugin: facts, not-scanned line, where it installs; the scope dialog's install option, in the
    # server's words, runs the two commands; cancel there runs none, even when dialog 1's options are out of order.
    plugin = {"repo": "anthropics/claude-plugins-official", "kind": "plugin", "plugin": "agent-sdk-dev", "dialog": ZH}
    p = Peer("安裝", server.USER_OPTION)
    with Held() as held:
        r = server.install(p, plugin, meta)
    q = p.asked[0][0]
    check("H9 plugin facts", "plugin: agent-sdk-dev" in q
          and "description: Development kit for working with the Claude Agent SDK" in q
          and "marketplace: .claude-plugin/marketplace.json (Claude Code format)" in q
          and f"{server.PLUGIN_NOT_SCANNED}\n{server.USER_ONLY}" in q, q)
    check("H9 plugin: scope dialog, then install", p.asked[1] == ("裝在哪個範圍？", ["cancel", server.USER_OPTION])
          and held.argv == [
        ["codex", "plugin", "marketplace", "add", "anthropics/claude-plugins-official"],
        ["codex", "plugin", "add", "agent-sdk-dev@claude-plugins-official"]]
          and r.startswith("installed (scope user): codex plugin marketplace add anthropics/claude-plugins-official\n")
          and r.endswith("\nnext: The user starts a new Codex session to use it.\n" + server.PLUGIN_NOT_SCANNED), r)
    p = Peer("安裝", "cancel")
    with Held() as held:
        r = server.install(p, plugin, meta)
    check("H9 plugin cancel at scope", not held.argv
          and r == "not installed: the user cancelled at the scope step.\n" + server.PLUGIN_NOT_SCANNED, r)
    # The model put cancel last, so the user's 取消 reads as install; the scope dialog still stops it.
    p = Peer("取消", "cancel")
    with Held() as held:
        r = server.install(p, {**plugin, "dialog": {**ZH, "options": ["安裝", "先讀 README", "換一個", "取消"]}}, meta)
    check("H9 options out of order -> scope dialog still asks", len(p.asked) == 2 and not held.argv
          and r.startswith("not installed: the user cancelled at the scope step."), r)

    # H10: an MCP server: the command, not-scanned line, where it installs.
    args = ["kirby-e2e", "--", "npx", "-y", "@modelcontextprotocol/server-everything"]
    p = Peer("安裝", server.USER_OPTION)
    with Held() as held:
        r = server.install(p, {"repo": "modelcontextprotocol/servers", "kind": "mcp", "mcp_args": args, "dialog": ZH}, meta)
    check("H10 mcp facts, scope dialog, then install",
          f"MCP server: codex mcp add {' '.join(args)}\n{server.MCP_NOT_SCANNED}\n{server.USER_ONLY}" in p.asked[0][0]
          and p.asked[1][1] == ["cancel", server.USER_OPTION] and held.argv == [["codex", "mcp", "add", *args]]
          and r == f"installed (scope user): codex mcp add {' '.join(args)}\n(held)\n"
                   f"next: The user starts a new Codex session to use it.\n{server.MCP_NOT_SCANNED}", r)

    # H11: refusals before any dialog.
    for case, a, want in [
        ("bad repo", {"repo": "x", "kind": "skill"}, 'not installed: not an owner/repo: "x"'),
        ("bad kind", {"repo": REPO, "kind": "app"}, "not installed: kind must be skill, plugin or mcp"),
        ("no folder", {"repo": REPO, "kind": "skill"}, "not installed: kind=skill needs folder"),
        ("no plugin", {"repo": "anthropics/claude-plugins-official", "kind": "plugin", "plugin": "no-such-plugin"},
         "not installed: anthropics/claude-plugins-official has no marketplace plugin named no-such-plugin"),
        ("no mcp_args", {"repo": "modelcontextprotocol/servers", "kind": "mcp"}, "not installed: kind=mcp needs mcp_args"),
    ]:
        p = Peer()
        r = server.install(p, a, meta)
        check(f"H11 {case}", r == want and not p.asked, r)
    p = Peer()
    p.can_elicit = False
    check("H11 no elicitation", server.install(p, skill, meta) == "not installed: this Codex client cannot show "
          "dialogs (no MCP elicitation), so the user cannot choose." and not p.asked)

    # H12: the file tool reads a flagged line at the scanned commit (GitHub, so the real base commit).
    ok, out = server.file({"repo": REPO, "path": f"{FOLDER}/validate-findings.test.cjs", "ref": fixture.BASE})
    check("H12 file tool reads line 5 at the commit",
          ok and out.splitlines()[4] == 'const { spawnSync } = require("node:child_process");', out[:200])
    for case, a in [("..", {"path": "../x"}), ("abs", {"path": "/etc/passwd"}), ("ref", {"ref": "main"})]:
        ok, out = server.file({"repo": REPO, "path": "a.sh", "ref": fixture.BASE, **a})
        check(f"H12 file tool refuses {case}", not ok, out)

    print(f"\n{'all passed' if not failures else f'{len(failures)} failed: ' + ', '.join(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
