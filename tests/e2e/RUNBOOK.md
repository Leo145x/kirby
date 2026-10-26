# kirby end-to-end runbook (herdr)

A Claude Code session running inside herdr follows this file to drive Claude Code and Codex in panes
beside it, exercise every kirby feature, and check each output against what the code produces. The
unit tests (`python3 -m unittest discover -s tests`, `claude plugin test .`) cover the pure parts;
this covers the dialogs, the installs and what the model does with the results.

Helpers in this folder:

| File | Does |
| --- | --- |
| `transcript.py` | Prints a session's user prompts, model text and tool calls with their results as JSON lines, from Claude Code's or Codex's own transcript. `--tool install --last 1`, `--say --last 1` narrow it. |
| `fixture.py` | `init DIR` builds a local stand-in for `cloudflare/security-audit-skill`: the repo at a fixed commit plus files that hit all 12 scan rules (one with a zero-width space in its name), and `DIR/env.sh`, which points git at it; `advance DIR` adds a commit to it. |
| `codex_server.py` | Drives the Codex MCP server's `install()` and `file()` with scripted dialog answers and checks each result exactly (H1–H12), for what the Codex UI cannot reach. |
| `scripts_check.py` | Checks the output format of `stars.py`, `public.py` and `detect.py` against live GitHub (S1–S6). |

## Ground rules

- Run only inside herdr (`test "$HERDR_ENV" = 1`). Work only in a fresh scratch directory, called
  `$E2E` below; never in a real project.
- **This run changes the user's real Claude Code and Codex setup.** Skills at `local` and
  `project` scope land in `$E2E`, but a Claude Code MCP server at `local` scope is recorded in
  `~/.claude.json`, kirby itself is added to Codex as a marketplace and plugin, and Codex installs
  every plugin and MCP server at user scope, in `~/.codex/config.toml`. So record the
  starting state (Setup, step 2) before anything else, and compare with it at the end (Cleanup)
  even when the run stops early.
- **Cases marked (opt-in) install at user scope.** Ask the user once, before starting, whether to
  run them. Without a yes, take the case's default path: it checks the same dialogs and ends at the
  scope step with `cancel`, so nothing is installed.
- **Tool-written text is checked exactly; model-written text by criteria.** Facts in dialogs and the
  results the install tool returns come from code, so a case quotes them verbatim (with `<…>`
  placeholders). What the model writes (dialog wording, summaries) is checked against the rules the
  case lists.
- **Check results from transcripts and the file system, not the screen.** Use the screen only for the
  dialogs, which are not in the transcripts.
- Shell state does not persist between your commands: put literal values in each command.
- Something outside kirby (a permission prompt, a trust prompt, an update notice) is not a failure:
  note it and answer it as the case says, or ask the user.
- Record every case as PASS, FAIL (with the differing text) or N/A (with why), and fill the report at
  the end.

## Constants

| Name | Value |
| --- | --- |
| `KIRBY` | the repo under test (`git rev-parse --show-toplevel`) |
| `SKILL_REPO`, `SKILL_FOLDER` | `cloudflare/security-audit-skill`, `skills/security-audit` |
| `PLUGIN_REPO`, `PLUGIN`, `PLUGIN_MCP` | `anthropics/claude-plugins-official`, `agent-sdk-dev` (no MCP server), `context7` (brings an MCP server) |
| `PLUGIN_DESC` | `Development kit for working with the Claude Agent SDK` |
| `MCP_REPO`, `MCP_ARGS` | `modelcontextprotocol/servers`, `kirby-e2e -- npx -y @modelcontextprotocol/server-everything` |
| `NOT_SCANNED_PLUGIN` | `scan: not scanned; a plugin installs from its marketplace as it is when the install runs, not pinned to a commit` |
| `NOT_SCANNED_MCP` | `scan: not scanned; the server runs what this command fetches when it starts, not this repo's files` |
| `ENGLISH_NOTE` | `note: the dialogs were in English because no dialog was given; pass dialog as the inhale skill describes.` |

`PLUGIN` and the MCP name `kirby-e2e` are chosen so the run does not touch anything the user already
has: check in Setup that neither is installed. Also check that `detect.py` still reports `PLUGIN`
with `"mcpServers": false` and `PLUGIN_MCP` with `"mcpServers": true` (`python3 -I
$KIRBY/skills/inhale/scripts/detect.py anthropics/claude-plugins-official`). If not, pick others that
do and note it.

### Values to record at the start

Run in an empty scratch directory (the check looks for an existing folder in the current directory):

```
git ls-remote https://github.com/cloudflare/security-audit-skill HEAD
python3 -I $KIRBY/skills/inhale/scripts/install_skill.py cloudflare/security-audit-skill skills/security-audit --scope project --check --json
```

