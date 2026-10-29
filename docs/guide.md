# kirby guide

English | [繁體中文](guide.zh-TW.md) | [简体中文](guide.zh-CN.md)

The details behind the [README](../README.md): how kirby is built, what each step of an install does, and how the Codex version differs.

## How it is built

kirby has three parts:

- **The `inhale` skill** searches your stars and star lists (or public GitHub), then judges and recommends skills, plugins or MCP servers that fit the task.
- **A mod** (`hooks/register.ts`, for Claude Code) provides the install tool `mcp__kirby__install`. An install through this tool waits for your answers in two dialogs.
- **An MCP server** (`codex/server.py`, for Codex) provides the search tools and an `install` tool with the same two dialogs.

The skill tells the model to install only through these tools, but that is an instruction, not a block: the model can still run install commands such as `claude mcp add` or `codex mcp add` itself.

## Search

In Claude Code you can invoke the skill directly with `/kirby:inhale`. The model may also use the skill on its own when a task needs it, but that is not guaranteed.

Every repo comes with its star count and last push date, as `owner/repo ★N · pushed DATE`.

### Default source

`stars` (default), `public` or `both`, set as kirby's `default_source` in `/config`. You can also say it in a prompt, e.g. "search public GitHub".

Public search only finds repos tagged with an agent-tooling topic (`agent-skills`, `claude-code-plugin`, `mcp-server`, …).

## Install flow

Once you pick a repo, the mod shows two dialogs:

1. **Next step**: Cancel / Read README first / Pick another / Install. The dialog lists the kind, commit, file count, any bundled scripts and the pre-install check (the scan and the lookups below). When the malware lookup finds a known-malicious package, Install is left out.
2. **Scope** (only after Install):

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | the project's `.claude/skills/`, added to `.gitignore` | `--scope local` (`.claude/settings.local.json`) | `--scope local` |
| `project` | the project's `.claude/skills/`, committed to git | `--scope project` (`.claude/settings.json`) | `--scope project` (`.mcp.json`) |
| `user` | `~/.claude/skills/` (`$CLAUDE_CONFIG_DIR/skills/` when that is set) | `--scope user` | `--scope user` |

Whatever the scope, a plugin's marketplace is recorded in your user settings.

### Scan

Before the first dialog, the tool scans a skill's files, the same ones it installs, for patterns worth a look: hidden Unicode, HTML comments and phrases aimed at the model in Markdown; broad `allowed-tools`; mentions of agent settings and credential files; and in scripts, network calls, shell execution, decoding, secret environment variables and shell startup files. The dialog lists each flagged rule with where it hit, led by its severity: `warn` for `hidden-unicode`, `injection-phrase`, `credentials` and `startup-files`, which are rarer in honest skills, and `info` for the rest; warn rules are listed first. It is a pattern match, not a safety review: a hit is not proof of harm, and no hit is not proof of safety, so no hit blocks an install. A plugin's files are scanned the same way (see Plugins below); MCP servers are not scanned, and the dialog says so. The tool also gives the model the hits with the scanned commit, so you can ask it what a flagged line does. In Claude Code the model reads that file with `gh api`, which the skill does not pre-approve, so unless your permission mode allows it, Claude Code asks you first.

### Advisory and malware lookups

