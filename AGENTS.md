# AGENTS.md

## Git Workflow

- **Never push directly to main.** Every change goes on a feature branch, is pushed, and is opened as a PR; it is merged only after review.
- After committing: `git checkout -b feat/xxx` → `git push -u origin feat/xxx` → `gh pr create`. Name the branch `feat/` for a feature, `fix/` for a bug fix, or `docs/` for a docs-only change.
- Branches that are never merged are the exception: `research/<name>` (from `/wayfinder`) and `prototype/<name>` (from `/prototype`) may be pushed without a PR. Nothing on them reaches main.

## Tests

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

`claude plugin test .` runs `tests/dialog.test.ts`, `tests/check.test.ts`, `tests/plugin.test.ts`, `tests/register.test.ts` and `tests/rows.test.ts`; unittest runs `tests/test_codex.py`, `tests/test_install_skill.py`, `tests/test_lookups.py`, `tests/test_check_plugin.py` and `tests/test_check_mcp.py`. The end-to-end run is in `tests/e2e/RUNBOOK.md`.

## Before Every Commit

1. **Run the tests for every supported agent CLI.** kirby currently supports Claude Code and Codex; a commit is made only after the tests of both pass. Always run the unit tests of both. Then run the end-to-end cases in `tests/e2e/RUNBOOK.md` that exercise what the commit changes, on every agent CLI the change reaches. How many cases that takes depends on the change, not on a fixed level: pick the cases that would fail if the change were wrong.

   | Agent CLI | Unit tests (always) | End-to-end cases to pick from (`tests/e2e/RUNBOOK.md`) |
   |-----------|-------|------------|
   | Claude Code | `claude plugin validate .`, `claude plugin test .` | section A + section B |
   | Codex | `python3 -B -m unittest discover -s tests` (`tests/test_codex.py`, plus `tests/test_install_skill.py`, `tests/test_lookups.py`, `tests/test_check_plugin.py` and `tests/test_check_mcp.py` for the shared scripts) | section A + section C |

   When kirby adds support for another agent CLI, add a row for it here, its tests to the Tests section, and its section to `tests/e2e/RUNBOOK.md` (see Adding an agent CLI there).

2. **Then check the READMEs and the guide.** Read `README.md`, `README.zh-TW.md` and `README.zh-CN.md` for any new feature in the commit that their Features list does not mention yet, and add it to all three in a line or two. Put how it works in `docs/guide.md`, `docs/guide.zh-TW.md` and `docs/guide.zh-CN.md`. A bug fix does not get its own entry; add only what other people need to know about it (for example, a changed behaviour or a step they now have to take).

## Tool Change Checklist

kirby's tools live in two places: the Claude Code mod provides `mcp__kirby__check`, `mcp__kirby__file` and `mcp__kirby__install`, and the Codex MCP server provides `stars`, `public`, `detect`, `readme`, `file`, `check` and `install`. Whenever a tool is added, removed or renamed, or its parameters change, update all of these files together:

| # | File | What to update |
|---|------|---------|
| 1 | `hooks/register.ts`, `hooks/check.ts` | `TOOL`, `CHECK`, `FILE` (name, description, inputSchema) + the tool names bound in `tool.call`; `check.ts`'s input checks and the `check` result; `READ_ONLY_TOOLS` (the tools the `tool.check` hook allows and the reviewer agent can use) and `REVIEWER` (the reviewer agent's prompt) |
| 2 | `codex/server.py` | the `TOOLS` list + the dispatch (`if name == …` / `SEARCHES`) |
| 3 | `skills/inhale/SKILL.md` | frontmatter `allowed-tools` + how section 4 calls the tools and their parameters, and how it starts `kirby:reviewer` |
| 4 | `codex/skills/inhale/SKILL.md` | the tool list in the opening **Tools.** paragraph + how each step calls the tools, and the review prompt |
| 5 | `tests/test_codex.py`, `tests/check.test.ts`, `tests/register.test.ts` | tests of each side's input checks and of the `check` result; the reviewer agent's tools and the tools allowed without a prompt |
| 6 | `tests/e2e/codex_server.py` | the calls and expected results of H1–H14 |
| 7 | `tests/e2e/RUNBOOK.md` | the tool list in A4 + each case's calls and expected results |
| 8 | `docs/guide.md`, `docs/guide.zh-TW.md`, `docs/guide.zh-CN.md` | the three parts under How it is built + the tool description in the Codex section |