Record `SHA` (40 hex), `SHA7` (`commit`, equal to `SHA[:7]`), `N` (`files`), `SCRIPTS` (`scripts`),
`SCAN_LINES` (`scan_lines`) and `SCAN_NOTE` (`scan_note`). `SHA` must equal the `ls-remote` HEAD.
At the time of writing (`SHA` `c1c8a8c1471069fb0e188eeaff69b8e8db6564a8`): 20 files, 4 scripts, and

```
scan: 20 files, the ones installed; a pattern match, not a safety review
flagged: exec ×2 (validate-coverage-ledger.test.cjs:5, validate-findings.test.cjs:5)
```

`HEADER(repo)` below means `^<repo> ★\d+ · pushed \d{4}-\d{2}-\d{2}( · ARCHIVED)?$`.

## Driving the panes

These came out of running this by hand; each one cost a retest.

- **Layout.** Split once to the right for Claude Code (pane `C`), then split `C` down for Codex
  (pane `X`): `herdr pane split --current --direction right --cwd <dir> --no-focus`, then
  `herdr pane split <C> --direction down --cwd <dir> --no-focus`. Read the IDs from
  `.result.pane.pane_id`. Wait for the shell prompt before the first `pane run`.
- **Start Claude Code** with the kirby under test, from the case's project directory:
  `herdr pane run <C> "cd <P> && claude --plugin-dir $KIRBY"`. **With the fixture**, start it in a
  subshell so the git redirect does not stay in that pane's shell:
  `herdr pane run <C> "cd <P> && (. $E2E/fx/env.sh && claude --plugin-dir $KIRBY)"`.
- **Start Codex**: `herdr pane run <X> "cd <P> && codex"`. Codex loads kirby from the plugin cache
  (see Setup), not from `$KIRBY`.
- **Trust prompts** come for every new directory and can appear a few seconds after the input box
  looked ready. Claude Code: wait for `trust this folder`, send `down`, wait until the screen shows
  `❯ Yes, I trust this folder`, then `enter`. Codex: wait for `Trust and continue`, then `enter`.
  Before typing a prompt, wait about 8 seconds and read the screen again.
- **Sending a prompt.** Claude Code: `herdr agent prompt <C> "<text>" --wait --timeout 300000`.
  Codex: `herdr pane send-text <X> "<text>"`, wait until the end of the text shows on screen, then
  `herdr pane send-keys <X> enter` on its own (an Enter sent with the text is swallowed). Confirm
  the agent went `working`.
- **Never `pane run` while an agent is in the foreground**: the text becomes a prompt. Exit Claude
  Code with `/exit` (send-text, wait for it to show, Enter; `ctrl+c` does not exit it) and Codex
  with `ctrl+c ctrl+c`; wait for `claude --resume` or `Token usage` before the next `pane run`.
- **Claude Code's input box can show a suggested reply** (greyed, e.g. `好，繼續安裝`). It is not
  typed; never press Enter on an input box you did not fill.
- **Dialogs.** Claude Code numbers the options with `❯` on the selected one; Codex with `›`. The
  first option (cancel) is selected when a dialog opens. Move with `down`, then read the screen and
  check the marker is on the intended option before `enter`. `esc` dismisses. Claude Code adds
  `Type something.` and `Chat about this` below kirby's options; they are not kirby's.
- **Reading a dialog.** Panes are narrow and wrap. Zoom (`herdr pane zoom <C>`), read
  `--source visible`, zoom again to restore. Strip the leading `│ ` and join wrapped lines before
  comparing.
- **herdr's agent status** can lag or read `blocked` on a trust prompt or a dialog; trust the screen.
  `agent read --lines` fails while an agent is blocked; use `--source visible`.

## Setup

1. `test "$HERDR_ENV" = 1`; `gh auth status`; record `claude --version`, `codex --version`,
   `herdr --version` and `git -C $KIRBY rev-parse HEAD`.
2. **Record the starting state** in `$E2E/before/` (save command output with a file tool; copy
   files with `cp`). Run the commands from `$E2E`:
   - `claude plugin list`, `claude plugin marketplace list`, `claude mcp list`
   - `codex mcp list`, `codex plugin marketplace list`
   - `ls -A ~/.claude/skills ~/.agents/skills`
   - `cp ~/.claude/settings.json $E2E/before/claude-settings.json`;
     `cp ~/.codex/config.toml $E2E/before/codex-config.toml`

   Then check nothing the run would add is already there: no `security-audit` in either skills
   folder; no `agent-sdk-dev`, `context7` or `kirby-e2e` in the lists; no `kirby` marketplace in
   Codex. Anything present: note it and skip the cases that would install or remove it.
