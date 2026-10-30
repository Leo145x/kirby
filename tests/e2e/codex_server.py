#!/usr/bin/env python3
"""Drive codex/server.py's install(), check() and file() with a fake peer in place of Codex's dialogs (H1–H16).

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
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "codex"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture  # noqa: E402
import server  # noqa: E402
from words import say  # noqa: E402  (server puts the scripts on the path)

REPO, FOLDER = fixture.REPO, fixture.FOLDER
ENGLISH = ["Cancel", "Read README first", "Pick another", "Install"]
# The model's wording without a lang, so the facts are in English (H15 and H16 pick a language).
ZH = {"about": "測試用。", "next": "下一步？", "options": ["取消", "先讀 README", "換一個", "安裝"], "scope": "裝在哪個範圍？"}
USER_ONLY, SKILL_USER_ONLY = say(server.USER_ONLY, "en"), say(server.SKILL_USER_ONLY, "en")
# The scope dialog's install option where user is the only scope, as it reads with no lang.
USER_OPTION, SKILL_USER_OPTION = say(server.USER_OPTION, "en"), say(server.SKILL_USER_OPTION, "en")
NO_DIALOG = "\nnote: the dialogs were in English because no dialog was given; pass dialog as the inhale skill describes."
# The fixture's warn findings as dialog 1 names them (#26), in English and in 繁體中文 (the mock-up in #24).
WARN_7 = ("⚠ warn (7): may send secrets out, may download and run code, may download and decode a payload, "
          "prompt-injection phrases, hidden Unicode, credentials, changes shell startup files")
WARN_7_ZH = "⚠ 警告 7 項：可能外傳密鑰、可能下載並執行程式碼、可能下載並解碼資料、提示詞注入字句、隱藏 Unicode、憑證、修改啟動檔"
INFO = {"agent-config", "long-base64", "broad-tools", "html-comment", "network", "exec", "decode", "env-secret"}
# A check that found a danger or warn finding asks for a model review; an install without one says so, in the dialog
# in kirby's words and to the model in the result's review: block.
UNREVIEWED = "? model review: did not run (no review result was passed)"
UNREVIEWED_NOTE = "\nreview: the dialog showed the user that the model review did not run (no review result was passed)"
DID_NOT_RUN = "\nreview: the dialog showed the user that the model review did not run"
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
    install_skill.py --scope user) and runs the rest. `codex plugin marketplace list` answers with
    `marketplaces`, the marketplaces Codex is to have already, and once a `codex plugin marketplace add`
    is recorded, with `then`."""

    def __init__(self, marketplaces=(), then=None):
        self.argv, self.run, self.marketplaces, self.then = [], server.run, list(marketplaces), then

    def __enter__(self):
        server.run = self
        return self

    def __exit__(self, *_):
        server.run = self.run

    def __call__(self, argv, cwd=None):
        if argv[:4] == ["codex", "plugin", "marketplace", "list"]:
            added = any(a[:4] == ["codex", "plugin", "marketplace", "add"] for a in self.argv)
            return True, json.dumps({"marketplaces": self.then if added and self.then is not None else self.marketplaces})
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
    c = json.loads(out)
    # What every result after the dialog opens ends with: the pattern scan, then the lookups, then (the fixture
    # always has warn findings) the line saying no model review was passed.
    c["check_note"] = c["note"]
    c["note"] = c["check_note"] + (UNREVIEWED_NOTE if c["review"]["needed"] else "")
    return c


