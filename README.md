# kirby

English | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

Finds the right skill, plugin or MCP server among your GitHub stars and star lists, or through a public GitHub search, and installs it at the scope you pick once you confirm.

It has two parts:

- **The `inhale` skill** searches your stars and star lists (or public GitHub), then judges and recommends skills, plugins or MCP servers that fit the task.
- **A mod** (`hooks/register.ts`) provides the install tool `mcp__kirby__install`. An install through this tool waits for your answers in two dialogs. The skill tells the model to install only through it, but that is an instruction, not a block: the model can still run install commands such as `claude mcp add` with Bash.

Claude Code only.

## Requirements

- The [`gh`](https://cli.github.com/) CLI, logged in (`gh auth login`)
- `git`
- `python3`

## Install

```
claude plugin marketplace add Leo145x/kirby
claude plugin install kirby@kirby
```

## Usage

Just ask, for example:

- "Is there a skill that draws architecture diagrams?"
- "Find a code review tool in my AI Tools list"
- "Search public GitHub for an MCP server that queries Postgres"

Or invoke it directly with `/kirby:inhale`. The model may also use the skill on its own when a task needs it, but that is not guaranteed.

Every repo comes with its star count and last push date, as `owner/repo ★N · pushed DATE`.

### Default source

`stars` (default), `public` or `both`, set as kirby's `default_source` in `/config`. You can also say it in a prompt, e.g. "search public GitHub".

Public search only finds repos tagged with an agent-tooling topic (`agent-skills`, `claude-code-plugin`, `mcp-server`, …).

### Install flow

Once you pick a repo, the mod shows two dialogs:

1. **Next step**: Cancel / Read README first / Pick another / Install. The dialog lists the kind, commit, file count and any bundled scripts.
2. **Scope** (only after Install):

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | the project's `.claude/skills/`, added to `.gitignore` | `--scope local` (`.claude/settings.local.json`) | `--scope local` |
| `project` | the project's `.claude/skills/`, committed to git | `--scope project` (`.claude/settings.json`) | `--scope project` (`.mcp.json`) |
| `user` | `~/.claude/skills/` | `--scope user` | `--scope user` |

Whatever the scope, a plugin's marketplace is recorded in your user settings.

The dialogs follow Claude Code's `language` setting (e.g. `"zh-TW"`, `"简体中文"`), or `LC_ALL` / `LANG` when it is unset. They are in English, Traditional Chinese or Simplified Chinese; any other language gets English.

### Installs and the prompt cache

Per the [official docs](https://code.claude.com/docs/en/prompt-caching) and this project's own tests:

- **Skill**: no cache miss after installing (tested).
- **MCP server**: `claude mcp add` takes effect after a restart; the current session's cache is not affected.
- **Plugin**: loads with `/reload-plugins`. Its skills, hooks and the like don't affect the cache. If it brings an MCP server and tool search is off in the session (it is on by default), loading it rebuilds the cache once. Claude Code warns first and applies the reload only with `--force` (tested).

The scope dialog shows the matching note.

## Scripts

In `skills/inhale/scripts/`. The first three are read-only and run without asking:

| Script | Purpose |
| --- | --- |
| `stars.py` | Reads your stars and star lists (GraphQL), cached in `~/.cache/kirby/stars.json` for 24 hours |
| `public.py` | Searches public GitHub by agent-tooling topic |
| `detect.py` | Tells whether a repo is a marketplace, plugin, skill or MCP server, with what installing it needs |
| `install_skill.py` | Copies a skill folder into the chosen scope's skills directory and records the source commit in `.kirby.json`. `--check` only lists what would be installed. Called by the mod |

## Development

```
claude plugin validate .
claude plugin test .
```

## License

[MIT](LICENSE)