3. Make the projects, each its own git repo: `$E2E/claude/p`, `$E2E/codex/p`, `$E2E/codex/h`, and
   later ones as the cases say (`git init -q <dir>`).
4. Build the fixture: `python3 -I $KIRBY/tests/e2e/fixture.py init $E2E/fx`. Record `FX_SHA`.
5. Load kirby into Codex: `codex plugin marketplace add $KIRBY`, `codex plugin add kirby@kirby`.
   Check the cache has this checkout: `diff -rq $KIRBY/codex ~/.codex/plugins/cache/kirby/kirby/0.1.0/codex`
   (only `__pycache__` may differ). After any change to kirby, remove and add it again.
6. Open the panes (Driving the panes).

To reset a project between cases: `git -C <P> clean -fdxq` (removes `.claude/`, `.agents/` and
`.gitignore` changes a case made).

**If the run stops early** (an error, the user stops it, the session ends), go straight to Cleanup
before anything else; it lists every place a case can leave something behind.

## A. Without panes

| ID | Run | Expect |
| --- | --- | --- |
| A1 | `python3 -m unittest discover -s tests` in `$KIRBY` | ends with `OK` |
| A2 | `claude plugin test $KIRBY` | `0 fail` |
| A3 | `claude plugin validate $KIRBY` | `✔ Validation passed with warnings`; the warnings are only `ICON_MISSING` and the marketplace's missing `description` |
| A4 | from `$KIRBY`: `printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"elicitation":{}}}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \| python3 -B ./codex/server.py` (not `-I`: the server imports `dialog` from its folder) | id 1: `serverInfo` `{"name": "kirby", "version": "0.1.0"}`; id 2: tool names exactly `stars, public, detect, readme, file, install` |
| A5 | `install_skill.py` with `--commit abc` | exits non-zero with `--commit needs a full 40-character sha: 'abc'` before cloning |
| A6 | in an empty dir: `install_skill.py cloudflare/security-audit-skill skills/nope --scope project --check --json` | exit 1, `cloudflare/security-audit-skill:skills/nope has no SKILL.md` |
| A7 | in a dir with `.claude/skills/security-audit/`: `install_skill.py … --scope local --commit <SHA>` | exit 1, `.claude/skills/security-audit already exists; pass --force to replace it` |
| A8 | in an empty dir, in one command: `(. $E2E/fx/env.sh && python3 -I $KIRBY/skills/inhale/scripts/install_skill.py … --scope project --check --json)` | `sha` = `FX_SHA`; `files` = `N + 3`; `scan_lines` = FLAGGED (below); `scan_note` has the 15 hit lines of FLAGGED_NOTE (below) |
| A9 | `python3 -I $KIRBY/tests/e2e/codex_server.py $E2E/fx $E2E/codex/h` (the server's log lines on stderr are expected) | every line `PASS`, last line `all passed`, exit 0. H6 adds a commit to the fixture: record the new HEAD as `FX_SHA` (`git -C $E2E/fx/upstream.git rev-parse HEAD`) |
| A10 | `python3 -I $KIRBY/tests/e2e/scripts_check.py` | every line `PASS`, last line `all passed`, exit 0 |

What A9 covers, against the Codex server with scripted answers: H1 the dialog's facts and scan lines,
English options and `ENGLISH_NOTE`, all 12 rules fired, the zero-width name shown as `we?ird.py`;
H2 the model's wording and the README / pick another / dismiss results; H3 unusable wording falls
back to English with the reason; H4 cancel and dismiss at the scope step; H5 no project from Codex
offers only `user`, with the reason; H6 a commit pushed while the scope dialog is open installs
nothing; H7 a local install records the shown commit and adds the folder to `.gitignore`; H8 the
`exists:` line, failure without `force`, replacement with it, `project` leaving `.gitignore` alone;
H9 a plugin's facts and `NOT_SCANNED_PLUGIN`; H10 an MCP server's command and `NOT_SCANNED_MCP`;
H11 the refusals before any dialog and a client without elicitation; H12 the `file` tool reading a
flagged line at the scanned commit and refusing `..`, an absolute path and a branch name. It
installs nothing outside `$E2E/codex/h`: its plugin and MCP cases cancel at the scope step.

FLAGGED, the scan lines for the fixture (the dialog shows these; the `exec` hits in `validate-*` follow
the upstream files at the fixed commit):

```
scan: <N+3> files, the ones installed; a pattern match, not a safety review
flagged: injection-phrase ×1 (E2E-NOTES.md:2)
flagged: html-comment ×1 (E2E-NOTES.md:2)
flagged: broad-tools ×1 (E2E-NOTES.md:3)
flagged: hidden-unicode ×1 (E2E-NOTES.md:4)
flagged: agent-config ×1 (E2E-NOTES.md:5)
flagged: long-base64 ×1 (E2E-NOTES.md:6)
flagged also: network ×1, exec ×4, env-secret ×1, credentials ×1, startup-files ×1, decode ×1
```

FLAGGED_NOTE, the scan block in every result for the fixture (`<FX_SHA>` is the commit the dialog
showed):

```
scan: the dialog showed the user these pattern hits in cloudflare/security-audit-skill at commit <FX_SHA>:
  injection-phrase skills/security-audit/E2E-NOTES.md:2
  html-comment skills/security-audit/E2E-NOTES.md:2
  broad-tools skills/security-audit/E2E-NOTES.md:3
  hidden-unicode skills/security-audit/E2E-NOTES.md:4
  agent-config skills/security-audit/E2E-NOTES.md:5
  long-base64 skills/security-audit/E2E-NOTES.md:6
  network skills/security-audit/e2e-setup.sh:3
  exec skills/security-audit/e2e-setup.sh:3
  env-secret skills/security-audit/e2e-setup.sh:4
  credentials skills/security-audit/e2e-setup.sh:5
  startup-files skills/security-audit/e2e-setup.sh:6
  decode skills/security-audit/e2e-setup.sh:7
  exec skills/security-audit/validate-coverage-ledger.test.cjs:5
  exec skills/security-audit/validate-findings.test.cjs:5
  exec skills/security-audit/we?ird.py:1
```

## B. Claude Code (pane C)

Project `$E2E/claude/p` unless a case says otherwise. Start one session for B1–B15, restart it for
B16 (fixture), and once more after B16.

Check each install result with `python3 -I $KIRBY/tests/e2e/transcript.py claude <P> --tool install --last 1`
and what the model wrote with `--say --last 1`.

### Search

**B1 Stars, default source, slash command.** Prompt `/kirby:inhale 從我的 star 找能做安全審查的 skill`.
- Transcript: a `Bash` call running `python3 -I …/scripts/stars.py` (with `--match`, `--list` or
  nothing); no `mcp__kirby__install` call.
- Reply: every repo mentioned starts with a line matching `HEADER(repo)`, whose numbers equal the
  `stars.py` line or `detect.py` `header` for it in the transcript; each recommendation has a source
  tag (`[★ <list>]` or `[★ starred]`), its kind, what it would install, and flags code it runs; the
  turn ends waiting for a choice. If nothing fits, it says so and offers a public search without
  running one.

**B2 Public search.** Prompt `從公開的 GitHub 找能查 Postgres 的 MCP server`.
- Transcript: a `public.py` call; no install call.
- Reply: as B1, with `[public]` tags and a plain statement that the user has not vetted these repos.

### Skill installs

Dialog 1 for `SKILL_REPO` (facts, verbatim):

```
HEADER(cloudflare/security-audit-skill)
skill: security-audit · commit <SHA7> · <N> files
scripts: <len(SCRIPTS)>, e.g. <SCRIPTS[0]>, <SCRIPTS[1]>
<SCAN_LINES, one per line>
```

then, after a blank line, the model's `about` (if any), a blank line and its `next` question; four
options in the user's language meaning cancel, read the README first, pick another, install. Dialog 2:
the model's scope question; options `cancel`, `local`, `project`, `user`.

Model-written rules for every install: the wording is in the prompt's language (Traditional Chinese
here); `about`, if present, never says the repo is safe, checked or reviewed; the scope question does
not explain the scopes.