## Install Results and Dialogs Checklist

The strings the install tool returns to the model (`not installed: …`, `installed (scope …)`, `install failed …`, `scan:`, `review:`) and the dialog rules, the model review's among them, exist once on each side; change one side, change the other:

| # | File | What to update |
|---|------|---------|
| 1 | `hooks/register.ts`, `hooks/plugin.ts` ↔ `codex/server.py` | result strings, notes such as `*_NOT_SCANNED` |
| 1a | `hooks/rows.ts`, `tests/rows.test.ts` | the result line shown in Claude Code's transcript, which reads the start of each result |
| 2 | `hooks/dialog.ts` ↔ `codex/dialog.py` | `english()`, the `MAX` and `REVIEW_MAX` limits, the rules in `readDialog` / `read_dialog` and `readReview` / `read_review`, `clean`, `reviewNote` / `review_note` |
| 3 | `tests/dialog.test.ts`, `tests/plugin.test.ts` ↔ `tests/test_codex.py` | tests of the dialog and review rules and of a plugin's install steps |
| 4 | `skills/inhale/SKILL.md`, `codex/skills/inhale/SKILL.md`, `hooks/check.ts` (`REVIEWER`) | the `dialog` format, the review prompt's result format, Limits, and each result under Act on the result |
| 5 | `tests/e2e/codex_server.py`, `tests/e2e/RUNBOOK.md` | expected results checked word for word |
| 6 | `docs/guide.md`, `docs/guide.zh-TW.md`, `docs/guide.zh-CN.md` | the Install flow section (and the README Features list, if a feature it names changes) |

## Scan Rules Checklist

When a scan rule in `install_skill.py` is added, removed or renamed, or its severity changes:

| # | File | What to update |
|---|------|---------|
| 1 | `skills/inhale/scripts/install_skill.py` | `RULES` |
| 2 | `tests/test_install_skill.py` | the expected rule, file and line of each hit, and each rule's severity |
| 3 | `tests/e2e/fixture.py` | the fixture's files, so they hit every rule |
| 4 | `tests/e2e/RUNBOOK.md` | the rule count and the cases that use it |
| 5 | `skills/inhale/SKILL.md`, `codex/skills/inhale/SKILL.md` | the list of what each rule matches |
| 6 | `docs/guide.md`, `docs/guide.zh-TW.md`, `docs/guide.zh-CN.md` | the Scan section (and the examples in the README Features list's scan line, if one of them changes) |

## Scripts Checklist

When the arguments or output format of `skills/inhale/scripts/*.py` change:

| # | File | What to update |
|---|------|---------|
| 1 | `skills/inhale/scripts/*.py` | arguments and output |
| 2 | `hooks/register.ts`, `hooks/check.ts` | the arguments they pass to `install_skill.py`, `check_plugin.py` and `check_mcp.py` (its `--read` too), and the JSON fields they read (`review` among them) |
| 3 | `codex/server.py` | the arguments it passes to each script, and how it parses the output |
| 4 | `skills/inhale/SKILL.md` | usage and output in sections 1a, 1b and 2 |
| 5 | `tests/test_install_skill.py`, `tests/test_lookups.py`, `tests/test_check_plugin.py`, `tests/test_check_mcp.py`, `tests/e2e/scripts_check.py` | the matching tests and format checks |
| 6 | `docs/guide.md`, `docs/guide.zh-TW.md`, `docs/guide.zh-CN.md` | the Scripts table |

## Plugin Metadata Checklist

| # | File | What to update |
|---|------|---------|
| 1 | `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json` | description (the same text in all three) |
| 2 | `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `codex/server.py` | version (`serverInfo` carries it too) |
| 3 | `tests/e2e/RUNBOOK.md` | the `serverInfo` version in A4 + the version in the Codex plugin cache path |

## README and guide

`README.md` is the quick start: what kirby is for, its features, requirements and install. It is not a manual; how things work goes in `docs/guide.md`.

`README.md`, `README.zh-TW.md` and `README.zh-CN.md` say the same thing, and so do `docs/guide.md`, `docs/guide.zh-TW.md` and `docs/guide.zh-CN.md`; when one changes, update the other two.

Missing any of these leaves the docs out of step with what the code does. Check each one before opening a PR.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for Leo145x/kirby, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