def plugin_check(repo, plugin, commit=None):
    out = subprocess.run([sys.executable, "-I", str(ROOT / "skills/inhale/scripts/check_plugin.py"), "--agent", "codex",
                          *(["--commit", commit] if commit else []), "--", repo, plugin],
                         capture_output=True, text=True, check=True).stdout
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
    scripts = f"scripts: {len(c['scripts'])}, e.g. {', '.join(c['scripts'][:2])}\n" if c["scripts"] else ""
    check("H1 dialog lists commit, scripts and every check line",
          f"skill: security-audit · commit {c['commit']} · {c['files']} files\n{scripts}" + "\n".join(c["lines"]) in q, q)
    check("H1 the check by severity: one warn line naming the 7 warn findings, one line for both lookups (B16)",
          c["lines"] == [WARN_7, "✓ advisory and malware lookups: nothing found"] and c["blocked"] is False, c["lines"])
    check("H1 English options", opts == ENGLISH, opts)
    check("H1 result = cancelled + scan and lookup notes + English note",
          r == "not installed: the user cancelled.\n" + c["note"] + NO_DIALOG, r)
    check("H1 fixture fires all 12 rules and the 3 combinations; the model gets each finding with its file and line",
          len({h["rule"] for h in c["scan"]["hits"]}) == 12
          and c["scan"]["combinations"] == ["send-secrets", "download-run", "download-decode"]
          and all(f"\n  {s} {h['rule']} {FOLDER}/" in c["check_note"] for h in c["scan"]["hits"]
                  for s in ("warn", "info") if s == ("info" if h["rule"] in INFO else "warn")),
          c["check_note"][:400])
    check("H1 file names are cleaned", "we?ird.py" in c["check_note"] and "\N{ZERO WIDTH SPACE}" not in q + r)
    check("H1 warn findings and no review passed -> one unchecked line, Install offered",
          c["review"]["needed"] is True and f"\n{UNREVIEWED}\n" in q and "Install" in opts, q)

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
              and r.endswith("\n" + c["note"]) and "note:" not in r, f"{opts}\n      {r}")

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
              and r == f"not installed: the user {end}\n" + c["note"], f"{p.asked[1]}\n      {r}")

    # H5: no project from Codex -> only user: the first dialog says so and why, the scope dialog's one
    # install option says where, and picking it installs there.
    p = Peer("安裝", SKILL_USER_OPTION)
    with Held() as held:
        r = server.install(p, {**skill, "dialog": ZH}, None)
    check("H5 no project -> only user", SKILL_USER_ONLY in p.asked[0][0]
          and p.asked[1] == ("裝在哪個範圍？", ["cancel", SKILL_USER_OPTION])
          and r.startswith("installed (scope user): ") and len(held.argv) == 1
          and held.argv[0][-6:] == ["--scope", "user", "--agent", "codex", "--commit", c["sha"]], f"{p.asked}\n      {r}")

    # H6: a commit pushed while the scope dialog is open -> the commit shown is installed all the same.
    def then(action, answer):
        """An answer that first runs fixture.py <action>, as if upstream changed while the dialog was open."""
        return lambda _options: (subprocess.run([sys.executable, "-I", str(Path(__file__).parent / "fixture.py"),
                                                 action, str(fx)], check=True, capture_output=True), answer)[1]

    shown = c["sha"]
    r = server.install(Peer("安裝", then("advance", "local")), {**skill, "dialog": ZH}, meta)
    now = fixture.head(fx)
    rec = project / ".agents/skills/security-audit/.kirby.json"
    check("H6 moved on -> the shown commit is installed",
          now != shown and r.startswith("installed (scope local): ") and f"--commit {shown}" in r
          and f"installed {REPO}:{FOLDER}@{shown[:7]} -> .agents/skills/security-audit" in r
          and rec.exists() and json.loads(rec.read_text())["commit"] == shown and r.endswith("\n" + c["note"]), r)
    shutil.rmtree(project / ".agents", ignore_errors=True)

    # H6: the shown commit force-pushed away and pruned while the scope dialog is open -> nothing installed.
    c = preview(project)
    gone = c["sha"]
    r = server.install(Peer("安裝", then("rewind", "local")), {**skill, "dialog": ZH}, meta)
    check("H6 shown commit gone -> install failed, says why, nothing written",
          fixture.head(fx) != gone and r.startswith("install failed (scope local): ") and f"--commit {gone}" in r
          and f"could not fetch {REPO} at commit {gone[:7]}, the one shown to the user; nothing installed "
              "(a force-push can remove a commit). git: " in r
          and r.endswith("\n" + c["note"]) and not (project / ".agents").exists(), r)

    # H7: install at local: the shown commit lands, .gitignore gets the folder.
    c = preview(project)
    r = server.install(Peer("安裝", "local"), {**skill, "dialog": ZH}, meta)
    rec = project / ".agents/skills/security-audit/.kirby.json"
    gi = (project / ".gitignore").read_text() if (project / ".gitignore").exists() else ""
    check("H7 local install", r.startswith("installed (scope local): ") and f"--commit {c['sha']}" in r
          and rec.exists() and json.loads(rec.read_text())["commit"] == c["sha"]
          and "/.agents/skills/security-audit/" in gi.splitlines() and r.endswith("\n" + c["note"]), r)

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

    # H15: dialog.lang: kirby words its own lines (repo, skill, scripts, exists, installs at) in 繁體中文 or 简体中文;
    # the check's lines too (#26), and what the tools answer the model stays English. The folder is there from H8.
    c = preview(project)
    names = "、".join(c["scripts"][:2])
    p = Peer("取消")
    r = server.install(p, {**skill, "dialog": {**ZH, "lang": "zh-TW"}}, meta)
    q = p.asked[0][0]
    check("H15 zh-TW: kirby's lines and the check's summary in 繁體中文, the result in English",
          re.match(rf"{re.escape(REPO)} ★\d+ · \d{{4}}-\d\d-\d\d 更新\n", q) is not None
          and f"\n技能：security-audit · commit {c['commit']} · {c['files']} 個檔案\n"
              + (f"{len(c['scripts'])} 個腳本，例如 {names}\n" if c["scripts"] else "")
              + "已存在：.agents/skills/security-audit/（安裝在 local 或 project 會失敗）\n"
              + f"{WARN_7_ZH}\n✓ 漏洞、惡意套件查詢：沒有發現\n" in q
          and r == "not installed: the user cancelled.\n" + c["note"], f"{q}\n      {r}")
    p = Peer("取消")
    server.install(p, {**skill, "dialog": {**ZH, "lang": "zh-CN"}}, None)
    q = p.asked[0][0]
    check("H15 zh-CN without a project: 简体中文, installs at in 简体中文",
          f"\n技能：security-audit · commit {c['commit']} · {c['files']} 个文件\n" in q
          and "\n安装位置：user（~/.agents/skills/；Codex 没有说这个会话在哪个项目）\n\n測試用。" in q, q)
    for lang in ("en", "ja"):
        p = Peer("取消")
        server.install(p, {**skill, "dialog": {**ZH, "lang": lang}}, meta)
        check(f"H15 lang {lang!r} -> English facts",
              f"\nskill: security-audit · commit {c['commit']} · {c['files']} files\n" in p.asked[0][0], p.asked[0][0])
    ok, out = server.check(skill, meta)
    check("H15 check findings stay English", ok and json.loads(out)["findings"][0]
          == f"skill: security-audit · commit {c['commit']} · {c['files']} files", out[:300])
    p = Peer("Cancel")
    r = server.install(p, {**skill, "dialog": {**ZH, "lang": "zh-TW", "about": "測" * 121}}, meta)
    check("H15 about over 120 characters -> English, facts too, and the note says why",
          p.asked[0][1] == ENGLISH and f"\nskill: security-audit · commit {c['commit']} · {c['files']} files\n" in p.asked[0][0]
          and r.endswith("\nnote: the dialogs were in English because dialog.about, when given, must be at most 120 "
                         "characters; pass dialog as the inhale skill describes."), r)

    # H9: a plugin: the pre-install check of its files, the marketplace format, where it installs; the scope
    # dialog's install option, in the server's words, adds the marketplace without a ref, installs, and
    # checks the marketplace's commit after; cancel there runs none, even when dialog 1's options are out
    # of order. A clone of the marketplace repo stands in for the one Codex would make.
    mk_repo, mk_name = "anthropics/claude-plugins-official", "claude-plugins-official"
    plugin = {"repo": mk_repo, "kind": "plugin", "plugin": "agent-sdk-dev", "dialog": ZH}
    clone = project.parent / "codex-marketplace-clone"
    shutil.rmtree(clone, ignore_errors=True)
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{mk_repo}.git", str(clone)], check=True)
    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    listed = [{"name": mk_name, "root": str(clone), "marketplaceSource": {"sourceType": "git", "source": f"https://github.com/{mk_repo}.git"}}]
    pc = plugin_check(mk_repo, "agent-sdk-dev")
    ok, out = server.check({k: plugin[k] for k in ("repo", "kind", "plugin")}, meta)
    check("H9 check: nothing found -> no review", ok and pc["review"]["needed"] is False
          and json.loads(out)["review"] == "not needed" and "files" not in json.loads(out), out[:300])
    p = Peer("安裝", USER_OPTION)
    with Held(then=listed) as held:
        r = server.install(p, plugin, meta)
    q = p.asked[0][0]
    check("H9 plugin facts: the check's lines, the format, where it installs",
          "\n".join([pc["lines"][0], "marketplace: .claude-plugin/marketplace.json (Claude Code format)", *pc["lines"][1:],
                     USER_ONLY]) in q
          and pc["lines"][1:3] == ["description: Development kit for working with the Claude Agent SDK",
                                   "source: plugins/agent-sdk-dev/ in this repo"], q)
    check("H9 plugin: scope dialog, then the marketplace added without a ref, the install, and its commit checked",
          pc["sha"] == head and p.asked[1] == ("裝在哪個範圍？", ["cancel", USER_OPTION]) and held.argv == [
              ["codex", "plugin", "marketplace", "add", mk_repo], ["codex", "plugin", "add", f"agent-sdk-dev@{mk_name}"]]
          and r.startswith(f"installed (scope user): codex plugin marketplace add {mk_repo}\n")
          and r.endswith("\nnext: The user starts a new Codex session to use it.\n" + pc["note"]), r)
    p = Peer("安裝", "cancel")
    with Held() as held:
        r = server.install(p, plugin, meta)
    check("H9 plugin cancel at scope", not held.argv
          and r == "not installed: the user cancelled at the scope step.\n" + pc["note"], r)

    # H9 a marketplace already added: checked at the commit its clone is at, not added again; moved on
    # while the scope dialog is open, the plugin is installed and then removed again.
    line = f"marketplace: already added as {mk_name}, at commit {head[:7]}; installs from it as it is"
    p = Peer("安裝", USER_OPTION)
    with Held(listed) as held:
        r = server.install(p, plugin, meta)
    check("H9 added marketplace: its commit, no add, the install", f"{line}\n" in p.asked[0][0]
          and held.argv == [["codex", "plugin", "add", f"agent-sdk-dev@{mk_name}"]]
          and r.startswith(f"installed (scope user): codex plugin add agent-sdk-dev@{mk_name}\n") and r.endswith(f"\n{line}"), r)
    # H16: dialog.lang for a plugin: its lines, the marketplace's and the install option in 繁體中文; picking the
    # translated option installs at user, and the model reads the marketplace line in English.
    option = "安裝在 user（~/.codex/config.toml，所有專案）"
    p = Peer("安裝", option)
    with Held(listed) as held:
        r = server.install(p, {**plugin, "dialog": {**ZH, "lang": "zh-TW"}}, meta)
    check("H16 zh-TW plugin: its lines, the marketplace's and the install option in 繁體中文, which installs",
          "\n".join([f"外掛：agent-sdk-dev · marketplace {mk_name} · commit {head[:7]} · {pc['files']} 個檔案",
                     f"marketplace：已加入，名稱 {mk_name}，在 commit {head[:7]}；直接從它安裝",
                     "marketplace：.claude-plugin/marketplace.json（Claude Code 格式）",
                     "說明：Development kit for working with the Claude Agent SDK",
                     "來源：這個 repo 的 plugins/agent-sdk-dev/",
                     # The check's summary in 繁體中文 too (#26).
                     *(say(f, "zh-TW") for f in pc["facts"][3:])]) in p.asked[0][0]
          and "✓ 檢查：沒有發現（" in p.asked[0][0]
          and "\n安裝位置：user（~/.codex/config.toml，所有專案）\n\n" in p.asked[0][0]
          and p.asked[1] == ("裝在哪個範圍？", ["cancel", option])
          and held.argv == [["codex", "plugin", "add", f"agent-sdk-dev@{mk_name}"]]
          and r.startswith("installed (scope user): ") and r.endswith(f"\n{line}"), f"{p.asked}\n      {r}")
    p = Peer("安裝", lambda _options: (subprocess.run(["git", "-C", str(clone), "-c", "user.name=e2e", "-c", "user.email=e2e@invalid",
                                                     "commit", "-q", "--allow-empty", "-m", "moved"], check=True), USER_OPTION)[1])
    with Held(listed) as held:
        r = server.install(p, plugin, meta)
    now = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    pid = f"agent-sdk-dev@{mk_name}"
    check("H9 added marketplace moved on -> installed, then removed again",
          held.argv == [["codex", "plugin", "add", pid], ["codex", "plugin", "remove", pid]]
          and r.startswith(f"install failed (scope user): codex plugin add {pid}\ncodex plugin remove {pid}\n(held)\n(held)\n"
                           f"the marketplace {mk_name} has moved on: it is at commit {now[:7]} after the install, not "
                           f"{head[:7]} as shown to the user; the plugin was removed again\n")
          and r.endswith(f"\n{line}"), r)
    shutil.rmtree(clone, ignore_errors=True)
    # The model put cancel last, so the user's 取消 reads as install; the scope dialog still stops it.
    p = Peer("取消", "cancel")
    with Held() as held:
        r = server.install(p, {**plugin, "dialog": {**ZH, "options": ["安裝", "先讀 README", "換一個", "取消"]}}, meta)
    check("H9 options out of order -> scope dialog still asks", len(p.asked) == 2 and not held.argv
          and r.startswith("not installed: the user cancelled at the scope step."), r)

    # H10: an MCP server: the check of the package its command runs, the command pinned to the version checked,
    # where it installs. A container image is unchecked and stays as given.
    args = ["kirby-e2e", "--", "npx", "-y", "@modelcontextprotocol/server-everything"]
    mcp = {"repo": "modelcontextprotocol/servers", "kind": "mcp", "dialog": ZH}
    out = subprocess.run([sys.executable, "-I", str(ROOT / "skills/inhale/scripts/check_mcp.py"), "--", mcp["repo"],
                          json.dumps(args)], capture_output=True, text=True, check=True).stdout
    c = json.loads(out)
    pinned = c["mcp_args"]
    check("H10 the package is found in the monorepo and pinned", pinned[:4] == args[:4]
          and re.fullmatch(r"@modelcontextprotocol/server-everything@\d+\.\d+\.\d+", pinned[4]) is not None
          and c["lines"][0] == f"package: {pinned[4]} (npm), named by this repo's src/everything/package.json; not "
                               "verified to come from this repo"
          and c["lines"][1].startswith("pinned: only @modelcontextprotocol/server-everything, to ")
          and c["lines"][2].startswith(("⚠ warn (", "✓ check: nothing found (", "✓ pattern scan: ", "✕ ")), out[:600])
    p = Peer("安裝", USER_OPTION)
    with Held() as held:
        r = server.install(p, {**mcp, "mcp_args": args}, meta)
    unreviewed = [UNREVIEWED] if c["review"]["needed"] else []
    check("H10 mcp facts, scope dialog, then install the pinned command",
          "\n".join([f"MCP server: codex mcp add {' '.join(pinned)}", *c["lines"], *unreviewed, USER_ONLY]) in p.asked[0][0]
          and p.asked[1][1] == ["cancel", USER_OPTION] and held.argv == [["codex", "mcp", "add", *pinned]]
          and r == f"installed (scope user): codex mcp add {' '.join(pinned)}\n(held)\n"
                   f"next: The user starts a new Codex session to use it.\n{c['note']}"
                   + (UNREVIEWED_NOTE if unreviewed else ""), r)
    # H16: dialog.lang for an MCP server: the command, package and pinned lines and the install option in 繁體中文,
    # with the command, package name and version as they are.
    p = Peer("安裝", "cancel")
    with Held() as held:
        server.install(p, {**mcp, "mcp_args": args, "dialog": {**ZH, "lang": "zh-TW"}}, meta)
    q = p.asked[0][0]
    check("H16 zh-TW MCP server: its lines and the install option in 繁體中文",
          f"\nMCP server：codex mcp add {' '.join(pinned)}\n套件：{pinned[4]}（npm），由這個 repo 的 src/everything/package.json "
          "指名；沒有驗證它來自這個 repo\n已鎖定：只有 @modelcontextprotocol/server-everything，鎖定在 " in q
          # The check's summary in 繁體中文 too (#26).
          and "\n".join(say(f, "zh-TW") for f in c["facts"][2:]) + "\n" in q
          and "\n安裝位置：user（~/.codex/config.toml，所有專案）\n\n" in q
          and p.asked[1][1] == ["cancel", "安裝在 user（~/.codex/config.toml，所有專案）"] and not held.argv, f"{p.asked}")
    # The review of an MCP server reads the package the check unpacked, through the file tool.
    ok, out = server.check({**{k: mcp[k] for k in ("repo", "kind")}, "mcp_args": args}, meta)
    got = json.loads(out) if ok else {}
    read = got.get("read") or {}
    check("H10 check: the package's files, named by the archive's sha256",
          got.get("review") == "needed" and read.get("package") == c["review"]["package"]
          and re.fullmatch(r"[0-9a-f]{64}", read.get("ref", "")) is not None and "package.json" in got.get("files", []), out[:400])
    ok, out = server.file({**read, "path": "package.json"})
    check("H12 file tool reads a file of the checked package",
          ok and json.loads(out).get("name") == "@modelcontextprotocol/server-everything", out[:200])
    ok, out = server.file({**read, "ref": "0" * 64, "path": "package.json"})
    check("H12 file tool refuses another archive than the one checked",
          not ok and out == "the registry now gives another archive than the one checked", out)
    docker = ["kirby-e2e", "--", "docker", "run", "-i", "--rm", "mcp/everything"]
    p = Peer("取消")
    with Held() as held:
        r = server.install(p, {**mcp, "mcp_args": docker}, meta)
    unchecked = ("? unchecked: pattern scan, advisory lookup and malware lookup (the command runs a container image, which "
                 "kirby does not check); not pinned")
    check("H10 a container image is unchecked and not pinned",
          f"MCP server: codex mcp add {' '.join(docker)}\n{unchecked}\n{USER_ONLY}" in p.asked[0][0] and not held.argv
          and r.startswith("not installed: the user cancelled.\npattern scan: the dialog showed the user that the pattern scan "
                           "and the lookups did not run on this MCP server"), r)

    # H11: refusals before any dialog. Past the repo and the kind, they also say why the dialogs would be in English,
    # as Claude Code's do.
    for case, a, want in [
        ("bad repo", {"repo": "x", "kind": "skill"}, 'not installed: not an owner/repo: "x"'),
        ("bad kind", {"repo": REPO, "kind": "app"}, "not installed: kind must be skill, plugin or mcp"),
        ("no folder", {"repo": REPO, "kind": "skill"}, "not installed: kind=skill needs folder" + NO_DIALOG),
        ("no plugin", {"repo": "anthropics/claude-plugins-official", "kind": "plugin", "plugin": "no-such-plugin"},
         "not installed: anthropics/claude-plugins-official has no marketplace plugin named no-such-plugin" + NO_DIALOG),
        ("no mcp_args", {"repo": "modelcontextprotocol/servers", "kind": "mcp"},
         "not installed: kind=mcp needs mcp_args" + NO_DIALOG),
    ]:
        p = Peer()
        with Held():
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

    # H14: check, then the model review's result into install: the check says a review is needed and what it
    # reads; the dialog counts the review's findings on the warn line and shows none of the reviewer's text, which
    # reaches the model in the result's review: block (docs/adr/0006); a review of another commit, one that could not
    # run and one that found nothing are one line of kirby's; one outside the limits opens no dialog. The fixture has
    # warn findings, so a review is needed.
    c = preview(project)
    ok, out = server.check(skill, meta)
    got = json.loads(out) if ok else {}
    check("H14 check: review needed, the fixture's files at the commit checked, the dialog's facts",
          got.get("review") == "needed" and got.get("read") == {"repo": REPO, "ref": c["sha"]}
          and f"{FOLDER}/e2e-setup.sh" in got.get("files", []) and got.get("findings", [])[-len(c["lines"]):] == c["lines"]
          and got.get("blocked") is False, out[:400])
    finding = {"file": f"{FOLDER}/e2e-setup.sh", "line": 5, "reason": "Reads the​ user's SSH key.\nSends it out."}
    base = c["check_note"]
    found = {**skill, "sha": c["sha"], "review": {"findings": [finding]}}
    p = Peer("取消")
    r = server.install(p, {**found, "dialog": ZH}, meta)
    check("H14 findings counted on the warn line, none of their text in the dialog; cleaned in the result",
          "\n".join([WARN_7.replace("(7)", "(8)") + ", model review (1)", *c["lines"][1:]]) + "\n\n測試用。" in p.asked[0][0]
          and "SSH" not in p.asked[0][0] and p.asked[0][1] == ZH["options"]
          and r == f"not installed: the user cancelled.\n{base}\nreview: the model review's findings, as reported by the model "
                   f"(the dialog showed the user only how many, on the warn line):\n  warn: {FOLDER}/e2e-setup.sh:5: Reads "
                   "the user's SSH key. Sends it out.", r)
    p = Peer("取消")
    server.install(p, {**found, "dialog": {**ZH, "lang": "zh-TW"}}, meta)
    check("H14 with zh-TW the count is in 繁體中文",
          f"\n{WARN_7_ZH.replace('7 項', '8 項')}、模型審查 1 項\n✓ 漏洞、惡意套件查詢：沒有發現\n" in p.asked[0][0], p.asked[0][0])
    other = f"it read fffffff, not {c['sha'][:7]}, the one checked here"
    for case, a, want, note in [
        ("another commit", {"sha": "f" * 40, "review": {"findings": []}}, f"? model review: did not run ({other})",
         f"{DID_NOT_RUN} ({other})"),
        ("could not run", {"review": {"could_not_run": "no subagent tool in this session"}}, "? model review: did not run",
         f"{DID_NOT_RUN}, without its reason, as reported by the model: no subagent tool in this session"),
        ("nothing found", {"sha": c["sha"], "review": {"findings": []}}, "✓ model review: nothing found",
         "\nreview: the dialog showed the user that the model review found nothing, as reported by the model"),
    ]:
        p = Peer("取消")
        r = server.install(p, {**skill, "dialog": ZH, **a}, meta)
        check(f"H14 {case} -> one line of kirby's, Install offered", f"\n{want}\n" in p.asked[0][0]
              and "subagent" not in p.asked[0][0] and p.asked[0][1] == ZH["options"] and r.endswith(note), r)
    p = Peer("取消")
    server.install(p, {**skill, "dialog": {**ZH, "lang": "zh-TW"}, "sha": "f" * 40, "review": {"findings": []}}, meta)
    check("H14 with zh-TW kirby's reason is in 繁體中文",
          f"\n？ 模型審查：未執行（它讀的是 fffffff，不是這裡檢查的 {c['sha'][:7]}）\n" in p.asked[0][0], p.asked[0][0])
    p = Peer()
    r = server.install(p, {**skill, "dialog": ZH, "sha": c["sha"], "review": {"findings": [{**finding, "reason": "x" * 121}]}}, meta)
    check("H14 a reason over 120 characters -> refused, no dialog", not p.asked and r == (
        "not installed: review.findings[0].reason must be one sentence of at most 120 characters; call this tool again "
        "with review as the inhale skill describes."), r)

    # H13: a known-malicious dependency blocks: the dialog shows the lookups and offers no Install, and the
    # result tells the model why. A lodash with a high advisory is danger but blocks nothing by itself.
    subprocess.run([sys.executable, "-I", str(Path(__file__).parent / "fixture.py"), "malware", str(fx)],
                   check=True, capture_output=True)
    shutil.rmtree(project / ".agents", ignore_errors=True)
    c = preview(project)
    name, version = fixture.MALWARE
    # The block line, then each danger finding on a line of its own with its ids (#26).
    check("H13 lookups found the malicious package and the advisory", c["blocked"] is True and c["lines"][:2] == [
        "✕ blocked: the malware lookup found a known-malicious package, so Install is not offered",
        f"✕ danger: {name}@{version} (npm) is listed as malicious (MAL-2025-20690)",
    ] and any(l.startswith("✕ danger: lodash@4.17.20 (npm) has ") for l in c["lines"])
      and "dependencies: package-lock.json: 2 npm" in c["lines"], c["lines"])
    p = Peer("取消")
    server.install(p, {**skill, "dialog": {**ZH, "lang": "zh-TW"}}, meta)
    check("H13 zh-TW: the block and danger lines in 繁體中文, ids as they are",
          "\n✕ 已擋下：惡意套件查詢找到已知的惡意套件，所以不提供安裝\n"
          f"✕ 危險：{name}@{version} (npm) 被列為惡意套件（MAL-2025-20690）\n" in p.asked[0][0]
          and "\n✕ 危險：lodash@4.17.20 (npm) 有 " in p.asked[0][0], p.asked[0][0])
    # Install is not offered, so no model review is asked for (docs/adr/0002).
    check("H13 a blocked install needs no model review", c["review"]["needed"] is False, c["review"])
    for answer, start in [("取消", "not installed: the user cancelled."),
                          ("先讀 README", "not installed: the user wants to read the README first.")]:
        p = Peer(answer)
        r = server.install(p, {**skill, "dialog": ZH}, meta)
        q, opts = p.asked[0]
        check(f"H13 {answer!r}: no Install, result says why", opts == ZH["options"][:3]
              and "\n".join(c["lines"]) in q and r.startswith(start) and r.endswith("\n" + c["note"])
              and f"\nblocked: the dialog did not offer Install, because the malware lookup lists {name}@{version} (npm) "
                  "as known-malicious." in r and "model review" not in q + r and len(p.asked) == 1, f"{opts}\n      {r}")
    check("H13 nothing written", not (project / ".agents").exists())

    print(f"\n{'all passed' if not failures else f'{len(failures)} failed: ' + ', '.join(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