**B3 Install at local.** Prompt `用 kirby 安裝 cloudflare/security-audit-skill 的 security-audit skill（folder 是 skills/security-audit）`.
Answer Install, then `local`.
- Dialogs as above.
- Result, in order:
  - `installed (scope local): python3 -I <KIRBY>/skills/inhale/scripts/install_skill.py cloudflare/security-audit-skill skills/security-audit --scope local --commit <SHA>`
  - `installed cloudflare/security-audit-skill:skills/security-audit@<SHA7> -> .claude/skills/security-audit (<N> files)`
  - `  top level: …` and `  contains <len(SCRIPTS)> script(s) the skill may run: …`
  - `added /.claude/skills/security-audit/ to .gitignore`
  - `next: if it does not show up in the / menu, start a new session.`
  - `next: If it does not show up in the / menu, the user starts a new session.`
  - `SCAN_NOTE`; no `note:` line
- Screen: the call's row is one line, `● kirby install cloudflare/security-audit-skill (skill security-audit)`, and its
  result one line, `⎿  installed (scope local) -> .claude/skills/security-audit (<N> files)`; ctrl+o shows the input and result in full.
- Files: `<P>/.claude/skills/security-audit/.kirby.json` has `"commit": "<SHA>"`; `<P>/.gitignore` has
  the line `/.claude/skills/security-audit/`.
