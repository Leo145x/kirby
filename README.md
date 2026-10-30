# kirby

[![M8ven Score](https://m8ven.ai/badge/mcp/leo145x-kirby-1trnl2?v=28c193f5aba552f95702e44af0339b36)](https://m8ven.ai/mcp/leo145x-kirby-1trnl2?s=readme)

English | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

Ask your agent for a tool: kirby finds the right skill, plugin or MCP server among your GitHub stars, and checks what it would install before you confirm.

## What it's for

kirby does two things, one after the other.

**It finds the tool.** You star agent tools on GitHub and sort them into star lists. When a task needs one, just ask in Claude Code or Codex: kirby searches your stars and star lists (or public GitHub), recommends what fits the task, and installs your pick without you leaving the session.

**It checks the tool before you install it.** Before the install dialog opens, kirby looks at what would be installed: it scans the files, looks up known vulnerabilities and malware in the tool and its dependencies, and, when that turns something up, has a model review the files. You see each finding in the dialog, so you know what you are installing. Installing stays one click; only a known-malicious package stops it.

## Features

### Finding a tool

- **Searches your stars first**: your GitHub stars and star lists, public GitHub (repos tagged with an agent-tooling topic), or both.
- **Recommends what fits**: the model judges each candidate against your task, and every repo comes with its star count and last push date.
- **Knows what it is installing**: tells a marketplace, plugin, skill or MCP server apart, and what installing it needs.

### Checking it before install

- **Scans the files that would be installed**: a skill's files, a plugin's own files (also in another repo), or the published npm or PyPI package an MCP server's command runs, downloaded but never installed or run. It looks for patterns worth a look, such as hidden Unicode, phrases aimed at the model, network calls or secret environment variables. It is a pattern match, not a safety review; ask the model what a flagged line does.
- **Looks up known vulnerabilities and malware**: in the tool and its dependencies, on OSV.dev and in the repo's own GitHub advisories.
- **Has a model review the files when something was found**: when the scan or the lookups find a danger or warn finding, a subagent that can only read (in Claude Code, kirby's reviewer agent) reports up to five findings, labelled as reported by the model.
- **Summed up by severity**: each danger finding on a line of its own with its ids, the warn findings on one line by name, the info ones left out (the model still gets every finding). A part that could not run says unchecked, never nothing found, and a clean tool gets a single `✓ check: nothing found` line.
- **One click by default**: no finding asks for an extra step. Only a known-malicious package blocks the install.
- **Installs what you saw**: a skill installs the commit the dialog showed, even if the repo has moved on; a plugin is removed again if its marketplace is not at the commit checked; an MCP server's command is pinned to the package version checked (its dependencies are not).

### Installing

- **Asks before installing**: nothing is installed until you pick Install in a dialog, where you can also read the README first or pick another. Then you choose the scope: `local`, `project` or `user`.
- **Speaks your language**: the dialogs are written in the language you write in. kirby words the facts in them itself, in English, 繁體中文 or 简体中文; the model only picks the language.
- **Keeps your prompt cache**: in Claude Code, installing a skill, plugin or MCP server does not cost you the prompt cache (tested). The one exception, a plugin that brings an MCP server and is loaded with `/reload-plugins` while tool search is off, is flagged in the dialog, and Claude Code itself warns before that reload.
- **Works in Claude Code and Codex**.

## Requirements

- The [`gh`](https://cli.github.com/) CLI, logged in (`gh auth login`)
- `git`
- `python3` (3.11 or later to read `uv.lock` and `pyproject.toml`)
- Optional: `npm` and `uv`, so the lookups can work out the versions of dependencies that have no lockfile; without them only the names are looked up

## Quick start

Claude Code:

```
claude plugin marketplace add Leo145x/kirby
claude plugin install kirby@kirby
```

Codex:

```
codex plugin marketplace add Leo145x/kirby
codex plugin add kirby@kirby
```

Then just ask, for example:

- "Is there a skill that draws architecture diagrams?"
- "Find a code review tool in my AI Tools list"
- "Search public GitHub for an MCP server that queries Postgres"

In Claude Code you can also call it with `/kirby:inhale`.

## Learn more

The [guide](docs/guide.md) covers the details: the search source setting; the pre-install check, with what each part checks, the severities, what blocks, the model review and what is pinned; each step of the install flow and where each scope installs; the prompt cache; how the Codex version differs; and the scripts.

## Development

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

## License

[MIT](LICENSE)
