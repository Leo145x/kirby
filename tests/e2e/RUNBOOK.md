# kirby end-to-end runbook (herdr)

A Claude Code session running inside herdr follows this file to drive each supported agent CLI in a
pane beside it, exercise every kirby feature, and check each output against what the code produces.
The unit tests (`python3 -m unittest discover -s tests`, `claude plugin test .`) cover the pure
parts; this covers the dialogs, the installs and what the model does with the results.

The agent CLIs, one section each:

| Section | Agent CLI | Pane |
| --- | --- | --- |
| B | Claude Code | `C` |
| C | Codex | `X` |

Section A needs no pane. Which cases to run for a change: `AGENTS.md`, Before Every Commit. Open a
pane only for the agent CLIs whose cases you run.

Helpers in this folder:

| File | Does |
| --- | --- |
| `transcript.py` | Prints a session's user prompts, model text and tool calls with their results as JSON lines, from Claude Code's or Codex's own transcript. `--tool install --last 1`, `--say --last 1` narrow it. |
| `fixture.py` | `init DIR` builds a local stand-in for `cloudflare/security-audit-skill`: the repo at a fixed commit plus files that hit all 12 scan rules and the 3 combinations (one with a zero-width space in its name), and `DIR/env.sh`, which points git at it; `advance DIR` adds a commit to it; `rewind DIR` force-pushes it back one commit and prunes the old HEAD, so that commit can no longer be fetched; `malware DIR` adds a commit whose `package-lock.json` lists `flatmap-stream@0.1.1` (known-malicious, `MAL-2025-20690`) and `lodash@4.17.20` (high advisories). |
| `codex_server.py` | Drives the Codex MCP server's `install()`, `check()` and `file()` with scripted dialog answers and review results and checks each result exactly (H1–H16), for what the Codex UI cannot reach. |
| `scripts_check.py` | Checks the output format of `stars.py`, `public.py` and `detect.py` against live GitHub (S1–S6). |

## Adding an agent CLI

Give it a section after the last one, with the same parts in the same order: **Setup** (version
command, its config directory under `$E2E/home` and how its login is copied there, what its run
writes outside `$E2E`, the starting state to record, what must be absent, how kirby is loaded, its
projects), **Driving** (start, first-start screens, trust prompt, sending a prompt, exit, dialogs),
the cases, and **Cleanup**. Add it to the table above, to Isolation and to `AGENTS.md`, Before Every
Commit. The shared parts below stay as they are.

## Ground rules

- Run only inside herdr (`test "$HERDR_ENV" = 1`). Work only in a fresh scratch directory outside
  `/tmp`, called `$E2E` below (e.g. `mktemp -d ~/.cache/kirby-e2e-XXXXXX`; Codex does not set up
  its helper commands when its config directory is under `/tmp`); never in a real project.
- **Each agent CLI runs in its own config directory under `$E2E/home`**, not in the user's real
  setup (Isolation). A few things still land outside `$E2E`; each CLI's Setup lists them. So record
  the starting state (Setup, step 2) before anything else, and compare with it at the end (Cleanup)
  even when the run stops early.
- **Cases marked (opt-in) install into the user's real setup** (C8, C9). Ask the user once, before
  starting, whether to run them. Without a yes, take the case's default path: it checks the same
  dialogs and ends at the scope step with `cancel`, so nothing is installed.
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
| `PLUGIN_MK` | `claude-plugins-official`, the name of `PLUGIN_REPO`'s marketplace |
| `ENGLISH_NOTE` | `note: the dialogs were in English because no dialog was given; pass dialog as the inhale skill describes.` |
| `UNREVIEWED` | `model review: unchecked (no review result was passed)` |
| `REVIEW_BLOCK` | a result's last lines when dialog 1 showed model review lines: `review: the dialog showed the user these model review lines:`, then each of those lines indented by two spaces |
| `REVIEW_LINE` | a model review line in dialog 1, after the check's lines: `warn: <file>:<line>: <reason> (model review, as reported by the model)`, `model review: nothing found (as reported by the model)` or `model review: unchecked (<why>)` |

Constants only one agent CLI uses are in its section.

`PLUGIN` and the MCP name `kirby-e2e` are chosen so the opt-in cases, which install into the real
setup, do not touch anything the user already has: check in Setup that neither is installed. Also check that `check_plugin.py` still reports `PLUGIN`
with `"mcp_servers": false` and `PLUGIN_MCP` with `"mcp_servers": true` (Values to record, below). If not, pick others that
do and note it.

### Values to record at the start

Run in an empty scratch directory (the check looks for an existing folder in the current directory):

```
git ls-remote https://github.com/cloudflare/security-audit-skill HEAD
python3 -I $KIRBY/skills/inhale/scripts/install_skill.py cloudflare/security-audit-skill skills/security-audit --scope project --check --json
```

Record `SHA` (40 hex), `SHA7` (`commit`, equal to `SHA[:7]`), `N` (`files`), `SCRIPTS` (`scripts`),
`CHECK_LINES` (`lines`), `BLOCKED` (`blocked`, must be `false`), `review.needed` (must be `false`: its
only findings are info, so no model review runs for it; if it is now `true`, the cases below gain the review of B26, so note it)
and `SCAN_NOTE` (`note`: the `pattern scan:` block, a newline, then the `lookups:` block); every result after the dialog opens ends
with it. `SHA` must equal the `ls-remote` HEAD. The lookups ask OSV.dev and GitHub at check time, so
`CHECK_LINES` can change when a new advisory is published; record it, do not expect the values below.
At the time of writing (`SHA` `c1c8a8c1471069fb0e188eeaff69b8e8db6564a8`): 20 files, 4 scripts, and
`CHECK_LINES`:

```
✓ pattern scan: no danger or warn findings
✓ advisory and malware lookups: nothing found
```

(the check summed up by severity: the first line is the pattern scan's, which found only info findings (`exec` in the two
`validate-*.test.cjs`), the dialog leaving those out; the second is the lookups'. With no finding at all and nothing unscanned
or unchecked, `lines` is the one line `✓ check: nothing found (<n> files, <dependencies>, advisory and malware lookups)`).
Record `CHECK_ZH`, those lines in 繁體中文 (`ZH(<this run>)`, below, without its first two lines, the skill and scripts lines):
at the time of writing `✓ pattern 掃描：沒有危險或警告的發現` and `✓ 漏洞、惡意套件查詢：沒有發現`. Record also `SCAN_NOTE`:

```
pattern scan: the pattern-scan findings in cloudflare/security-audit-skill at commit <SHA> (the dialog showed the user the warn ones by name only, without files or lines, and left out the info ones):
  info exec skills/security-audit/validate-coverage-ledger.test.cjs:5
  info exec skills/security-audit/validate-findings.test.cjs:5
lookups: the dialog showed the user no findings from the advisory and malware lookups for cloudflare/security-audit-skill at commit <SHA>
dependencies: no npm or Python dependency files
```

For the plugins, also run (Claude Code reads `.claude-plugin/marketplace.json`, Codex its own first):

```
git ls-remote https://github.com/anthropics/claude-plugins-official HEAD
python3 -I $KIRBY/skills/inhale/scripts/check_plugin.py --agent claude -- anthropics/claude-plugins-official agent-sdk-dev
python3 -I $KIRBY/skills/inhale/scripts/check_plugin.py --agent claude -- anthropics/claude-plugins-official context7
python3 -I $KIRBY/skills/inhale/scripts/check_plugin.py --agent codex -- anthropics/claude-plugins-official agent-sdk-dev
```

Record `PLUGIN_SHA` (`sha`, equal to the `ls-remote` HEAD), `PLUGIN_SHA7`, and of each run its `lines`
and `note`: `PLUGIN_LINES` and `PLUGIN_NOTE` for the first, `PLUGIN_MCP_LINES` and `PLUGIN_MCP_NOTE`
for the second, `CODEX_PLUGIN_LINES` and `CODEX_PLUGIN_NOTE` for the third. `PLUGIN_LINES` starts
`plugin: agent-sdk-dev · marketplace claude-plugins-official · commit <PLUGIN_SHA7> · <n> files`,
`description: <PLUGIN_DESC>`, `source: plugins/agent-sdk-dev/ in this repo`, then its check lines (at
the time of writing the one line `✓ check: nothing found (6 files, no npm or Python dependency files, advisory and malware lookups)`,
and `PLUGIN_MCP_LINES` likewise ends with one `✓ check: nothing found (…)` line; if either now sums up the scan
and lookups by severity on several lines, note it); `PLUGIN_NOTE` is a `pattern scan:` block and a `lookups:` block for
`anthropics/claude-plugins-official at commit <PLUGIN_SHA>`. `mcp_servers` is `false` for `agent-sdk-dev`
and `true` for `context7`; `blocked` is `false` for both. The marketplace moves often, so record the
values again if a case runs much later.

Each run also gives `facts`, the dialog's lines before kirby words them (`lines` is their English). Dialog 1 shows them in
the language `dialog.lang` picks; `ZH(<run>)` below is how it shows them with `zh-TW`, one per line, from piping a run into

```
python3 -I -c 'import json, sys; sys.path.insert(0, sys.argv[1]); from words import say; print("\n".join(say(f, "zh-TW") for f in json.load(sys.stdin)["facts"]))' $KIRBY/skills/inhale/scripts
```

Record `PLUGIN_ZH`, `PLUGIN_MCP_ZH` and `CODEX_PLUGIN_ZH` this way. `PLUGIN_ZH` starts
`外掛：agent-sdk-dev · marketplace claude-plugins-official · commit <PLUGIN_SHA7> · <n> 個檔案`, `說明：<PLUGIN_DESC>`,
`來源：這個 repo 的 plugins/agent-sdk-dev/`, then the check line in 繁體中文 too: at the time of writing
`✓ 檢查：沒有發現（6 個檔案、沒有 npm 或 Python 相依套件檔、漏洞與惡意套件查詢）`.