- Reply: says what was added and where, the `next:` line, and that removing it means deleting the folder.

**B4 Existing folder.** Same session and project; same prompt. Answer Install, `local`.
- Dialog 1 gains, after the scripts line: `exists: .claude/skills/security-audit/ (installing at local or project fails)`.
- Result starts `install failed (scope local): ` and holds `.claude/skills/security-audit already exists; pass --force to replace it`, then `SCAN_NOTE`.
- Reply shows the failure; no second install call with `force` unless the user asks.

**B5 Force.** Reply `取代現有的資料夾`. Answer Install, `local`.
- The install call has `"force": true`; dialog 1 shows `(installing at local or project replaces it)`.
- Result starts `installed (scope local): ` and its command ends `--commit <SHA> --force`.
- `.kirby.json` was rewritten (newer mtime than in B3).

**B6 Project scope.** Reset the project. Prompt as B3; answer Install, `project`.
- Result `installed (scope project): …--scope project --commit <SHA>`; no `added … to .gitignore` line; `.gitignore` unchanged.

**B7 User scope (opt-in).** Only if `~/.claude/skills/security-audit` is absent. Prompt as B3; answer Install.
- Opted in: answer `user`. Result `installed (scope user): …` with `-> <HOME>/.claude/skills/security-audit (<N> files)`.
  Then at once: `rm -rf ~/.claude/skills/security-audit` and check it is gone.
- Not opted in: answer `cancel`. Result `not installed: the user cancelled at the scope step.` + `SCAN_NOTE`;
  `~/.claude/skills/security-audit` still absent.

### The other answers

Reset the project before each; prompt as B3.

**B8 Read the README first.** Answer `Read README first` (option 2).
- Result exactly: `not installed: the user wants to read the README first. Summarise it for them (gh api repos/cloudflare/security-audit-skill/readme -H 'Accept: application/vnd.github.raw') and end your turn. Call this tool again only after they reply that they still want it.` then `SCAN_NOTE`.
- Transcript: a `gh api repos/cloudflare/security-audit-skill/readme` call; no further install call in the turn.
- Reply: a README summary that also lists each hit in `SCAN_NOTE` with the commit, offers to explain them, and ends the turn.

**B9 Explain a hit.** Right after B8, prompt `validate-findings.test.cjs 第 5 行在做什麼？`.
- Transcript: a `Bash` call with `gh api 'repos/cloudflare/security-audit-skill/contents/skills/security-audit/validate-findings.test.cjs?ref=<SHA>'` (the scanned commit, not a branch). If Claude Code asks permission for it, approve and note it (expected unless the mode allows it).
- Reply: quotes or describes line 5 of that file at `<SHA>` (fetch it yourself to compare); describes what the code does; gives no verdict that it is safe or malicious.

**B10 Pick another.** Answer option 3. Result exactly `not installed: the user wants a different one. Ask which of the other recommendations to look at.` + `SCAN_NOTE`. Reply asks which other one; no install call.

**B11 Cancel.** Answer option 1. Result `not installed: the user cancelled.` + `SCAN_NOTE`. The model stops.

**B12 Dismiss.** Press `esc` on dialog 1. Result `not installed: the user dismissed the dialog.` + `SCAN_NOTE`.

**B13 Free text.** On dialog 1 choose `Type something.` and enter `稍後再說`. Result `not installed: the user answered "稍後再說".` + `SCAN_NOTE`.

**B14 Scope step.** Answer Install, then option 1 (`cancel`): `not installed: the user cancelled at the scope step.` + `SCAN_NOTE`. Again with `esc` on dialog 2: `not installed: the user dismissed the scope dialog.` + `SCAN_NOTE`. Nothing written either time.

**B15 English fallback.** Prompt `直接呼叫 mcp__kirby__install 安裝 cloudflare/security-audit-skill（kind skill，folder skills/security-audit），不要傳 dialog 參數，也不要先載入 skill。` Answer Cancel.
- Dialog 1 ends `What next?`, options `Cancel`, `Read README first`, `Pick another`, `Install`.
- Result `not installed: the user cancelled.`, `SCAN_NOTE`, then `ENGLISH_NOTE`. If the model loads the skill and passes `dialog` anyway, mark N/A.

### Fixture: flagged files and a repo that moves on

**B16 Flagged scan, then the repo moves on.** New project `$E2E/claude/fx`; start Claude Code with the
fixture (subshell, Driving the panes). Prompt as B3. Record `FX_SHA` again (`git -C $E2E/fx/upstream.git rev-parse HEAD`).
- Dialog 1: the header is still GitHub's; `skill: security-audit · commit <FX_SHA7> · <N+3> files`;
  the scripts line counts the fixture's `e2e-setup.sh` and `we?ird.py` too; the scan lines are
  FLAGGED; no zero-width character anywhere in the dialog.
