#!/usr/bin/env python3
"""Check the output format of the inhale scripts against live GitHub (needs a logged-in gh).

    python3 -I tests/e2e/scripts_check.py

What a search returns depends on the user's stars and on GitHub, so this checks shapes, not results.
Prints PASS or FAIL per check and exits 1 if any failed.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "skills/inhale/scripts"
HEADER = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+ ★\d+ · pushed (\d{4}-\d{2}-\d{2}|\?)( · ARCHIVED)?"
failures = []


def run(script, *args):
    res = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *args], capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr


def check(case, ok, detail: object = ""):
    print(f"{'PASS' if ok else 'FAIL'}  {case}" + (f"\n      {detail}" if not ok and detail else ""))
    if not ok:
        failures.append(case)


def main():
    code, out, err = run("stars.py", "--lists")
    lines = out.splitlines()
    check("S1 stars --lists: one line per list", code == 0 and all(
        re.fullmatch(r".+ \[[^\]]+\] \d+ repos( \(private\))?( .*)?", l) for l in lines), err or out[:300])

    code, out, err = run("stars.py", "--match", "skill", "mcp", "claude")
    lines = out.splitlines()
    check("S2 stars --match: count line", code == 0 and bool(lines) and re.fullmatch(
        r"# \d+ of \d+ repos for \S+ \(cache age \d+ min\)", lines[0]), err or out[:300])
    check("S2 stars --match: repo lines start with the header", all(
        re.match(HEADER + r"( \[[^\]]*\])? — ", l) for l in lines[1:]), "\n".join(lines[1:4]))

    code, out, err = run("stars.py", "--list", "no-such-list-kirby-e2e")
    check("S3 stars --list unknown -> names the lists", code != 0 and "no star list named 'no-such-list-kirby-e2e'" in err,
          err)

    code, out, err = run("public.py", "pdf", "--kind", "skill", "--limit", "3")
    lines = out.splitlines()
    check("S4 public: count line", code == 0 and bool(lines) and re.fullmatch(
        r"# \d+ of \d+ public repos for 'pdf' \(kind=skill, stars>=10\)", lines[0]), err or out[:300])
    check("S4 public: at most 3 repos, header + matched topics", len(lines) - 1 <= 3 and all(
        re.match(HEADER + r"( \[starred by you\])? — .* \(matched: [a-z,-]+\)$", l) for l in lines[1:]),
        "\n".join(lines[1:]))

    code, out, err = run("detect.py", "--match", "security", "--", "cloudflare/security-audit-skill",
                         "anthropics/claude-plugins-official")
    data = json.loads(out) if code == 0 else []
    check("S5 detect: header per repo", len(data) == 2 and all(re.fullmatch(HEADER, d["header"]) for d in data),
          err or out[:300])
    skill = next((u for u in data[0]["install"] if u["type"] == "skill"), {}) if data else {}
    check("S5 detect: the skill and its folder", data and "skill" in data[0]["kinds"]
          and skill.get("folder") == "skills/security-audit", skill)
    plugin = next((u for u in data[1]["install"] if u.get("name") == "agent-sdk-dev"), {}) if len(data) > 1 else {}
    check("S5 detect: a marketplace plugin without MCP", "marketplace" in data[1]["kinds"]
          and plugin.get("mcpServers") is False and plugin.get("marketplace") == "claude-plugins-official", plugin)

    code, out, err = run("detect.py", "--agent", "codex", "anthropics/claude-plugins-official")
    unit = next((u for u in json.loads(out)[0]["install"] if u.get("name") == "agent-sdk-dev"), {}) if code == 0 else {}
    check("S6 detect --agent codex: falls back to the Claude Code marketplace file",
          unit.get("marketplaceFile") == ".claude-plugin/marketplace.json", unit)

    print(f"\n{'all passed' if not failures else f'{len(failures)} failed: ' + ', '.join(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