For a skill or a plugin, the pre-install check also looks up published vulnerabilities and known-malicious packages, using only public services that need nothing beyond your `gh` login: [OSV.dev](https://osv.dev) and GitHub.

- **Dependencies.** The tool reads the skill's `package-lock.json` (or `package.json`), `uv.lock`, `requirements.txt` and `pyproject.toml` at the pinned commit. Where there is no lockfile, it works out the versions with `npm install --package-lock-only --ignore-scripts` or `uv pip compile --no-build`, which install nothing and run no package code ([ADR 0004](adr/0004-resolve-dependencies-without-installing.md)). The dialog then says the versions were resolved at check time: they may differ when the skill runs. Without npm or uv only the package names are known, so the malware lookup runs on the names and the advisory lookup is marked unchecked.
- **Advisory lookup.** OSV.dev for each dependency at its version and for the pinned commit itself (OSV matches a commit against the git ranges of its records), and GitHub for the advisories the repo published for itself. A critical or high vulnerability in a dependency, and any record OSV places on the commit, is `danger`; any other vulnerability is `warn`, and so is a repo advisory that cannot be placed on the commit, for which the dialog says it could not tell whether it affects this commit.
- **Malware lookup.** OSV.dev records with a `MAL-` id, which come from OpenSSF Malicious Packages. A hit is `danger` and **blocks** the install: the first dialog offers only Cancel, Read README first and Pick another, and the model tells you why. To install such a tool anyway, you do it by hand. Nothing else blocks: scan hits and vulnerabilities, however severe, are for you to weigh ([ADR 0001](adr/0001-block-only-on-confirmed-malware.md)).
- **Unchecked.** A lookup that fails or runs out of time shows as `unchecked`, never as nothing found, and Install stays available.

The model gets the same findings in every result, so you can ask about one. MCP servers are not looked up yet.

### Plugins

A plugin is checked where its marketplace entry says it comes from, at the marketplace's commit:

- **A folder of the marketplace repo** (`"source": "./plugins/x"`): that folder, at the commit the dialog shows.
- **Another GitHub repo** (`github`, `url` or `git-subdir`): that repo, at the entry's `sha` when it gives one. Without a `sha` it is checked as it stands, and the dialog says the source is not pinned, so what installs may differ from what was checked.
- **Anything else** (an npm package, an archive, a command, a git host other than GitHub): not fetched, and the dialog marks the scan and both lookups unchecked.

The dialog's `source:` line says which it is. The scan and the lookups then run on those files as for a skill, and a known-malicious package blocks the install in the same way.

### Pinned commit

A skill or a plugin installs exactly the commit the dialog showed. If the repo gets a new commit before the install runs, nothing stays installed; the model tells you, and if you still want it, it shows the dialogs again with the new commit. An MCP server is not pinned: it runs whatever its command fetches when it starts, such as `npx -y <package>`.

For a plugin, the commit is the marketplace's ([ADR 0003](adr/0003-verify-plugin-commit-after-adding-marketplace.md)):

- **In both**, neither CLI installs a given commit in a way kirby can use, so the tool adds the marketplace if you do not have it yet (without a ref), installs the plugin, and then reads the commit of the marketplace's clone. If that is not the commit checked, it removes the plugin again and says so; the marketplace stays.
- **Claude Code**, marketplace already added: Claude Code refreshes a marketplace that is behind its repo when it installs from it. So the tool checks the repo's current commit, which is what the install brings, and the dialog says so: `installs from it as it is`, or `behind its repo; installing refreshes it to <commit>`. If the tool cannot tell whether it is behind (GitHub did not answer), the dialog says that as an `unchecked:` line and the check is of the commit your marketplace is at.
- **Codex**, marketplace already added: `codex plugin add` does not refresh it, so the tool checks the commit it is at and installs from it.

A plugin can depend on other plugins, which install along with it. The tool does not check those; the dialog lists them in one `installed along with it, not checked:` line.

### Dialog language

The model writes the dialogs' wording in the language you write in, in the format the skill gives. The facts above it (repo, stars, commit, files, scripts, an existing folder, the scan and the lookups) and the prompt-cache note below the scope question come from the tool, in English. The scope dialog's options are always `cancel`, `local`, `project` and `user`. If the wording is missing or incomplete, the dialogs are in English.

### Installs and the prompt cache

Per the [official docs](https://code.claude.com/docs/en/prompt-caching) and this project's own tests:

- **Skill**: no cache miss after installing (tested).
- **MCP server**: `claude mcp add` takes effect after a restart; the current session's cache is not affected.
- **Plugin**: loads with `/reload-plugins`. Its skills, hooks and the like don't affect the cache. If it brings an MCP server and tool search is off in the session (it is on by default), loading it rebuilds the cache once. Claude Code warns first and applies the reload only with `--force` (tested).

The plugin note is in the scope dialog, from the tool. The MCP note is up to the model: the skill asks it to mention it in the first dialog.

## Codex

The same repo is a Codex plugin. Codex reads `.codex-plugin/plugin.json`, which loads the Codex version of the skill (`codex/skills/inhale/`) and an MCP server (`codex/server.py`, Python standard library only, declared in `mcp.json`). The Claude Code mod is not used there.

What differs from Claude Code:

- **Searches and reads go through MCP tools.** The server's `stars`, `public` and `detect` tools run the same scripts, and its `readme` and `file` tools read a README or one file at a commit from GitHub, all outside Codex's sandbox, so they do not ask for network access each time. These five tools declare that they only read, and with Codex's default approval settings Codex runs them without asking. It still asks before kirby's `install` runs; "Always allow" remembers the answer.
- **The dialogs are MCP elicitations.** The `install` tool shows the same two dialogs. As in Claude Code, the model writes their wording in your language, and the facts stay in English.
- **No `default_source` setting.** The default is `stars`; say "public" or "both" in the prompt.
- **Scopes:**

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | the project's `.agents/skills/`, added to `.gitignore` | — | — |
| `project` | the project's `.agents/skills/`, committed to git | — | — |
| `user` | `~/.agents/skills/` | `codex plugin add` (`~/.codex/config.toml`) | `codex mcp add` (`~/.codex/config.toml`) |

`codex plugin add` and `codex mcp add` have no scope option, so plugins and MCP servers install for the user only. If Codex does not say which project the session is in, a skill can only go to `user` too. In those cases the first dialog adds a line saying where it installs (`installs at: user …`), and the scope dialog's options are `cancel` and `install at user (…)`, so it is a confirmation in the tool's own words.

After installing, start a new Codex session to use what was added.

Codex also reads Claude Code's marketplace format. When a plugin comes from one, the dialog's facts name the marketplace file, and the skill asks the model to note that parts made only for Claude Code (such as hooks) may not work.

If you only say "install owner/repo", Codex may use its built-in `skill-installer` instead, which skips kirby's dialogs (seen in testing). If it asks to run that installer, decline and ask it to install through kirby.

## Scripts

In `skills/inhale/scripts/`. The first three are read-only and run without asking:

| Script | Purpose |
| --- | --- |
| `stars.py` | Reads your stars and star lists (GraphQL), cached in `~/.cache/kirby/stars.json` for 24 hours |
| `public.py` | Searches public GitHub by agent-tooling topic |
| `detect.py` | Tells whether a repo is a marketplace, plugin, skill or MCP server, with what installing it needs |
| `install_skill.py` | Copies a skill folder into the chosen scope's skills directory and records the source commit in `.kirby.json`. `--check` only lists what would be installed, with the scan and the lookups; `--commit` installs only the commit the dialog showed. Called by the mod and the Codex MCP server |
| `check_plugin.py` | The pre-install check of a marketplace plugin: fetches the marketplace (at `--commit` for one already added), follows the plugin's source, and runs the scan and the lookups on its files. Prints JSON; installs nothing. Called by the mod and the Codex MCP server |
| `lookups.py` | The advisory and malware lookups `install_skill.py --check` and `check_plugin.py` run: reads the dependency files, resolves versions without installing, and asks OSV.dev and GitHub. Not run on its own |

`detect.py --agent codex` looks for Codex marketplaces (`.agents/plugins/marketplace.json`) first; `install_skill.py --agent codex` installs into `.agents/skills/`.