- Answer Install. While dialog 2 is open, run `python3 -I $KIRBY/tests/e2e/fixture.py advance $E2E/fx`
  (prints `NEW`). Answer `local`.
- Result starts `install failed (scope local): ` and holds `--commit <FX_SHA>` and
  `cloudflare/security-audit-skill has moved on: HEAD is now <NEW7>, not <FX_SHA7> as shown to the user; nothing installed`,
  then FLAGGED_NOTE for `<FX_SHA>`.
- No `.claude/` in the project. Reply says nothing was installed and why, and asks before trying
  again; no second install call in the turn.
- Exit this session; the next ones start without the fixture.

### Plugins and MCP servers

**B17 Plugin without an MCP server.** Reset `$E2E/claude/p`. Prompt `用 kirby 安裝 anthropics/claude-plugins-official 裡的 agent-sdk-dev plugin`.
- Dialog 1 facts: `HEADER(anthropics/claude-plugins-official)`, `plugin: agent-sdk-dev`,
  `description: <PLUGIN_DESC>`, `NOT_SCANNED_PLUGIN`. Dialog 2: no `prompt cache:` line.
- Answer Install, `local`. Result first line exactly
  `installed (scope local): claude plugin install agent-sdk-dev --marketplace anthropics/claude-plugins-official --scope local`,
  then the command's output, `next: The user runs /reload-plugins to load it. The marketplace itself is recorded in their user settings.`, then `NOT_SCANNED_PLUGIN`.
- `claude plugin list` run in the project shows `agent-sdk-dev@claude-plugins-official` at scope local.
- Reply: what was added, the `next:` line, removal with `claude plugin uninstall agent-sdk-dev --scope local` (or with `@claude-plugins-official`).
- Cleanup at once, in the project: `claude plugin uninstall agent-sdk-dev@claude-plugins-official --scope local`;
  `claude plugin list` no longer shows it.

**B18 Plugin with an MCP server.** Prompt as B17 with `context7`. Answer Install.
- Dialog 2 ends with a blank line and `prompt cache: this plugin brings an MCP server; if tool search is off in this session, loading it with /reload-plugins rebuilds the cache once.`
  (If the pane's environment has `ENABLE_TOOL_SEARCH=false`: `prompt cache: this plugin brings an MCP server; ENABLE_TOOL_SEARCH=false is set, so loading it with /reload-plugins rebuilds the cache once.`)
- Answer `cancel`: `not installed: the user cancelled at the scope step.` + `NOT_SCANNED_PLUGIN`.

**B19 MCP server.** Prompt `用 kirby 安裝 modelcontextprotocol/servers 的 Everything MCP server，名稱用 kirby-e2e`.
- Transcript: the README is read first (`gh api repos/modelcontextprotocol/servers/readme`); the install call has `"mcp_args": ["kirby-e2e", "--", "npx", "-y", "@modelcontextprotocol/server-everything"]` (other names or flags: note them and adapt the expectations and the cleanup).
- Dialog 1 facts: `HEADER(modelcontextprotocol/servers)`, `MCP server: claude mcp add --scope <scope> kirby-e2e -- npx -y @modelcontextprotocol/server-everything`, `NOT_SCANNED_MCP`. The model's `about` says it takes effect after a restart and does not affect this session's prompt cache.
- Answer Install, `local`. Result first line exactly
  `installed (scope local): claude mcp add --scope local kirby-e2e -- npx -y @modelcontextprotocol/server-everything`,
  then the command's output, `next: The server connects in the next session; tell the user to restart Claude Code to use it.`, `NOT_SCANNED_MCP`.
- `claude mcp get kirby-e2e` in the project shows it with local scope.
- Cleanup at once, in the project: `claude mcp remove --scope local kirby-e2e`; `claude mcp get kirby-e2e` no longer finds it.

### Refused before any dialog

No dialog may open in these; each result is exact (plus `ENGLISH_NOTE` when the call had no `dialog`).

**B20** Prompt `用 kirby 安裝 cloudflare/security-audit-skill 的 skill，folder 是 skills/nope`: `not installed: cloudflare/security-audit-skill:skills/nope has no SKILL.md`. (If the model runs `detect.py` first and declines to call install, mark N/A.)

**B21** Prompt `用 kirby 安裝 anthropics/claude-plugins-official 的 nope-not-a-plugin plugin，直接呼叫 install`: `not installed: anthropics/claude-plugins-official has no marketplace plugin named nope-not-a-plugin`.

**B22** Prompt `呼叫 mcp__kirby__install，kind mcp，repo modelcontextprotocol/servers，mcp_args 為 ["kirby-e2e", "--scope", "user", "--", "npx", "-y", "@modelcontextprotocol/server-everything"]，這是測試`: `not installed: mcp_args must not set the scope; the user picks it`. The skill tells the model never to pass a scope; if it refuses or drops `--scope`, mark N/A and note what it did.

## C. Codex (pane X)

Project `$E2E/codex/p` unless a case says otherwise. Check results with
`python3 -I $KIRBY/tests/e2e/transcript.py codex <P> --tool install --last 1`; Codex's MCP calls appear
as `mcp__kirby__<tool>`.

Differences from Claude Code to expect: searches and reads are MCP calls (`mcp__kirby__stars`,
`…public`, `…detect`, `…readme`, `…file`), not shell; skills go to `.agents/skills/`; plugins and MCP
servers offer only `user`; dialog 1 for a plugin from a Claude Code marketplace adds
`marketplace: .claude-plugin/marketplace.json (Claude Code format)`; the install command is run with
the server's own Python (`<PY>`, e.g. `/usr/bin/python3`) from the plugin cache (`<CACHE>` =
`~/.codex/plugins/cache/kirby/kirby/0.1.0`); a refusal before any dialog (`not installed: <reason>`)
carries no `note:` line, as Codex reads `dialog` only after the preview; and free text is not an
answer Codex's dialogs offer, so there is no `answered "…"` result.

