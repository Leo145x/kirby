#!/usr/bin/env python3
"""Drive the Codex MCP server's install tool with scripted dialog answers, for the Codex cases the
Codex UI cannot reach: a fixture repo (Codex does not pass GIT_CONFIG_* to the server), a repo moving
on while the scope dialog is open, a session with no project, and a client without elicitation.

    codex_harness.py --answers Install,local --project DIR '{"repo": …, "kind": "skill", "folder": …}'
    codex_harness.py --answers Install,local --project DIR --advance FIXTURE '<args>'
    codex_harness.py --answers Install,user --no-project '<args>'
    codex_harness.py --no-elicit '<args>'

--answers lists one answer per dialog, by option label; `-` dismisses the dialog. --advance runs
`fixture.py advance FIXTURE` just before answering the second dialog. Prints each dialog, then the
tool's result after a `--- result ---` line.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "codex"))
import server  # noqa: E402


class ScriptedPeer:
    def __init__(self, answers, elicit, advance):
        self.answers, self.can_elicit, self.advance, self.asked = list(answers), elicit, advance, 0

    def ask(self, question, options):
        self.asked += 1
        print(f"--- dialog {self.asked} ---\n{question}\noptions: {json.dumps(options, ensure_ascii=False)}")
        if self.asked == 2 and self.advance:
            sha = subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("fixture.py")), "advance",
                                  self.advance], capture_output=True, text=True, check=True).stdout.strip()
            print(f"(fixture advanced to {sha})")
        if not self.answers:
            sys.exit(f"no answer left for dialog {self.asked}")
        answer = self.answers.pop(0)
        if answer == "-":
            return None
        if answer not in options:
            sys.exit(f"{answer!r} is not an option of dialog {self.asked}")
        return answer


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("args", help="the install tool's arguments, as JSON")
    ap.add_argument("--answers", default="", help="comma-separated option labels; - dismisses")
    ap.add_argument("--project", help="the session's project directory, as Codex would name it")
    ap.add_argument("--no-project", action="store_true", help="Codex names no project")
    ap.add_argument("--no-elicit", action="store_true", help="the client cannot show dialogs")
    ap.add_argument("--advance", metavar="FIXTURE", help="advance this fixture before the second dialog's answer")
    a = ap.parse_args()
    if not a.no_project and not a.project:
        ap.error("pass --project DIR or --no-project")
    meta = None if a.no_project else {"x-codex-turn-metadata": {"workspaces": {str(Path(a.project).resolve()): {}}}}
    peer = ScriptedPeer([x for x in a.answers.split(",") if x], not a.no_elicit, a.advance)
    print("--- result ---\n" + server.install(peer, json.loads(a.args), meta))


if __name__ == "__main__":
    main()
