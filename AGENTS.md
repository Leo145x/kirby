# AGENTS.md

## Git Workflow

- **Never push directly to main.** Every change goes on a feature branch, is pushed, and is opened as a PR; it is merged only after review.
- After committing: `git checkout -b feat/xxx` → `git push -u origin feat/xxx` → `gh pr create`.

## Tests

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

`claude plugin test .` runs `tests/dialog.test.ts`; unittest runs `tests/test_codex.py` and `tests/test_install_skill.py`. The end-to-end run is in `tests/e2e/RUNBOOK.md`.

## Tool Change Checklist

kirby's tools live in two places: the Claude Code mod provides `mcp__kirby__install`, and the Codex MCP server provides `stars`, `public`, `detect`, `readme`, `file` and `install`. Whenever a tool is added, removed or renamed, or its parameters change, update all of these files together:

| # | File | What to update |
|---|------|---------|
| 1 | `hooks/register.ts` | `TOOL` (name, description, inputSchema) + the tool name bound in `tool.call` |
| 2 | `codex/server.py` | the `TOOLS` list + the dispatch (`if name == …` / `SEARCHES`) |
| 3 | `skills/inhale/SKILL.md` | frontmatter `allowed-tools` + how section 4 calls the tool and its parameters |
| 4 | `codex/skills/inhale/SKILL.md` | the tool list in the opening **Tools.** paragraph + how each step calls the tools |
| 5 | `tests/test_codex.py` | tests of the server's input checks |
| 6 | `tests/e2e/codex_server.py` | the calls and expected results of H1–H12 |
| 7 | `tests/e2e/RUNBOOK.md` | the tool list in A4 + each case's calls and expected results |
| 8 | `README.md`, `README.zh-TW.md`, `README.zh-CN.md` | the three parts at the top + the tool description in the Codex section |

## Install Results and Dialogs Checklist

The strings the install tool returns to the model (`not installed: …`, `installed (scope …)`, `install failed …`, `scan:`) and the dialog rules exist once on each side; change one side, change the other:

| # | File | What to update |
|---|------|---------|
| 1 | `hooks/register.ts` ↔ `codex/server.py` | result strings, notes such as `*_NOT_SCANNED` |
| 2 | `hooks/dialog.ts` ↔ `codex/dialog.py` | `english()`, the `MAX` length limits, the rules in `readDialog` / `read_dialog` |
| 3 | `tests/dialog.test.ts` ↔ `tests/test_codex.py` | tests of the dialog rules |
| 4 | `skills/inhale/SKILL.md`, `codex/skills/inhale/SKILL.md` | the `dialog` format, Limits, and each result under Act on the result |
| 5 | `tests/e2e/codex_server.py`, `tests/e2e/RUNBOOK.md` | expected results checked word for word |
| 6 | `README.md`, `README.zh-TW.md`, `README.zh-CN.md` | the Install flow section |

## Scan Rules Checklist

When a scan rule in `install_skill.py` is added, removed or renamed:

| # | File | What to update |
|---|------|---------|
| 1 | `skills/inhale/scripts/install_skill.py` | `RULES` |
| 2 | `tests/test_install_skill.py` | the expected rule, file and line of each hit |
| 3 | `tests/e2e/fixture.py` | the fixture's files, so they hit every rule |
| 4 | `tests/e2e/RUNBOOK.md` | the rule count and the cases that use it |
| 5 | `skills/inhale/SKILL.md`, `codex/skills/inhale/SKILL.md` | the list of what each rule matches |
| 6 | `README.md`, `README.zh-TW.md`, `README.zh-CN.md` | the paragraph on the scan |

## Scripts Checklist

When the arguments or output format of `skills/inhale/scripts/*.py` change:

| # | File | What to update |
|---|------|---------|
| 1 | `skills/inhale/scripts/*.py` | arguments and output |
| 2 | `hooks/register.ts` | the arguments it passes to `install_skill.py` and `detect.py`, and the JSON fields it reads |
| 3 | `codex/server.py` | the arguments it passes to each script, and how it parses the output |
| 4 | `skills/inhale/SKILL.md` | usage and output in sections 1a, 1b and 2 |
| 5 | `tests/test_install_skill.py`, `tests/e2e/scripts_check.py` | the matching tests and format checks |
| 6 | `README.md`, `README.zh-TW.md`, `README.zh-CN.md` | the Scripts table |

## Plugin Metadata Checklist

| # | File | What to update |
|---|------|---------|
| 1 | `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json` | description (the same text in all three) |
| 2 | `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `codex/server.py` | version (`serverInfo` carries it too) |
| 3 | `tests/e2e/RUNBOOK.md` | the `serverInfo` version in A4 + the version in the Codex plugin cache path |

## README

`README.md`, `README.zh-TW.md` and `README.zh-CN.md` say the same thing; when one changes, update the other two.

Missing any of these leaves the docs out of step with what the code does. Check each one before opening a PR.