**C1 Stars.** Prompt `用 kirby 從我的 star 找能做安全審查的 skill`. As B1, with an `mcp__kirby__stars` call and no shell `gh` or `python3` call.

**C2 Public.** Prompt `用 kirby 從公開的 GitHub 找能查 Postgres 的 MCP server`. As B2, with `mcp__kirby__public`.

**C3 Skill at local.** Prompt `用 kirby 安裝 cloudflare/security-audit-skill 裡的 security-audit skill（folder 是 skills/security-audit）。`
- Dialog 1 facts as for Claude Code. Dialog 2 options `cancel`, `local`, `project`, `user`.
- Answer Install, `local`. Result, in order:
  - `installed (scope local): <PY> -I <CACHE>/skills/inhale/scripts/install_skill.py cloudflare/security-audit-skill skills/security-audit --scope local --agent codex --commit <SHA>`
  - `installed cloudflare/security-audit-skill:skills/security-audit@<SHA7> -> .agents/skills/security-audit (<N> files)`, the top level and scripts lines
  - `added /.agents/skills/security-audit/ to .gitignore`
  - `next: if Codex does not list it, start a new session.`
  - `SCAN_NOTE`; no `note:` line
- Files: `.agents/skills/security-audit/.kirby.json` has `"commit": "<SHA>"`; `.gitignore` has `/.agents/skills/security-audit/`.

**C4 Existing folder.** Same prompt again. Dialog 1 adds `exists: .agents/skills/security-audit/ (installing at local or project fails)`; answer Install, `local`: `install failed (scope local): …` with `.agents/skills/security-audit already exists; pass --force to replace it`, then `SCAN_NOTE`.

**C5 Read the README first.** Reset; prompt as C3; answer option 2.
- Result exactly `not installed: the user wants to read the README first. Summarise it for them (the readme tool) and end your turn. Call this tool again only after they reply that they still want it.` + `SCAN_NOTE`.
- Transcript: `mcp__kirby__readme` with `{"repo": "cloudflare/security-audit-skill"}`. Reply as B8.

**C6 Explain a hit.** Prompt `validate-findings.test.cjs 第 5 行在做什麼？`.
- Transcript: `mcp__kirby__file` with `{"repo": "cloudflare/security-audit-skill", "path": "skills/security-audit/validate-findings.test.cjs", "ref": "<SHA>"}`; no shell `gh api`.
- Reply as B9.

**C7 The other answers.** Prompt as C3 each time:
option 3 → `not installed: the user wants a different one. Ask which of the other recommendations to look at.`;
option 1 → `not installed: the user cancelled.`;
`esc` on dialog 1 → `not installed: the user dismissed the dialog.`;
Install then `cancel` → `not installed: the user cancelled at the scope step.`;
Install then `esc` → `not installed: the user dismissed the scope dialog.`
Each followed by `SCAN_NOTE`; nothing written.