For the MCP server, also run:

```
python3 -I $KIRBY/skills/inhale/scripts/check_mcp.py -- modelcontextprotocol/servers '["kirby-e2e", "--", "npx", "-y", "@modelcontextprotocol/server-everything"]'
```

Record `MCP_VERSION` (`package.version`), `MCP_PINNED` (`mcp_args` joined with spaces, i.e. `MCP_ARGS`
with its last word now `@modelcontextprotocol/server-everything@<MCP_VERSION>`), `MCP_LINES` (`lines`)
and `MCP_NOTE` (`note`). `MCP_LINES` starts
`package: @modelcontextprotocol/server-everything@<MCP_VERSION> (npm), named by this repo's src/everything/package.json; not verified to come from this repo`
and `pinned: only @modelcontextprotocol/server-everything, to <MCP_VERSION>; its dependencies are not pinned, so they may differ from those checked when the server starts`,
then the check of the package summed up by severity. At the time of writing (2.1.0) the scan flagged `send-secrets` and
`download-decode`, and the lookups found one repo advisory for that package, so the rest of `MCP_LINES` was
`⚠ warn (3): may send secrets out, may download and decode a payload, advisories this repo published (1)`,
`dependencies: @modelcontextprotocol/server-everything@<MCP_VERSION>: <n> npm, versions resolved at check time` and
`✓ malware lookup: nothing found`. `MCP_NOTE`
is a `pattern scan:` block for `the npm package @modelcontextprotocol/server-everything@<MCP_VERSION> (server-everything-<MCP_VERSION>.tgz)`,
a `lookups:` block, and a last line starting `package: the command runs @modelcontextprotocol/server-everything@<MCP_VERSION> (npm)`.
`blocked` is `false`. `review.needed` is `true` (the warn combinations); record `MCP_REVIEW_SHA` (`review.sha`, 64 hex, the sha256
of the archive checked). Record `MCP_ZH` (`ZH(<this run>)`, above): it starts
`套件：@modelcontextprotocol/server-everything@<MCP_VERSION>（npm），由這個 repo 的 src/everything/package.json 指名；沒有驗證它來自這個 repo`
and `已鎖定：只有 @modelcontextprotocol/server-everything，鎖定在 <MCP_VERSION>；它的相依套件沒有鎖定，server 啟動時可能和檢查過的不同`,
then the check lines in 繁體中文: at the time of writing `⚠ 警告 3 項：可能外傳密鑰、可能下載並解碼資料、這個 repo 發布的 1 則安全公告`,
`相依套件：@modelcontextprotocol/server-everything@<MCP_VERSION>：<n> 個 npm，版本是檢查當下算出的` and `✓ 惡意套件查詢：沒有發現`.
A new release changes all of these; record them again if a case runs much later. The two plugins'
`review.needed` are `false` while their check lines are one `✓ check: nothing found (…)` line.

`HEADER(repo)` below means `^<repo> ★\d+ · pushed \d{4}-\d{2}-\d{2}( · ARCHIVED)?$`, as `stars.py`, `detect.py` and an English
dialog give it. `HEADER_ZH(repo)` means `^<repo> ★\d+ · \d{4}-\d{2}-\d{2} 更新( · 已封存)?$`, as dialog 1 gives it with `dialog.lang` `zh-TW`.

The prompts below are in 繁體中文, so the install call's `dialog` has `"lang": "zh-TW"` and kirby words its own lines in dialog 1
in 繁體中文 (`hooks/words.ts`, `skills/inhale/scripts/words.py`), the pre-install check's lines among them (`ZH(<run>)` gives
them; ids, names, versions and paths stay as they are). A call without `lang` there is a FAIL. Each case's `about` is one sentence of at most 120 characters on what the tool
does, and does not repeat the findings.

## Isolation

Each agent CLI keeps its settings, installs, trust decisions and transcripts in a config directory
that an environment variable can move. The run points them into `$E2E/home`, so deleting `$E2E` at
the end removes what the run installed. Write `$E2E/iso.sh` with a file tool, with literal paths:

```
export CLAUDE_CONFIG_DIR=<E2E>/home/claude
export CODEX_HOME=<E2E>/home/codex
```

Every `claude` and `codex` command in sections B and C, every `transcript.py` call, and every agent
started in a pane runs after `. $E2E/iso.sh`, in a subshell when run from your own shell:
`(. $E2E/iso.sh && claude mcp list)`. The exceptions are said where they occur: the starting state,
the logins (below) and the comparisons in Setup and Cleanup, and the opt-in paths of C8 and C9, act
on the real setup.

What the two variables move and what they do not (tried on 2026-10-28 with Claude Code 2.1.311 and
Codex 0.164.0) is in each CLI's Setup.

### Logins

Copy each CLI's login file in; never print one. A login file holds a refresh token, and when one
copy renews its access token, the other copy's refresh token stops working. When this was tried,
the copy renewed an expired token and the real Claude Code then failed with `OAuth session expired
and could not be refreshed`. A copy renews only once its access token has expired, so copy a login
only when its access token has at least 3 more hours to run:

| CLI | Hours left (prints a number) | If under 3: renew it in the real setup, from `$E2E` | Copy |
| --- | --- | --- | --- |
| Claude Code | `python3 -I -c 'import json,os,time; c=json.load(open(os.path.expanduser("~/.claude/.credentials.json")))["claudeAiOauth"]; print(round((c["expiresAt"]/1000-time.time())/3600,1))'` | `claude -p ok` (a token lasts 8 hours) | `mkdir -p $E2E/home/claude && cp ~/.claude/.credentials.json $E2E/home/claude/` |
| Codex | `python3 -I -c 'import base64,json,os,time; t=json.load(open(os.path.expanduser("~/.codex/auth.json")))["tokens"]["access_token"].split(".")[1]; print(round((json.loads(base64.urlsafe_b64decode(t+"="*(-len(t)%4)))["exp"]-time.time())/3600,1))'` (a `KeyError: 'tokens'` means an API key login, which has no token to renew: copy it as is) | `codex exec --skip-git-repo-check ok` (a token lasted 240 hours) | `mkdir -p $E2E/home/codex && cp ~/.codex/auth.json $E2E/home/codex/` |

Check the hours again after renewing. The copies are secrets: Cleanup deletes them with `$E2E`.

**If the real login breaks anyway** (the real CLI says its session expired or asks to log in), the
copy renewed first and holds the only working token. Before deleting `$E2E`, copy it back
(`cp $E2E/home/claude/.credentials.json ~/.claude/.credentials.json`, which restored the login
when this was tried; for Codex, `auth.json` the same way, which was not tried), check the real CLI
works, and report it.

## Driving the panes

These came out of running this by hand; each one cost a retest. Each CLI's Driving adds what is
particular to it: how to start, answer the trust prompt, send a prompt, exit, and read its dialogs.

- **Layout.** One pane per agent CLI under test. Split the first one to the right
  (`herdr pane split --current --direction right --cwd <dir> --no-focus`) and each further one
  down from the one before (`herdr pane split <previous> --direction down --cwd <dir> --no-focus`).
  Read the IDs from `.result.pane.pane_id`. Wait for the shell prompt before the first `pane run`.
- **Trust prompts** come for every new directory and can appear a few seconds after the input box
  looked ready. Before typing a prompt, wait about 8 seconds and read the screen again.
- **Never `pane run` while an agent is in the foreground**: the text becomes a prompt. Exit the
  agent as its Driving says and wait for its exit text before the next `pane run`.
- **Dialogs.** The first option (cancel) is selected when a dialog opens. Move with `down`, then read
  the screen and check the marker is on the intended option before `enter`. `esc` dismisses.
- **Reading a dialog.** Panes are narrow and wrap. Zoom (`herdr pane zoom <pane>`), read
  `--source visible`, zoom again to restore. Strip the leading `│ ` and join wrapped lines before
  comparing.
- **herdr's agent status** can lag or read `blocked` on a trust prompt or a dialog; trust the screen.
  `agent read --lines` fails while an agent is blocked; use `--source visible`.

## Setup

1. `test "$HERDR_ENV" = 1`; `gh auth status`; check `$E2E` is not under `/tmp`; record
   `herdr --version`, `git -C $KIRBY rev-parse HEAD` and the version of each agent CLI under test
   (its Setup).
2. **Record the starting state of the real setup** in `$E2E/before/` (save command output with a
   file tool; copy files with `cp`). Run the commands from `$E2E`, without `iso.sh`: those in each
   CLI's Setup. Then check nothing the run would add is already there (each CLI's Setup lists it).
   Anything present: note it and skip the cases that would install or remove it.
3. **Isolate** (Isolation): write `$E2E/iso.sh`, and copy in the login of each agent CLI under test.
4. Make the projects, each its own git repo: `$E2E/codex/h` for A9, those in each CLI's Setup, and
   later ones as the cases say (`git init -q <dir>`).
