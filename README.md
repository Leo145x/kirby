# kirby

[![M8ven Score](https://m8ven.ai/badge/mcp/leo145x-kirby-1trnl2?v=28c193f5aba552f95702e44af0339b36)](https://m8ven.ai/mcp/leo145x-kirby-1trnl2?s=readme)

English | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

Ask your agent for a tool, and kirby finds the right skill, plugin or MCP server among your GitHub stars, then installs it once you confirm.

## What it's for

You star agent tools on GitHub and sort them into star lists. When a task needs one, just ask in Claude Code or Codex: kirby searches your stars and star lists (or public GitHub), recommends what fits the task, and installs your pick without you leaving the session.

## Features

- **Searches your stars first**: your GitHub stars and star lists, public GitHub (repos tagged with an agent-tooling topic), or both.
- **Recommends what fits**: the model judges each candidate against your task, and every repo comes with its star count and last push date.
- **Knows what it is installing**: tells a marketplace, plugin, skill or MCP server apart, and what installing it needs.
- **Asks before installing**: nothing is installed until you pick Install in a dialog, where you can also read the README first or pick another. Then you choose the scope: `local`, `project` or `user`.
- **Scans a skill before installing**: looks for patterns worth a look, such as hidden Unicode, phrases aimed at the model, network calls or secret environment variables, and lists each hit in the dialog. Ask the model what a flagged line does. It is a pattern match, not a safety review; plugins and MCP servers are not scanned.
- **Installs the commit you saw**: a skill installs exactly the commit the dialog showed; if the repo changes before the install runs, nothing is installed.
- **Speaks your language**: the dialogs are written in the language you write in.
- **Keeps your prompt cache**: in Claude Code, installing a skill, plugin or MCP server does not cost you the prompt cache (tested). The one exception, a plugin that brings an MCP server and is loaded with `/reload-plugins` while tool search is off, is flagged in the dialog, and Claude Code itself warns before that reload.
- **Works in Claude Code and Codex**.

## Requirements

- The [`gh`](https://cli.github.com/) CLI, logged in (`gh auth login`)
- `git`
- `python3`

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

The [guide](docs/guide.md) covers the details: the search source setting, each step of the install flow, where each scope installs, what the scan matches, the prompt cache, how the Codex version differs, and the scripts.

## Development

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

## License

[MIT](LICENSE)