**C8 Plugin (opt-in).** Prompt `用 kirby 安裝 anthropics/claude-plugins-official 裡的 agent-sdk-dev plugin`.
- Dialog 1 facts: `HEADER(anthropics/claude-plugins-official)`, `plugin: agent-sdk-dev`, `description: <PLUGIN_DESC>`, `marketplace: .claude-plugin/marketplace.json (Claude Code format)`, `NOT_SCANNED_PLUGIN`. The model's `about` says parts made only for Claude Code (such as hooks) may not work in Codex. Dialog 2 options `cancel`, `user`.
- Not opted in: answer Install, `cancel`. Result `not installed: the user cancelled at the scope step.` + `NOT_SCANNED_PLUGIN`; `~/.codex/config.toml` unchanged.
- Opted in: answer Install, `user`. Result starts
  `installed (scope user): codex plugin marketplace add anthropics/claude-plugins-official` then a line `codex plugin add agent-sdk-dev@claude-plugins-official`, the two commands' output, `next: The user starts a new Codex session to use it.`, `NOT_SCANNED_PLUGIN`.
  `~/.codex/config.toml` gains `[plugins."agent-sdk-dev@claude-plugins-official"]` and `[marketplaces.claude-plugins-official]`.
  Cleanup at once: `codex plugin remove agent-sdk-dev@claude-plugins-official`; `codex plugin marketplace remove claude-plugins-official` (only if Setup found no such marketplace).

**C9 MCP server (opt-in).** Prompt `用 kirby 安裝 modelcontextprotocol/servers 的 Everything MCP server，名稱用 kirby-e2e`.
- Transcript: `mcp__kirby__readme` first; install with `"mcp_args": ["kirby-e2e", "--", "npx", "-y", "@modelcontextprotocol/server-everything"]`.
- Dialog 1 facts: header, `MCP server: codex mcp add kirby-e2e -- npx -y @modelcontextprotocol/server-everything`, `NOT_SCANNED_MCP`. Dialog 2 options `cancel`, `user`.
- Not opted in: answer Install, `cancel`. Result `not installed: the user cancelled at the scope step.` + `NOT_SCANNED_MCP`; `codex mcp list` unchanged.
- Opted in: answer Install, `user`. Result first line exactly `installed (scope user): codex mcp add kirby-e2e -- npx -y @modelcontextprotocol/server-everything`, then output, `next: The user starts a new Codex session to use it.`, `NOT_SCANNED_MCP`.
  `codex mcp get kirby-e2e` shows it. Cleanup at once: `codex mcp remove kirby-e2e`.

**C10 English fallback.** Prompt `直接呼叫 kirby 的 install tool 安裝 cloudflare/security-audit-skill（kind skill，folder skills/security-audit），不要傳 dialog 參數。` Answer Cancel. Dialog 1 ends `What next?` with options `Cancel`, `Read README first`, `Pick another`, `Install`; result ends `ENGLISH_NOTE`. N/A if the model passes `dialog` anyway.

**C11 Built-in installer (observe only).** In a fresh project, prompt `install cloudflare/security-audit-skill` (no mention of kirby). Record whether Codex goes through `mcp__kirby__install` or offers its built-in `skill-installer`; decline the latter. This checks the README's warning still holds; neither outcome fails.

A9 covers, through `codex_server.py`, what the Codex UI cannot: the fixture (Codex does not pass
`GIT_CONFIG_*` to its MCP server), a commit pushed while a dialog is open, a session with no project,
a client without elicitation, and unusable dialog wording.

## Cleanup

Run all of it, also after a run that stopped early.

1. Exit both agents; close panes `C` and `X` (`herdr pane close <id>`).
2. Remove what the cases may have added, and check each is gone:
   - `~/.claude/skills/security-audit`, `~/.agents/skills/security-audit` (only if Setup found them absent)
   - in `$E2E/claude/p`: `claude plugin uninstall agent-sdk-dev@claude-plugins-official --scope local` and
     `claude mcp remove --scope local kirby-e2e`, if `claude plugin list` / `claude mcp list` there still show them
   - `codex plugin remove agent-sdk-dev@claude-plugins-official`, `codex mcp remove kirby-e2e`, and
     `codex plugin marketplace remove claude-plugins-official` if Setup did not have it
   - `codex plugin remove kirby@kirby`; `codex plugin marketplace remove kirby`; remove `~/.codex/plugins/cache/kirby` if left empty
3. **Compare with the starting state**: run the commands of Setup step 2 again from `$E2E` and diff
   each against `$E2E/before/`; `diff $E2E/before/claude-settings.json ~/.claude/settings.json`;
   `diff $E2E/before/codex-config.toml ~/.codex/config.toml`. Codex adds a `[projects."<dir>"]`
   trust entry for each test directory; remove only those. Anything else that differs: report it,
   do not revert it.
4. `git -C $KIRBY status --short` is clean (the run must not touch the repo).

## Report

| ID | Result | Evidence (differing text, transcript line, or why N/A) |
| --- | --- | --- |
| A1 | | |
| … | | |

Above the table: date, `git -C $KIRBY rev-parse HEAD`, the tool versions from Setup, `SHA`, `FX_SHA`,
whether the opt-in cases ran, every deviation from this runbook, and the result of Cleanup step 3.