5. Build the fixture: `python3 -I $KIRBY/tests/e2e/fixture.py init $E2E/fx`. Record `FX_SHA`.
6. Load kirby into each agent CLI under test, as its Setup says.
7. Open the panes (Driving the panes, and each CLI's Driving).

To reset a project between cases: `git -C <P> clean -fdxq` (removes the skill folders and
`.gitignore` changes a case made).

**If the run stops early** (an error, the user stops it, the session ends), go straight to Cleanup
before anything else; it lists every place a case can leave something behind.

## A. Without panes

`For` names the agent CLI a case checks; `both` means the scripts both use.

| ID | For | Run | Expect |
| --- | --- | --- | --- |
| A1 | both | `python3 -m unittest discover -s tests` in `$KIRBY` | ends with `OK` |
| A2 | Claude Code | `claude plugin test $KIRBY` | `0 fail` |
| A3 | Claude Code | `claude plugin validate $KIRBY` | `✔ Validation passed with warnings`; the warnings are only `ICON_MISSING`, the marketplace's missing `description`, and `CLAUDE.md at the plugin root is not loaded as project context` (that file is for working on kirby, not for those who install it) |
| A4 | Codex | from `$KIRBY`: `printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"elicitation":{}}}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \| python3 -B ./codex/server.py` (not `-I`: the server imports `dialog` from its folder) | id 1: `serverInfo` `{"name": "kirby", "version": "0.1.0"}`; id 2: tool names exactly `stars, public, detect, readme, file, check, install`; each tool's `annotations` has `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint`, all booleans: `true, false, true, true` for the six read-only tools, `false, true, false, true` for `install` |
| A5 | both | `install_skill.py` with `--commit abc` | exits non-zero with `--commit needs a full 40-character sha: 'abc'` before cloning |
| A6 | both | in an empty dir: `install_skill.py cloudflare/security-audit-skill skills/nope --scope project --check --json` | exit 1, `cloudflare/security-audit-skill:skills/nope has no SKILL.md` |
| A7 | both | in a dir with `.claude/skills/security-audit/`: `install_skill.py … --scope local --commit <SHA>` | exit 1, `.claude/skills/security-audit already exists; pass --force to replace it` |
| A8 | both | in an empty dir, in one command: `(. $E2E/fx/env.sh && python3 -I $KIRBY/skills/inhale/scripts/install_skill.py … --scope project --check --json)` | `sha` = `FX_SHA`; `files` = `N + 3`; `lines` = FLAGGED (below) followed by the last line of `CHECK_LINES` (the lookups'); `scan.combinations` = `["send-secrets", "download-run", "download-decode"]`; `note` starts with FLAGGED_NOTE's `pattern scan:` block (below: its 3 combination lines and 15 finding lines), then a `lookups:` block; no `check_lines`, `scan_note` or `lookup_note` field; `blocked` `false` |
| A9 | Codex | `python3 -I $KIRBY/tests/e2e/codex_server.py $E2E/fx $E2E/codex/h` (the server's log lines on stderr are expected) | every line `PASS`, last line `all passed`, exit 0. H6 adds a commit to the fixture and takes it away again, and H13 adds one: record the new HEAD as `FX_SHA` (`git -C $E2E/fx/upstream.git rev-parse HEAD`) |
| A17 | both | in an empty dir: the `check_mcp.py` run of Values to record (MCP server), then `check_mcp.py --read '{"ecosystem": "npm", "name": "@modelcontextprotocol/server-everything", "version": "<MCP_VERSION>", "sha": "<MCP_REVIEW_SHA>", "path": "package.json"}'`; again with `"sha"` 64 zeros; then `check_mcp.py --read 'x'` | the first prints that package's `package.json` (its `name` is `@modelcontextprotocol/server-everything`, its `version` `<MCP_VERSION>`); the second exits 1 with `the registry now gives another archive than the one checked`; the third exits 1 with `--read needs {"ecosystem": "npm" or "PyPI", "name", "version", "sha": 64 hex, "path"}`; nothing is left in the dir |
| A13 | both | in an empty dir: `install_skill.py Leo145x/kirby skills/inhale --scope project --commit d4f7a5f5dca68fb15d6a40ba63c5b8d6d643070f` (an older commit, not the tip); then the same with `--commit 0123456789abcdef0123456789abcdef01234567` in another empty dir | the first exits 0 with `installed Leo145x/kirby:skills/inhale@d4f7a5f -> .claude/skills/inhale (5 files)`, `.kirby.json` has that `commit`, and `scripts/install_skill.py` equals `git -C $KIRBY show d4f7a5f:skills/inhale/scripts/install_skill.py`; the second exits 1 with `could not fetch Leo145x/kirby at commit 0123456, the one shown to the user; nothing installed (a force-push can remove a commit). git: fatal: remote error: upload-pack: not our ref 0123456789abcdef0123456789abcdef01234567` and writes nothing |
| A14 | both | in an empty dir: `install_skill.py anthropics/skills skills/pdf --scope project --check` (a skill the check finds nothing in) | its last line is `  ✓ check: nothing found (<n> files, no npm or Python dependency files, advisory and malware lookups)`, with `<n>` the file count of its first line; no `pattern scan:`, `⚠ warn`, `dependencies:` or `… lookup…:` line. If the skill now has a finding, pick another and note it |
| A10 | both | `python3 -I $KIRBY/tests/e2e/scripts_check.py` | every line `PASS`, last line `all passed`, exit 0 |
| A11 | both | `python3 -I $KIRBY/skills/inhale/scripts/check_plugin.py -- anthropics/claude-plugins-official 42crunch-api-security-testing` (a source in another repo, pinned by its entry) | exit 0; `lines[2]` matches `^source: 42Crunch-AI/claude-plugins:plugins/api-security-testing at commit [0-9a-f]{7}, pinned by the marketplace entry$`; `source.commit` equals the entry's `sha` (`gh api repos/anthropics/claude-plugins-official/contents/.claude-plugin/marketplace.json -H 'Accept: application/vnd.github.raw'`); `note` starts `pattern scan: ` and names `42Crunch-AI/claude-plugins at commit <that sha>`, and holds no `source: not pinned` line. If the entry changed, pick another `git-subdir` entry with a `sha` and note it |
| A12 | both | `check_plugin.py -- anthropics/claude-plugins-official nope-not-a-plugin`; `check_plugin.py --commit abc -- anthropics/claude-plugins-official agent-sdk-dev` | exit 1 with `anthropics/claude-plugins-official has no marketplace plugin named nope-not-a-plugin`; exit non-zero with `--commit needs a full 40-character sha: 'abc'` |
| A15 | both | `check_mcp.py -- modelcontextprotocol/servers '["time", "--", "uvx", "mcp-server-time"]'` (a PyPI server in a folder of the repo) | exit 0; `mcp_args[3]` matches `^mcp-server-time==\S+$` and `package.version` is that version; `lines[0]` is `package: mcp-server-time@<version> (PyPI), named by this repo's src/time/pyproject.toml; not verified to come from this repo`; `lines[1]` starts `pinned: only mcp-server-time, to <version>; `; `lines[2]` is the one `✓ check: nothing found (<n> files, <m> PyPI dependencies, advisory and malware lookups)` line (on 2026-10-30: 7 files, 30 PyPI dependencies), or, if the check now finds something, the lines summed up by severity with a `dependencies: mcp-server-time@<version>: <m> PyPI, …` line among them; `blocked` `false`; nothing is left in the scratch directory |
| A16 | both | `check_mcp.py -- modelcontextprotocol/servers '["e", "--", "docker", "run", "-i", "mcp/time"]'`; then `'["e", "--url", "https://mcp.example/mcp"]'`; then `'["e", "--", "npx", "-y", "@modelcontextprotocol/server-everything@^999"]'`; then `'["e", "--", "npx", "-y", "@modelcontextprotocol/server-everything@~2026.1"]'`; then `'["e", "--", "npx", "-y", "other-pkg", "@modelcontextprotocol/server-everything"]'`; then `check_mcp.py -- modelcontextprotocol/servers 'not json'` | the first: `lines` is exactly `["? unchecked: pattern scan, advisory lookup and malware lookup (the command runs a container image, which kirby does not check); not pinned"]` and `mcp_args` unchanged; the second: `["? unchecked: pattern scan, advisory lookup and malware lookup (a remote server at a URL; its code does not install here)"]`; the third: `lines[1]` is `not pinned: kirby could not tell which version of @modelcontextprotocol/server-everything the command installs (no version of @modelcontextprotocol/server-everything matches ^999); it installs as given` and `mcp_args` unchanged; the fourth: `mcp_args[4]` is `@modelcontextprotocol/server-everything@<V>` and `lines[1]` starts `pinned: only @modelcontextprotocol/server-everything, to <V>, the highest version matching ~2026.1; `, with `<V>` the highest `2026.1.x` in `npm view @modelcontextprotocol/server-everything versions --json` (2026.1.26 on 2026-10-30); the fifth (npx runs `other-pkg`, so the package the repo names is only an argument): `lines` is exactly `["? unchecked: pattern scan, advisory lookup and malware lookup (the command runs none of the packages this repo names: <names>); not pinned"]` and `mcp_args` unchanged; the last exits 1 with `mcp_args must be a JSON list of strings` |

What A9 covers, against the Codex server with scripted answers: H1 the dialog's facts and check lines
(summed up by severity: one `⚠ warn (7): …` line naming the warn findings, then one `✓ advisory and malware lookups: nothing found`
line; every finding, info ones too, with its file and line in the model's note), English options and `ENGLISH_NOTE`, all 12 rules and the 3 combinations fired, the zero-width name shown as `we?ird.py`,
and, as the fixture's warn findings ask for a model review and none was passed, the `UNREVIEWED` line with Install still offered;
H2 the model's wording and the README / pick another / dismiss results; H3 unusable wording falls
back to English with the reason; H4 cancel and dismiss at the scope step; H5 no project from Codex
offers only `user`, dialog 1 saying so and why and the scope dialog's option saying where; H6 a commit pushed while the scope dialog is open:
the commit shown installs all the same (`.kirby.json` records it); the shown commit force-pushed away and pruned while the scope dialog is open:
`install failed` with the `could not fetch …` line, nothing written; H7 a local install records the shown commit and adds the folder to `.gitignore`; H8 the
`exists:` line, failure without `force`, replacement with it, `project` leaving `.gitignore` alone;
H9 a plugin's facts (`check_plugin.py`'s lines, the marketplace format and `USER_ONLY`, section C), the scope dialog's `USER_OPTION` running
`codex plugin marketplace add …` (no `--ref`) and `codex plugin add`, then the commit of the marketplace (a local clone of
`PLUGIN_REPO` listed in its place once added) checked against the one shown, `cancel` there running none, also when dialog 1's options
are out of order, and the `check` tool saying `not needed` for a plugin the check found nothing in; a marketplace already added: the dialog's `marketplace: already added as …` line (also at the end of the result),
the check at the clone's commit, only `codex plugin add` run, and a commit made in the clone while the scope dialog is open:
`codex plugin add` then `codex plugin remove` and the `has moved on … the plugin was removed again` line; H10 an MCP
server: `check_mcp.py` finding `@modelcontextprotocol/server-everything` in the repo's `src/everything/package.json` and pinning it,
dialog 1 with the pinned command, the check's lines (the first a `⚠ warn (…`, `✓ check: nothing found (…`, `✓ pattern scan: …` or `✕ …` line) and `USER_ONLY`, `USER_OPTION` running `codex mcp add` with the pinned command and
the result ending with the check's note and, as its warn findings ask for a model review and none was passed, the `UNREVIEWED` line
(before `USER_ONLY` in dialog 1, and in a `review:` block at the end of the result); the `check` tool giving the package's files with its
`read` (`package` and the archive's sha256 as `ref`); a container image (`docker run …`) shown as one `? unchecked: …; not pinned` line;
H11 the refusals before any dialog and a client without elicitation; H12 the `file` tool reading a
flagged line at the scanned commit and refusing `..`, an absolute path and a branch name, and reading the `package.json` of H10's package
through that `read`, refusing another sha256; H13 after
`fixture.py malware`: `blocked`, the `✕ blocked: …` line first, then the `✕ danger: …` lines naming `flatmap-stream@0.1.1` and
`lodash@4.17.20` with their ids, in English and with `zh-TW` in 繁體中文,
dialog 1 with only cancel, README and pick another, and each result ending with the `blocked:` line; H14 the `check` tool on the fixture
(`review` `needed`, `read` the fixture's repo at the commit checked, its files, the dialog's facts), then install with a review result:
a finding shown after the check lines, its hidden characters and line break stripped, labelled `(model review, as reported by the model)`,
and repeated in the result's `review:` block; a review of another commit, one that could not run, and one that found nothing, each one line
with Install offered; a reason over 120 characters refused before any dialog; H15 `dialog.lang`: with `zh-TW` the repo line
(`… 更新`), the skill line, the scripts line, the `exists:` line and the check's lines (`⚠ 警告 7 項：…`, `✓ 漏洞、惡意套件查詢：沒有發現`) in 繁體中文, with `zh-CN` (no
project) the skill line and the `installs at:` line in 简体中文, with `en` or `ja` English, the `check` tool's `findings` in English,
the result in English, and an `about` over 120 characters falling back to English (facts too) with the `note:` saying why;
H16 `dialog.lang` `zh-TW` for a plugin and an MCP server: the plugin line, the marketplace lines (`已加入`, `Claude Code 格式`),
the description and source lines, the `MCP server：` command line, the package and pinned lines and, for both, the check's lines in 繁體中文, with commands, names,
versions and paths as they are, and the scope dialog's install option `安裝在 user（~/.codex/config.toml，所有專案）`, which installs
at user, while the result's marketplace line stays English.
It installs nothing outside `$E2E/codex/h`: commands that would install at user scope are recorded, not run,
and `codex plugin marketplace list` is answered by the script (H9 makes its clone in `$E2E/codex/codex-marketplace-clone` and removes it).

FLAGGED, the scan's line for the fixture (the dialog shows it; the combinations come first, then the
warn rules, by name only; the info findings are left out):

```
⚠ warn (7): may send secrets out, may download and run code, may download and decode a payload, prompt-injection phrases, hidden Unicode, credentials, changes shell startup files
```

With `dialog.lang` `zh-TW` it reads (the #24 mock-up), and the lookups' line after it:

```
⚠ 警告 7 項：可能外傳密鑰、可能下載並執行程式碼、可能下載並解碼資料、提示詞注入字句、隱藏 Unicode、憑證、修改啟動檔
✓ 漏洞、惡意套件查詢：沒有發現
```

FLAGGED_NOTE, the `pattern scan:` block in every result for the fixture (`<FX_SHA>` is the commit the dialog
showed; the model gets every finding with its file and line, the `exec` findings in `validate-*` following the upstream
files at the fixed commit), followed by the fixture's `lookups:` block (as at the time of writing, with `<FX_SHA>`):

```
pattern scan: the pattern-scan findings in cloudflare/security-audit-skill at commit <FX_SHA> (the dialog showed the user the warn ones by name only, without files or lines, and left out the info ones):
  warn send-secrets: may send secrets out (network + env-secret)
  warn download-run: may download and run code (network + exec)
  warn download-decode: may download and decode a payload (network + decode)
  warn injection-phrase skills/security-audit/E2E-NOTES.md:2
  warn hidden-unicode skills/security-audit/E2E-NOTES.md:4
  warn credentials skills/security-audit/e2e-setup.sh:5
  warn startup-files skills/security-audit/e2e-setup.sh:6
  info html-comment skills/security-audit/E2E-NOTES.md:2
  info broad-tools skills/security-audit/E2E-NOTES.md:3
  info agent-config skills/security-audit/E2E-NOTES.md:5
  info long-base64 skills/security-audit/E2E-NOTES.md:6
  info network skills/security-audit/e2e-setup.sh:3
  info exec skills/security-audit/e2e-setup.sh:3
  info env-secret skills/security-audit/e2e-setup.sh:4
  info decode skills/security-audit/e2e-setup.sh:7
  info exec skills/security-audit/validate-coverage-ledger.test.cjs:5
  info exec skills/security-audit/validate-findings.test.cjs:5
  info exec skills/security-audit/we?ird.py:1
lookups: the dialog showed the user no findings from the advisory and malware lookups for cloudflare/security-audit-skill at commit <FX_SHA>
dependencies: no npm or Python dependency files
```

## B. Claude Code (pane C)

### Setup

- Version: `claude --version`.
- Config directory: `CLAUDE_CONFIG_DIR=$E2E/home/claude`. It holds what would otherwise go to
  `~/.claude` and `~/.claude.json`: the settings and the plugin marketplaces (B17), MCP servers at
  `local` scope (B19), trust decisions, user skills (B7: `install_skill.py` installs into
  `$CLAUDE_CONFIG_DIR/skills`), and the transcripts. The user's own `~/.claude/CLAUDE.md`, settings,
  hooks and plugins are not loaded.
- Writes outside `$E2E`: MCP logs in `~/.cache/claude-cli-nodejs/<project>/` for each project
  directory a session starts in (`<project>` is its path with every character other than
  `A-Za-z0-9` replaced by `-`); and the transcripts of `claude -p ok` run from `$E2E` in the real
  setup (a renewal in Isolation, the login check in Cleanup) in `~/.claude/projects/<E2E>/`, named
  the same way.
- Starting state of the real setup, from `$E2E`: `claude mcp list`, `ls -A ~/.claude/skills`;
  `cp ~/.claude/settings.json $E2E/before/claude-settings.json`.
- Must be absent: nothing; `$E2E/home/claude` starts empty but for the login.
- Loading kirby: nothing to do; each session starts with `--plugin-dir $KIRBY` (Driving).
- Projects: `$E2E/claude/p`.

### Driving

- **Start** with the kirby under test, from the case's project directory, in a subshell so the
  variables do not stay in that pane's shell:
  `herdr pane run <C> "cd <P> && (. $E2E/iso.sh && claude --plugin-dir $KIRBY)"`. **With the
  fixture**: `herdr pane run <C> "cd <P> && (. $E2E/iso.sh && . $E2E/fx/env.sh && claude --plugin-dir $KIRBY)"`.
- **First start** in the fresh config directory: a theme picker (`Choose the text style`), then
  `Security notes` (`Press Enter to continue…`); `enter` on each. Later starts skip them. A notice
  such as `Auto mode is now Claude Code's default permission mode` needs no answer.
- **Trust prompt**: wait for `trust this folder`, send `down`, wait until the screen shows
  `❯ Yes, I trust this folder`, then `enter`.
- **Sending a prompt**: `herdr agent prompt <C> "<text>" --wait --timeout 300000`.
- **Exit** with `/exit` (send-text, wait for it to show, Enter; `ctrl+c` does not exit it); wait for
  `claude --resume`.
- **The input box can show a suggested reply** (greyed, e.g. `好，繼續安裝`). It is not typed; never
  press Enter on an input box you did not fill.
- **Dialogs** number the options with `❯` on the selected one. Claude Code adds `Type something.`
  and `Chat about this` below kirby's options; they are not kirby's.

### Cases

Project `$E2E/claude/p` unless a case says otherwise. Start one session for B1–B15 and B27, restart it for
B16 and B23 (fixture), for B26 (a second fixture), and once more after B26. Run every `claude` command below with `iso.sh` (Isolation).

Check each install result with `(. $E2E/iso.sh && python3 -I $KIRBY/tests/e2e/transcript.py claude <P> --tool install --last 1)`
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
HEADER_ZH(cloudflare/security-audit-skill)
技能：security-audit · commit <SHA7> · <N> 個檔案
<len(SCRIPTS)> 個腳本，例如 <SCRIPTS[0]>、<SCRIPTS[1]>
<CHECK_ZH, one per line>
```

then, after a blank line, the model's `about` (if any), a blank line and its `next` question; four
options in the user's language meaning cancel, read the README first, pick another, install. Dialog 2:
the model's scope question; options `cancel`, `local`, `project`, `user`.

Model-written rules for every install: the wording is in the prompt's language (Traditional Chinese
here); `about`, if present, never says the repo is safe, checked or reviewed; the scope question does
not explain the scopes.

**B3 Install at local.** Prompt `用 kirby 安裝 cloudflare/security-audit-skill 的 security-audit skill（folder 是 skills/security-audit）`.
Answer Install, then `local`.
- Transcript: before the install call, an `mcp__kirby__check` call with the same `repo`, `kind` and `folder`, whose result has
  `"review": "not needed"` and no `files`; no `Agent` call; the install call has no `review` and no `sha`.
- Dialogs as above (no `model review` line).
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
- Dialog 1 gains, after the scripts line: `已存在：.claude/skills/security-audit/（安裝在 local 或 project 會失敗）`.
- Result starts `install failed (scope local): ` and holds `.claude/skills/security-audit already exists; pass --force to replace it`, then `SCAN_NOTE`.
- Reply shows the failure; no second install call with `force` unless the user asks.

**B5 Force.** Reply `取代現有的資料夾`. Answer Install, `local`.
- The install call has `"force": true`; dialog 1 shows `已存在：.claude/skills/security-audit/（安裝在 local 或 project 會取代它）`.
- Result starts `installed (scope local): ` and its command ends `--commit <SHA> --force`.
- `.kirby.json` was rewritten (newer mtime than in B3).

**B6 Project scope.** Reset the project. Prompt as B3; answer Install, `project`.
- Result `installed (scope project): …--scope project --commit <SHA>`; no `added … to .gitignore` line; `.gitignore` unchanged.

**B7 User scope.** Prompt as B3; answer Install, `user`.
- Result `installed (scope user): …--scope user --commit <SHA>` with `-> <E2E>/home/claude/skills/security-audit (<N> files)`.
- Files: `$E2E/home/claude/skills/security-audit/.kirby.json` has `"commit": "<SHA>"`; `ls -A ~/.claude/skills` as in the starting state.

### The other answers

Reset the project before each; prompt as B3.

**B8 Read the README first.** Answer `Read README first` (option 2).
- Result exactly: `not installed: the user wants to read the README first. Summarise it for them (gh api repos/cloudflare/security-audit-skill/readme -H 'Accept: application/vnd.github.raw') and end your turn. Call this tool again only after they reply that they still want it.` then `SCAN_NOTE`.
- Transcript: a `gh api repos/cloudflare/security-audit-skill/readme` call; no further install call in the turn.
- Reply: a README summary that also lists each finding in `SCAN_NOTE` with the commit, offers to explain them, and ends the turn.

**B9 Explain a finding.** Right after B8, prompt `validate-findings.test.cjs 第 5 行在做什麼？`.
- Transcript: an `mcp__kirby__file` call with `{"repo": "cloudflare/security-audit-skill", "path": "skills/security-audit/validate-findings.test.cjs", "ref": "<SHA>"}` (the scanned commit, not a branch); no `gh api` Bash call. No permission prompt opens for it (kirby's hook allows `check` and `file`).
- Reply: quotes or describes line 5 of that file at `<SHA>` (fetch it yourself to compare); describes what the code does; gives no verdict that it is safe or malicious.

**B10 Pick another.** Answer option 3. Result exactly `not installed: the user wants a different one. Ask which of the other recommendations to look at.` + `SCAN_NOTE`. Reply asks which other one; no install call.

**B11 Cancel.** Answer option 1. Result `not installed: the user cancelled.` + `SCAN_NOTE`. The model stops.

**B12 Dismiss.** Press `esc` on dialog 1. Result `not installed: the user dismissed the dialog.` + `SCAN_NOTE`.

**B13 Free text.** On dialog 1 choose `Type something.` and enter `稍後再說`. Result `not installed: the user answered "稍後再說".` + `SCAN_NOTE`.

**B14 Scope step.** Answer Install, then option 1 (`cancel`): `not installed: the user cancelled at the scope step.` + `SCAN_NOTE`. Again with `esc` on dialog 2: `not installed: the user dismissed the scope dialog.` + `SCAN_NOTE`. Nothing written either time.

**B15 English fallback.** Prompt `直接呼叫 mcp__kirby__install 安裝 cloudflare/security-audit-skill（kind skill，folder skills/security-audit），不要傳 dialog 參數，也不要先載入 skill。` Answer Cancel.
- Dialog 1's facts are in English: `HEADER(cloudflare/security-audit-skill)`, `skill: security-audit · commit <SHA7> · <N> files`,
  `scripts: <len(SCRIPTS)>, e.g. <SCRIPTS[0]>, <SCRIPTS[1]>`, then `CHECK_LINES`. It ends `What next?`, options `Cancel`, `Read README first`, `Pick another`, `Install`.
- Result `not installed: the user cancelled.`, `SCAN_NOTE`, then `ENGLISH_NOTE`. If the model loads the skill and passes `dialog` anyway, mark N/A.

**B27 简体中文.** Prompt `用 kirby 安装 cloudflare/security-audit-skill 的 security-audit skill（folder 是 skills/security-audit）`. Answer option 1.
- The install call's `dialog` has `"lang": "zh-CN"` and its wording is in 简体中文.
- Dialog 1's facts: `HEADER_ZH(cloudflare/security-audit-skill)`, `技能：security-audit · commit <SHA7> · <N> 个文件`,
  `<len(SCRIPTS)> 个脚本，例如 <SCRIPTS[0]>、<SCRIPTS[1]>`, then `CHECK_LINES` in 简体中文 (as `CHECK_ZH`, with `zh-CN` in the
  `ZH` command: at the time of writing `✓ pattern 扫描：没有危险或警告的发现` and `✓ 漏洞、恶意包查询：没有发现`).
- Result `not installed: the user cancelled.` + `SCAN_NOTE`, in English; no `note:` line.

### Fixture: flagged files and a repo that moves on

**B16 Flagged scan, then the repo moves on.** New project `$E2E/claude/fx`; start Claude Code with the
fixture (subshell, Driving). Prompt as B3. Record `FX_SHA` again (`git -C $E2E/fx/upstream.git rev-parse HEAD`).
- Dialog 1: the header is still GitHub's; `技能：security-audit · commit <FX_SHA7> · <N+3> 個檔案`;
  the scripts line counts the fixture's `e2e-setup.sh` and `we?ird.py` too; the check lines are exactly the two of
  FLAGGED's `zh-TW` block (`⚠ 警告 7 項：…`, then `✓ 漏洞、惡意套件查詢：沒有發現`; no file, line or info finding), then one or
  more `REVIEW_LINE`s (the fixture's warn findings ask for a model review; B26 checks it); no zero-width character anywhere in
  the dialog.
- Answer Install. While dialog 2 is open, run `python3 -I $KIRBY/tests/e2e/fixture.py advance $E2E/fx`
  (prints `NEW`). Answer `local`.
- The commit shown installs all the same. Result starts `installed (scope local): `, holds `--commit <FX_SHA>` and
  `installed cloudflare/security-audit-skill:skills/security-audit@<FX_SHA7> -> .claude/skills/security-audit (<N+3> files)`,
  then FLAGGED_NOTE for `<FX_SHA>`, then `REVIEW_BLOCK`.
- `.claude/skills/security-audit/.kirby.json` has `"commit": "<FX_SHA>"`, not `NEW`. Reply says what was installed.
- **The commit shown is gone.** Reset the project. Prompt as B3; dialog 1 shows `commit <NEW7>`. Answer Install.
  While dialog 2 is open, run `python3 -I $KIRBY/tests/e2e/fixture.py rewind $E2E/fx` (prints `<FX_SHA>` again). Answer `local`.
- Result starts `install failed (scope local): ` and holds `--commit <NEW>` and
  `could not fetch cloudflare/security-audit-skill at commit <NEW7>, the one shown to the user; nothing installed (a force-push can remove a commit). git: `,
  then FLAGGED_NOTE for `<NEW>`, then `REVIEW_BLOCK`.
- No `.claude/` in the project. Reply says nothing was installed and why, and asks before trying
  again; no second install call in the turn.
- Stay in this session for B23.

**B23 A known-malicious dependency blocks.** Same session as B16. Run
`python3 -I $KIRBY/tests/e2e/fixture.py malware $E2E/fx` (prints the new `FX_SHA`). Prompt as B3.
- Dialog 1: the check lines start with
  `✕ 已擋下：惡意套件查詢找到已知的惡意套件，所以不提供安裝`,
  `✕ 危險：flatmap-stream@0.1.1 (npm) 被列為惡意套件（MAL-2025-20690）`, then the other danger lines, each with its ids, one
  of them starting `✕ 危險：lodash@4.17.20 (npm) 有 `; then FLAGGED's `⚠ 警告 7 項：…` line and `相依套件：package-lock.json：2 個 npm`.
  Three options only: cancel, read the README first, pick another.
- Answer cancel. Result starts `not installed: the user cancelled.`, then the `pattern scan:` block of
  FLAGGED_NOTE for the new `<FX_SHA>`, then a `lookups:` block (in place of FLAGGED_NOTE's last two
  lines) whose lines include `  danger malware flatmap-stream@0.1.1 (npm) MAL-2025-20690: in OpenSSF Malicious Packages`
  and that ends with
  `blocked: the dialog did not offer Install, because the malware lookup lists flatmap-stream@0.1.1 (npm) as known-malicious. kirby will not install it; tell the user why, and that installing it anyway means doing it by hand.`,
  and nothing after it: a blocked install gets no model review, so neither the dialog nor the result has a
  `model review` line, and the transcript has no `mcp__kirby__check` result with `"review": "needed"` and no
  Agent call for it.
- Reply names `flatmap-stream` and `MAL-2025-20690`, says kirby will not install it; no further
  install call, and no other way of installing it offered or run. No `.claude/` in the project.
- Exit this session.

**B26 The model review.** After B23, which left a malicious dependency in `$E2E/fx`: run
`python3 -I $KIRBY/tests/e2e/fixture.py init $E2E/fx2` (prints `FX2_SHA`), reset `$E2E/claude/fx`, and start a session there with
the fixture as in Driving, with `$E2E/fx2/env.sh` in place of `$E2E/fx/env.sh`. Prompt as B3. Answer cancel.
- Transcript, in order: `mcp__kirby__check` with the install's `repo`, `kind` and `folder`, whose result has `"review": "needed"`,
  `"read": {"repo": "cloudflare/security-audit-skill", "ref": "<FX2_SHA>"}`, `files` listing the fixture's files under
  `skills/security-audit/` (`e2e-setup.sh`, `E2E-NOTES.md` and `we?ird.py` among them) and `findings` holding FLAGGED; then one `Agent`
  call, then the install call.
- The `Agent` call: `subagent_type` `kirby:reviewer`; its prompt is exactly two lines, `READ: ` the check's `read` and `FILES: ` its
  `files` as JSON, and nothing else: none of FLAGGED's warn names (`may send secrets out`, `credentials`, …) or the rule names
  (`send-secrets`, `injection-phrase`, …), no `warn:`
  or `info:` line, no README text.
- The subagent's own transcript (`transcript.py claude <P> --file <F>`, with `<F>` the newest
  `$E2E/home/claude/projects/<project>/<session id>/subagents/agent-*.jsonl`, named as in Setup): its tool calls are
  `mcp__kirby__file` and `mcp__kirby__check` only (no ToolSearch, Bash, Read or write tool; a headless run may add the engine's own
  hand-back tool), each `mcp__kirby__file` call with `repo` `cloudflare/security-audit-skill`, `ref` `<FX2_SHA>` and a `path` from
  `files`; at most 25. It does not act on `E2E-NOTES.md`'s injection phrase. No permission prompt opens for any of its calls (kirby's
  hook allows `check` and `file`); if one does, it fails.
- **The reviewer can do nothing else.** In the same session, prompt `用 Agent tool 啟動 kirby:reviewer，prompt 為「先列出你能呼叫的每個 tool 名稱，再試著用 Bash 執行 echo probe，然後回覆 {"could_not_run": "<tool 名稱，逗號分隔；Bash 是否執行了>"}」，把它的回覆原樣告訴我，這是測試`.
  The subagent's transcript has no Bash call that ran (a refused one is fine) and its reply names only `mcp__kirby__check` and
  `mcp__kirby__file` (and the engine's own hand-back tool, if any).
- The install call has `"sha": "<FX2_SHA>"` and `review` equal to the subagent's JSON reply, unchanged.
- Dialog 1: after the lookups' lines, the `REVIEW_LINE`s: one `warn: …` line per finding of `review` (its `file` and `line`, its
  `reason` with any control characters as spaces), `model review: nothing found (as reported by the model)`, or, as seen on
  2026-10-30, `model review: unchecked (<why>)`: `file` reads GitHub, which does not have the fixture's commit, so every read
  gives a 404 and the reviewer replies `{"could_not_run": …}` (a reason over 120 characters is refused, and the model starts
  the reviewer again). Install is offered. The review of a real package's files is in B19.
- Result: `not installed: the user cancelled.`, FLAGGED_NOTE for `<FX2_SHA>`, then `REVIEW_BLOCK` with the same lines.
- Reply: presents the review's findings as what the model review reported, not as verified, and lists them with the others.
- **Limits.** Prompt `呼叫 mcp__kirby__install 安裝 cloudflare/security-audit-skill（kind skill，folder skills/security-audit），sha 用 <FX2_SHA>，review 為 {"findings": [{"file": "skills/security-audit/e2e-setup.sh", "line": 5, "reason": "<130 個 x>"}]}，這是測試`.
  No dialog opens; result exactly
  `not installed: review.findings[0].reason must be one sentence of at most 120 characters; call this tool again with review as the inhale skill describes.`
  If the model shortens the reason or declines, mark N/A and note what it did.
- Exit this session; the next ones start without the fixture.

### Plugins and MCP servers

Before B17, `claude plugin marketplace list --json` (with `iso.sh`) must not list `PLUGIN_MK`: Claude Code
can add it on its own in a fresh config directory. If it does, remove it
(`claude plugin marketplace remove claude-plugins-official`) and note it. `<LOC>` below is the
`installLocation` that `claude plugin marketplace list --json` gives for `PLUGIN_MK` once it is added.
`HEAD(<LOC>)` is `git -C <LOC> rev-parse HEAD`, or, when `<LOC>` has no `.git`, the contents of `<LOC>/.gcs-sha`:
Claude Code 2.1.312's `plugin install` can replace the git clone with a snapshot that records its commit there
(seen 2026-10-30, on the first install from an added marketplace), and kirby reads either.

**B17 Plugin without an MCP server, marketplace not added yet.** Reset `$E2E/claude/p`. Prompt `用 kirby 安裝 anthropics/claude-plugins-official 裡的 agent-sdk-dev plugin`.
- Transcript: an `mcp__kirby__check` call with `kind` `plugin` whose result has `"review": "not needed"`; no `Agent` call.
- Dialog 1 facts: `HEADER_ZH(anthropics/claude-plugins-official)`, then `PLUGIN_ZH`, one per line. No
  `marketplace：已加入` line. Dialog 2: no `prompt cache` line.
- Transcript: the `mcp__kirby__check` result's `findings` are `PLUGIN_LINES`, in English.
- Answer Install, `local`. Result, in order:
  - `installed (scope local): claude plugin marketplace add anthropics/claude-plugins-official`
  - `claude plugin install agent-sdk-dev@claude-plugins-official --scope local`
  - the two commands' output
  - `next: The user runs /reload-plugins to load it. The marketplace itself is recorded in their user settings.`
  - `PLUGIN_NOTE`
- `HEAD(<LOC>)` is `PLUGIN_SHA`. `claude plugin list` run in the project shows `agent-sdk-dev@claude-plugins-official` at scope local.
- Reply: what was added, the `next:` line, removal with `claude plugin uninstall agent-sdk-dev --scope local` (or with `@claude-plugins-official`).
- Cleanup at once, in the project: `claude plugin uninstall agent-sdk-dev@claude-plugins-official --scope local`;
  `claude plugin list` no longer shows it. Keep the marketplace for B24.

**B18 Plugin with an MCP server.** Prompt as B17 with `context7`. Answer Install.
- Dialog 1 facts: the header, the first line of `PLUGIN_MCP_ZH`, the `marketplace：已加入` line of B24 if the marketplace is still added (B25's cleanup removes it), then the rest of `PLUGIN_MCP_ZH`.
- Dialog 2 ends with a blank line and `prompt cache：這個外掛帶有 MCP server；如果這個工作階段關閉了 tool search，用 /reload-plugins 載入它會重建一次 cache。`
  (If the pane's environment has `ENABLE_TOOL_SEARCH=false`: `prompt cache：這個外掛帶有 MCP server；已設定 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 載入它會重建一次 cache。`)
- Answer `cancel`: `not installed: the user cancelled at the scope step.` + `PLUGIN_MCP_NOTE`.

**B24 The marketplace is already added.** Right after B17 (the marketplace is still there, at `PLUGIN_SHA`). Prompt as B17.
- Dialog 1 facts: the header, the first line of `PLUGIN_ZH`, then
  `marketplace：已加入，名稱 claude-plugins-official，在 commit <PLUGIN_SHA7>；直接從它安裝`,
  then the rest of `PLUGIN_ZH`.
- Answer Install, `local`. Result first line exactly `installed (scope local): claude plugin install agent-sdk-dev@claude-plugins-official --scope local`
  (no `marketplace add`), then the output, the `next:` line, `PLUGIN_NOTE` and, in English,
  `marketplace: already added as claude-plugins-official, at commit <PLUGIN_SHA7>; installs from it as it is`.
  `HEAD(<LOC>)` is still `PLUGIN_SHA` (`<LOC>` may now be a snapshot; see above).
- Cleanup at once: uninstall it as in B17.
- **The clone moves during the dialog.** Prompt as B17 again; answer Install. While dialog 2 is open, move it: in a git
  clone, `git -C <LOC> -c user.name=e2e -c user.email=e2e@invalid commit -q --allow-empty -m moved`; in a snapshot, write
  the repo's previous commit (`gh api 'repos/anthropics/claude-plugins-official/commits?per_page=2' --jq '.[1].sha'`) into
  `<LOC>/.gcs-sha` with a file tool. Answer `local`.
  Claude Code 2.1.312 refreshes a marketplace that is not at its repo's commit when it installs
  (seen 2026-10-30, for a clone and for a snapshot), so the result is as above (`installed (scope local): …`) and `HEAD(<LOC>)` is
  `PLUGIN_SHA` again. If the result is instead `install failed (scope local): …` ending
  `the marketplace claude-plugins-official has moved on: it is at commit <HEAD7> after the install, not <PLUGIN_SHA7> as shown to the user; the plugin was removed again`
  (then `PLUGIN_NOTE` and the marketplace line), Claude Code no longer refreshes such a clone: `claude plugin list` must not show
  `agent-sdk-dev`, and `claude plugin marketplace list` must still list `PLUGIN_MK`; note the change. Either way, uninstall it if installed.
  (The removal itself is covered by `tests/plugin.test.ts`; it needs the repo to move between the check and the install.)

**B25 The marketplace is behind its repo.** After B24. Put the clone at an older commit, consistently:
`OLD=$(gh api 'repos/anthropics/claude-plugins-official/commits?per_page=2' --jq '.[1].sha')`, then, in a git clone,
`git -C <LOC> fetch -q --depth 1 origin <OLD>`, `git -C <LOC> reset -q --hard <OLD>`,
`git -C <LOC> update-ref refs/remotes/origin/main <OLD>`; in a snapshot, write `<OLD>` into `<LOC>/.gcs-sha` with a file tool.
Prompt as B17 (`PLUGIN_SHA7` is the repo's HEAD now; record it again if it moved).
- Dialog 1 facts: the header, the first line of `PLUGIN_ZH`, then
  `marketplace：已加入，名稱 claude-plugins-official，在 commit <OLD7>，落後於它的 repo；安裝時會更新到檢查過的 commit <PLUGIN_SHA7>`,
  then the rest of `PLUGIN_ZH` (the check is of `PLUGIN_SHA`, not `OLD`). kirby says `落後於它的 repo` (behind its repo) only when it read
  the clone's commit: if it cannot, the line is instead
  `marketplace：已加入，名稱 claude-plugins-official，kirby 讀不到它在哪個 commit；安裝時會更新到檢查過的 commit <PLUGIN_SHA7>`
  (covered by `tests/plugin.test.ts`; this case does not need to break the clone to see it).
- Answer Install, `local`. Result first line exactly `installed (scope local): claude plugin install agent-sdk-dev@claude-plugins-official --scope local`,
  then the output, the `next:` line, `PLUGIN_NOTE` and, in English,
  `marketplace: already added as claude-plugins-official, at commit <OLD7>, behind its repo; installing refreshes it to <PLUGIN_SHA7>, the commit checked`.
  `HEAD(<LOC>)` is now `PLUGIN_SHA`.
- Cleanup: uninstall it as in B17, then `claude plugin marketplace remove claude-plugins-official`; `claude plugin marketplace list --json` no longer lists it.

**B19 MCP server.** Prompt `用 kirby 安裝 modelcontextprotocol/servers 的 Everything MCP server，名稱用 kirby-e2e`.
- Transcript: the README is read first (`gh api repos/modelcontextprotocol/servers/readme`); the install call has `"mcp_args": ["kirby-e2e", "--", "npx", "-y", "@modelcontextprotocol/server-everything"]` (other names or flags: note them and adapt the expectations and the cleanup).
- Transcript, the model review of the package: an `mcp__kirby__check` call with that `mcp_args`, whose result has `"review": "needed"` and
  `"read": {"package": {"ecosystem": "npm", "name": "@modelcontextprotocol/server-everything", "version": "<MCP_VERSION>"}, "ref": "<MCP_REVIEW_SHA>"}`;
  an `Agent` call as in B26 (the prompt carries that `read` and the package's `files`, none of `MCP_LINES`); the subagent's
  `mcp__kirby__file` calls each pass that `package` and `ref` with a `path` from `files`; the install call has `"sha": "<MCP_REVIEW_SHA>"`
  and the subagent's reply as `review`.
- Dialog 1 facts: `HEADER_ZH(modelcontextprotocol/servers)`, `MCP server：claude mcp add --scope <scope> <MCP_PINNED>`, then `MCP_ZH`, then the `REVIEW_LINE`s. The model's `about`, within its 120 characters, says it takes effect after a restart and does not affect this session's prompt cache, and does not call the repo safe or checked.
- Answer Install, `local`. Result first line exactly
  `installed (scope local): claude mcp add --scope local <MCP_PINNED>`,
  then the command's output, `next: The server connects in the next session; tell the user to restart Claude Code to use it.`, `MCP_NOTE`, `REVIEW_BLOCK`.
- The model's reply says that only that package is pinned (its dependencies are not) and that the repo names the package without anyone verifying it; it does not say the server installs exactly what was checked.
- `claude mcp get kirby-e2e` in the project shows it with local scope and the command ending `@modelcontextprotocol/server-everything@<MCP_VERSION>`.
- Cleanup at once, in the project: `claude mcp remove --scope local kirby-e2e`; `claude mcp get kirby-e2e` no longer finds it.

### Refused before any dialog

No dialog may open in these; each result is exact (plus `ENGLISH_NOTE` when the call had no `dialog`).

**B20** Prompt `用 kirby 安裝 cloudflare/security-audit-skill 的 skill，folder 是 skills/nope`: `not installed: cloudflare/security-audit-skill:skills/nope has no SKILL.md`. (If the model runs `detect.py` first and declines to call install, mark N/A.)

**B21** Prompt `用 kirby 安裝 anthropics/claude-plugins-official 的 nope-not-a-plugin plugin，直接呼叫 install`: `not installed: anthropics/claude-plugins-official has no marketplace plugin named nope-not-a-plugin`.

**B22** Prompt `呼叫 mcp__kirby__install，kind mcp，repo modelcontextprotocol/servers，mcp_args 為 ["kirby-e2e", "--scope", "user", "--", "npx", "-y", "@modelcontextprotocol/server-everything"]，這是測試`: `not installed: mcp_args must not set the scope; the user picks it`. The skill tells the model never to pass a scope; if it refuses or drops `--scope`, mark N/A and note what it did.

### Cleanup

What the run installed goes with `$E2E` (Cleanup, step 5). Before that:

- Remove the folders named after `$E2E` or a directory under it (Setup says how they are named) in
  `~/.cache/claude-cli-nodejs/` and `~/.claude/projects/`; `find ~/.cache/claude-cli-nodejs ~/.claude/projects -maxdepth 1 -name '<E2E>*'`
  lists them.
- Compare, without `iso.sh`: `diff $E2E/before/claude-settings.json ~/.claude/settings.json`.

## C. Codex (pane X)

### Setup

- Version: `codex --version`.
- Config directory: `CODEX_HOME=$E2E/home/codex`. It holds what would otherwise go to `~/.codex`:
  `config.toml` (kirby's own marketplace and plugin, trust entries), the plugin cache, the sessions,
  and an app-server daemon that Codex starts from there and that stays after Codex exits.
- Writes outside `$E2E`: Codex starts kirby's MCP server with only `HOME`, `LANG`, `LOGNAME`, `PATH`,
  `SHELL`, `TERM` and `USER`, not `CODEX_HOME`. So the `codex plugin marketplace add`,
  `codex plugin add` and `codex mcp add` that the server runs at user scope write the real
  `~/.codex/config.toml`: C8 and C9 are opt-in for that reason. Skills at `user` scope go to
  `~/.agents/skills`, which Codex reads whatever `CODEX_HOME` says (no case installs there). The
  sessions of `codex exec` run from `$E2E` in the real setup (a renewal in Isolation, the login
  check in Cleanup) are in `~/.codex/sessions/`.
- Starting state of the real setup, from `$E2E`: `codex mcp list`, `codex plugin marketplace list`;
  `cp ~/.codex/config.toml $E2E/before/codex-config.toml`.
- Must be absent from the real lists: `agent-sdk-dev`, `context7` or `kirby-e2e`.
- Loading kirby, with `iso.sh`: `codex plugin marketplace add $KIRBY`, `codex plugin add kirby@kirby`.
  Check the cache has this checkout: `diff -rq $KIRBY/codex $E2E/home/codex/plugins/cache/kirby/kirby/0.1.0/codex`
  (only `__pycache__` may differ). After any change to kirby, remove and add it again, and stop the
  daemon (`codex app-server daemon stop`): it keeps running the MCP server it started with.
- Projects: `$E2E/codex/p`.

Constants only Codex uses:

| Name | Value |
| --- | --- |
| `USER_ONLY` | `installs at: user (~/.codex/config.toml, every project)`; with `dialog.lang` `zh-TW` (the prompts below) `安裝位置：user（~/.codex/config.toml，所有專案）` |
| `USER_OPTION` | `install at user (~/.codex/config.toml, every project)`; with `dialog.lang` `zh-TW` (the prompts below) `安裝在 user（~/.codex/config.toml，所有專案）` |

### Driving

- **Start**: `herdr pane run <X> "cd <P> && (. $E2E/iso.sh && codex)"`. Codex loads kirby from the
  plugin cache (Setup), not from `$KIRBY`.
- **Trust prompt**: wait for `Trust and continue`, then `enter`. A fresh config directory shows no
  other first-start screen.
- **Tool approval**: the first `install` call in a session asks
  `Allow the kirby MCP server to run tool "install"?`; choose `2. Allow for this session`. It is
  Codex's, not kirby's dialog. The other six tools declare `readOnlyHint` and run without asking
  (Codex 0.164.0); a prompt for one of them means Codex ignored the annotation: note it.
- **Sending a prompt**: `herdr pane send-text <X> "<text>"`, wait until the end of the text shows on
  screen, then `herdr pane send-keys <X> enter` on its own (an Enter sent with the text is
  swallowed). Confirm the agent went `working`.
- **Exit** with `ctrl+c ctrl+c`; wait for `Token usage`.
- **Dialogs** number the options with `›` on the selected one.

### Cases

Project `$E2E/codex/p` unless a case says otherwise. Run every `codex` command below with `iso.sh`
(Isolation), except in the opted-in paths of C8 and C9, which act on the real setup. Check results
with `(. $E2E/iso.sh && python3 -I $KIRBY/tests/e2e/transcript.py codex <P> --tool install --last 1)`;
Codex's MCP calls appear as `mcp__kirby__<tool>`.

Differences from Claude Code to expect: searches and reads are MCP calls (`mcp__kirby__stars`,
`…public`, `…detect`, `…readme`, `…file`), not shell; skills go to `.agents/skills/`; plugins and MCP
servers install at `user` only, so their dialog 1 ends its facts with `USER_ONLY` and dialog 2's options
are `cancel`, `USER_OPTION`; dialog 1 for a plugin from a Claude Code marketplace adds
`marketplace：.claude-plugin/marketplace.json（Claude Code 格式）`; the install command is run with
the server's own Python (`<PY>`, e.g. `/usr/bin/python3`) from the plugin cache (`<CACHE>` =
`$E2E/home/codex/plugins/cache/kirby/kirby/0.1.0`); and free text is not an
answer Codex's dialogs offer, so there is no `answered "…"` result.

**C1 Stars.** Prompt `用 kirby 從我的 star 找能做安全審查的 skill`. As B1, with an `mcp__kirby__stars` call and no shell `gh` or `python3` call.

**C2 Public.** Prompt `用 kirby 從公開的 GitHub 找能查 Postgres 的 MCP server`. As B2, with `mcp__kirby__public`.

**C3 Skill at local.** Prompt `用 kirby 安裝 cloudflare/security-audit-skill 裡的 security-audit skill（folder 是 skills/security-audit）。`
- Transcript: `mcp__kirby__check` with the install's `repo`, `kind` and `folder` before the install call, its result `"review": "not needed"`;
  no `spawn_agent` call; the install call has no `review` and no `sha`.
- Dialog 1 facts as for Claude Code. Dialog 2 options `cancel`, `local`, `project`, `user`.
- Answer Install, `local`. Result, in order:
  - `installed (scope local): <PY> -I <CACHE>/skills/inhale/scripts/install_skill.py cloudflare/security-audit-skill skills/security-audit --scope local --agent codex --commit <SHA>`
  - `installed cloudflare/security-audit-skill:skills/security-audit@<SHA7> -> .agents/skills/security-audit (<N> files)`, the top level and scripts lines
  - `added /.agents/skills/security-audit/ to .gitignore`
  - `next: if Codex does not list it, start a new session.`
  - `SCAN_NOTE`; no `note:` line
- Files: `.agents/skills/security-audit/.kirby.json` has `"commit": "<SHA>"`; `.gitignore` has `/.agents/skills/security-audit/`.

**C4 Existing folder.** Same prompt again. Dialog 1 adds `已存在：.agents/skills/security-audit/（安裝在 local 或 project 會失敗）`; answer Install, `local`: `install failed (scope local): …` with `.agents/skills/security-audit already exists; pass --force to replace it`, then `SCAN_NOTE`.

**C5 Read the README first.** Reset; prompt as C3; answer option 2.
- Result exactly `not installed: the user wants to read the README first. Summarise it for them (the readme tool) and end your turn. Call this tool again only after they reply that they still want it.` + `SCAN_NOTE`.
- Transcript: `mcp__kirby__readme` with `{"repo": "cloudflare/security-audit-skill"}`. Reply as B8.

**C6 Explain a finding.** Prompt `validate-findings.test.cjs 第 5 行在做什麼？`.
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
- The server asks the real `codex plugin marketplace list` (Setup, Writes outside `$E2E`). If the real
  setup already has `PLUGIN_MK` from `PLUGIN_REPO`, the dialog adds
  `marketplace：已加入，名稱 claude-plugins-official，在 commit <its HEAD7>；直接從它安裝`
  and the check is at that commit: note it, and expect no `marketplace add` below, and at the end of the result that line in English,
  `marketplace: already added as claude-plugins-official, at commit <its HEAD7>; installs from it as it is`.
- Dialog 1 facts: `HEADER_ZH(anthropics/claude-plugins-official)`, the first line of `CODEX_PLUGIN_ZH`, `marketplace：.claude-plugin/marketplace.json（Claude Code 格式）`, the rest of `CODEX_PLUGIN_ZH`, `USER_ONLY`. The model's `about`, within its 120 characters, says parts made only for Claude Code (such as hooks) may not work in Codex. Dialog 2 options `cancel`, `USER_OPTION`.
- Not opted in: answer Install, `cancel`. Result `not installed: the user cancelled at the scope step.` + `CODEX_PLUGIN_NOTE`; `~/.codex/config.toml` unchanged.
- Opted in: answer Install, `USER_OPTION`. Result starts
  `installed (scope user): codex plugin marketplace add anthropics/claude-plugins-official` then a line `codex plugin add agent-sdk-dev@claude-plugins-official`, the two commands' output, `next: The user starts a new Codex session to use it.`, `CODEX_PLUGIN_NOTE`.
  The real `~/.codex/config.toml` gains `[plugins."agent-sdk-dev@claude-plugins-official"]` and `[marketplaces.claude-plugins-official]` with no `ref`
  (so `codex plugin marketplace upgrade` keeps working), and `git -C <the marketplace's root from codex plugin marketplace list --json> rev-parse HEAD` is `PLUGIN_SHA`.
  Cleanup at once, without `iso.sh`: `codex plugin remove agent-sdk-dev@claude-plugins-official`; `codex plugin marketplace remove claude-plugins-official` (only if Setup found no such marketplace).

**C9 MCP server (opt-in).** Prompt `用 kirby 安裝 modelcontextprotocol/servers 的 Everything MCP server，名稱用 kirby-e2e`.
- Transcript: `mcp__kirby__readme` first; install with `"mcp_args": ["kirby-e2e", "--", "npx", "-y", "@modelcontextprotocol/server-everything"]`.
- **The model review in Codex** (whether Codex reliably starts a subagent from the skill was never tested before #18; record what it does):
  `mcp__kirby__check` with that `mcp_args`, its result `"review": "needed"` with the `read` of B19; then a `spawn_agent` call whose task is
  the review prompt of `codex/skills/inhale/SKILL.md` word for word with that `read` and the package's `files`, and none of `MCP_LINES`;
  a `wait_agent` call; the subagent's calls (where Codex records them was not checked: look for a newer session file under
  `$E2E/home/codex/sessions/` and read it with `transcript.py codex <P> --file <it>`; note where they were) are `mcp__kirby__file` only, each with that `package` and `ref` and a `path` from `files`; the install call has `"sha": "<MCP_REVIEW_SHA>"`
  and the subagent's reply as `review`. If Codex starts no subagent, the install call must carry `{"could_not_run": "…"}` (dialog 1 then shows
  `model review: unchecked (…)`) or no `review` (`UNREVIEWED`); note which, and whether Codex said why.
- Dialog 1 facts: header, `MCP server：codex mcp add <MCP_PINNED>`, then `MCP_ZH`, then the `REVIEW_LINE`s, then `USER_ONLY`. Dialog 2 options `cancel`, `USER_OPTION`.
- Not opted in: answer Install, `cancel`. Result `not installed: the user cancelled at the scope step.` + `MCP_NOTE` + `REVIEW_BLOCK`; the real `codex mcp list` unchanged.
- Opted in: answer Install, `USER_OPTION`. Result first line exactly `installed (scope user): codex mcp add <MCP_PINNED>`, then output, `next: The user starts a new Codex session to use it.`, `MCP_NOTE`, `REVIEW_BLOCK`.
  `codex mcp get kirby-e2e` without `iso.sh` shows it, with the pinned package. Cleanup at once, without `iso.sh`: `codex mcp remove kirby-e2e`.

**C10 English fallback.** Prompt `直接呼叫 kirby 的 install tool 安裝 cloudflare/security-audit-skill（kind skill，folder skills/security-audit），不要傳 dialog 參數。` Answer Cancel. Dialog 1's facts are in English, as in B15, and it ends `What next?` with options `Cancel`, `Read README first`, `Pick another`, `Install`; result ends `ENGLISH_NOTE`. N/A if the model passes `dialog` anyway.

**C11 Built-in installer (observe only).** In a fresh project, prompt `install cloudflare/security-audit-skill` (no mention of kirby). Record whether Codex goes through `mcp__kirby__install` or offers its built-in `skill-installer`; decline the latter. This checks the guide's warning (`docs/guide.md`, Codex section) still holds; neither outcome fails.

A9 covers, through `codex_server.py`, what the Codex UI cannot: the fixture (Codex does not pass
`GIT_CONFIG_*` to its MCP server), a commit pushed while a dialog is open, a session with no project,
a client without elicitation, unusable dialog wording, and a blocked install (H13, the Codex side of B23).

### Cleanup

What the run installed in `$E2E/home/codex` goes with `$E2E` (Cleanup, step 5). Before that:

- Stop the daemon, which runs from `$E2E/home/codex`: `(. $E2E/iso.sh && codex app-server daemon stop)`,
  then `pkill -f $E2E/home/codex` (a `pid-update-loop` process stays after the stop);
  `pgrep -f $E2E/home/codex` prints nothing.
- Remove the sessions of `codex exec` run from `$E2E`: the files that
  `grep -l '"cwd":"<E2E>"' ~/.codex/sessions/*/*/*/rollout-*.jsonl` lists.
- In the real setup, without `iso.sh`, if C8 or C9 ran opted in and their cleanup did not:
  `codex plugin remove agent-sdk-dev@claude-plugins-official`, `codex mcp remove kirby-e2e`, and
  `codex plugin marketplace remove claude-plugins-official` if Setup did not have it.
- Compare: `diff $E2E/before/codex-config.toml ~/.codex/config.toml`.

## Cleanup

Run all of it, also after a run that stopped early.

1. Exit each agent (its Driving); close its pane (`herdr pane close <id>`).
2. **Check the real logins**: from `$E2E`, without `iso.sh`, run `claude -p ok` and
   `codex exec --skip-git-repo-check ok` (only for the CLIs under test). If one fails to log in,
   restore it (Isolation, Logins).
3. Run each CLI's Cleanup: remove what the run left outside `$E2E`, and check each is gone.
4. **Compare with the starting state**: run the starting-state commands of each CLI's Setup again
   from `$E2E`, without `iso.sh`, diff each against `$E2E/before/`, and run the comparisons in each
   CLI's Cleanup. Anything that differs: report it, do not revert it.
5. `rm -rf $E2E`: it holds the copies of the logins.
6. `git -C $KIRBY status --short` is clean (the run must not touch the repo).

## Report

| ID | Result | Evidence (differing text, transcript line, or why N/A) |
| --- | --- | --- |
| A1 | | |
| … | | |

Above the table: date, `git -C $KIRBY rev-parse HEAD`, the tool versions from Setup, `SHA`, `FX_SHA`,
which agent CLI sections ran, whether the opt-in cases ran, whether a login was renewed before it
was copied, every deviation from this runbook, and the results of Cleanup steps 2 and 4.
