# kirby guide

English | [繁體中文](guide.zh-TW.md) | [简体中文](guide.zh-CN.md)

The details behind the [README](../README.md): how kirby is built, what each step of an install does, and how the Codex version differs.

## How it is built

kirby has three parts:

- **The `inhale` skill** searches your stars and star lists (or public GitHub), then judges and recommends skills, plugins or MCP servers that fit the task.
- **A mod** (`hooks/register.ts`, for Claude Code) provides the install tool `mcp__kirby__install`, two read-only tools for the model review (`mcp__kirby__check`, which runs the pre-install check without a dialog, and `mcp__kirby__file`, which reads one file where the check read it) and the reviewer agent `kirby:reviewer`, which can use only those two. kirby lets the two read-only tools run without a permission prompt. An install through the install tool waits for your answers in two dialogs.
- **An MCP server** (`codex/server.py`, for Codex) provides the search tools, the same `check` and `file` tools, and an `install` tool with the same two dialogs.

The skill tells the model to install only through these tools, but that is an instruction, not a block: the model can still run install commands such as `claude mcp add` or `codex mcp add` itself.

## Search

In Claude Code you can invoke the skill directly with `/kirby:inhale`. The model may also use the skill on its own when a task needs it, but that is not guaranteed.

Every repo comes with its star count and last push date, as `owner/repo ★N · pushed DATE`.

### Default source

`stars` (default), `public` or `both`, set as kirby's `default_source` in `/config`. You can also say it in a prompt, e.g. "search public GitHub".

Public search only finds repos tagged with an agent-tooling topic (`agent-skills`, `claude-code-plugin`, `mcp-server`, …).

## Install flow

Once you pick a repo, the mod shows two dialogs:

1. **Next step**: Cancel / Read README first / Pick another / Install. The dialog lists the kind, commit, file count, any bundled scripts and the pre-install check (the scan, the lookups and, when they found something, the model review below). When the check finds nothing and nothing went unscanned or unchecked, that is one line, such as `check: nothing found (12 files, 3 npm dependencies, advisory and malware lookups)`; otherwise each part has its own lines. When the malware lookup finds a known-malicious package, Install is left out.
2. **Scope** (only after Install):

| scope | skill | plugin | MCP |
| --- | --- | --- | --- |
| `local` | the project's `.claude/skills/`, added to `.gitignore` | `--scope local` (`.claude/settings.local.json`) | `--scope local` |
| `project` | the project's `.claude/skills/`, committed to git | `--scope project` (`.claude/settings.json`) | `--scope project` (`.mcp.json`) |
| `user` | `~/.claude/skills/` (`$CLAUDE_CONFIG_DIR/skills/` when that is set) | `--scope user` | `--scope user` |

Whatever the scope, a plugin's marketplace is recorded in your user settings.

### Scan

Before the first dialog, the tool scans a skill's files, the same ones it installs, for patterns worth a look: hidden Unicode, HTML comments and phrases aimed at the model in Markdown; broad `allowed-tools`; mentions of agent settings and credential files; and in scripts, network calls, shell execution, decoding, secret environment variables and shell startup files. The dialog lists each flagged rule with where it hit, led by its severity: `warn` for `hidden-unicode`, `injection-phrase`, `credentials` and `startup-files`, which are rarer in honest skills, and `info` for the rest; warn rules are listed first. One tool hitting `network` together with `env-secret`, `exec` or `decode`, in any of its files, also gets a `warn` finding that names the pair: `send-secrets` (may send secrets out), `download-run` (may download and run code) and `download-decode` (may download and decode a payload). Each of those rules alone stays `info`, so a skill that reads a secret and sends it out is not all `info` ([ADR 0005](adr/0005-one-click-by-default.md)); these findings are listed first. It is a pattern match, not a safety review: a hit is not proof of harm, and no hit is not proof of safety, so no hit blocks an install. A plugin's files are scanned the same way (see Plugins below), and so is the published package an MCP server's command runs (see MCP servers below). The tool also gives the model the hits with the scanned commit, so you can ask it what a flagged line does. The model reads that file at that commit with kirby's read-only `file` tool.

### Advisory and malware lookups

For a skill, a plugin or an MCP server, the pre-install check also looks up published vulnerabilities and known-malicious packages, using only public services that need nothing beyond your `gh` login: [OSV.dev](https://osv.dev) and GitHub.

- **Dependencies.** The tool reads the skill's `package-lock.json` (or `package.json`), `uv.lock`, `requirements.txt` and `pyproject.toml` at the pinned commit. Where there is no lockfile, it works out the versions with `npm install --package-lock-only --ignore-scripts` or `uv pip compile --no-build`, which install nothing and run no package code ([ADR 0004](adr/0004-resolve-dependencies-without-installing.md)). The dialog then says the versions were resolved at check time: they may differ when the skill runs. Without npm or uv only the package names are known, so the malware lookup runs on the names and the advisory lookup is marked unchecked.
- **Advisory lookup.** OSV.dev for each dependency at its version and for the pinned commit itself (OSV matches a commit against the git ranges of its records), and GitHub for the advisories the repo published for itself. A critical or high vulnerability in a dependency, and any record OSV places on the commit, is `danger`; any other vulnerability is `warn`, and so is a repo advisory that cannot be placed on the commit, for which the dialog says it could not tell whether it affects this commit.
- **Malware lookup.** OSV.dev records with a `MAL-` id, which come from OpenSSF Malicious Packages. A hit is `danger` and **blocks** the install: the first dialog offers only Cancel, Read README first and Pick another, and the model tells you why. To install such a tool anyway, you do it by hand. Nothing else blocks: scan hits and vulnerabilities, however severe, are for you to weigh ([ADR 0001](adr/0001-block-only-on-confirmed-malware.md)).
- **Unchecked.** A lookup that fails or runs out of time shows as `unchecked`, never as nothing found, and Install stays available.

The model gets the same findings in every result, so you can ask about one.

### Model review

When the scan or the lookups find a `danger` or `warn` finding (a combination finding included), a model also reads the files and reports what looks harmful ([ADR 0002](adr/0002-model-review-in-a-subagent.md)). A tool where they find nothing, or only `info` hits, gets no review, so it costs no extra wait or tokens. Neither does a blocked install: Install is not offered anyway.

- **The flow.** Before the install tool, the model calls the `check` tool, which runs the same pre-install check without a dialog and says whether a review is needed, where the files are (the repo at the commit checked, or an MCP server's package) and which files they are. If a review is needed, the model starts a subagent: in Claude Code kirby's reviewer agent `kirby:reviewer` with the Agent tool, in Codex a subagent with its multi-agent tools and a fixed prompt from the skill. The subagent reads the files only through the `file` tool, at that commit or from that package, and is not told what the other checks found, so it reviews the files on its own. Then the model calls the install tool with the review's result and the sha the check gave.
- **The reviewer in Claude Code.** `kirby:reviewer` can use only `check` and `file`, so even if a reviewed file carries instructions aimed at it, it has no Bash or write tool to misuse. Its instructions are its own; the model gives it only where the files are and which. kirby's hook allows `check` and `file` without a permission prompt, and nothing else: they only read GitHub and package contents and write nothing to your machine. A deny rule in your settings or your organization's still stops them. In Codex the tools declare themselves read-only, so Codex runs them without asking.
- **What is reviewed.** What gets installed: a skill's files, a plugin's source (also in another repo), or, for an MCP server, the published package the check unpacked. For a package, `file` downloads the same archive again, checks it against the registry's hash and against the sha256 the check gave, and unpacks it into a temporary folder; nothing in it is installed or run.
- **The result.** At most 5 findings, each a file the check listed, a line number, and a one-sentence reason of at most 120 characters that does not quote the file; or `could_not_run` with a reason. The install tool checks that structure, strips hidden and control characters, and refuses a result outside it before any dialog opens, so the model sends it again.
- **In the dialog.** Each finding is a `warn` line after the check's lines, labelled `(model review, as reported by the model)`, or one line says the review found nothing. A review finding only adds: it never removes or lowers another finding, and it never blocks.
- **Missing review.** The install tool decides from its own check whether a review was needed. If one was and none was passed, the review could not run, or it read another commit than the one checked, the dialog says `model review: unchecked (…)` in one line, and Install stays available ([ADR 0005](adr/0005-one-click-by-default.md)).

The model passes the result on, so kirby cannot prove that the review was not edited on the way or skipped; that is why its findings are labelled as reported by the model.

### Plugins

A plugin is checked where its marketplace entry says it comes from, at the marketplace's commit:

- **A folder of the marketplace repo** (`"source": "./plugins/x"`): that folder, at the commit the dialog shows.
- **Another GitHub repo** (`github`, `url` or `git-subdir`): that repo, at the entry's `sha` when it gives one. Without a `sha` it is checked as it stands, and the dialog says the source is not pinned, so what installs may differ from what was checked.
- **Anything else** (an npm package, an archive, a command, a git host other than GitHub): not fetched, and the dialog marks the scan and both lookups unchecked.

The dialog's `source:` line says which it is. The scan and the lookups then run on those files as for a skill, and a known-malicious package blocks the install in the same way.

### MCP servers

An MCP server runs the package its command fetches when it starts (`npx -y <package>`, `uvx <package>`), so the check is of that package, not of the repo's files:

- **Which package.** The repo is read only to learn which packages it names: the `packages` of a `server.json`, then the `name` of a `package.json` (not a private one), then that of a `pyproject.toml`, at the root or up to two folders down, so a repo that holds several servers works too. The tool checks the one the command runs. Nothing ties a package to a repo (the MCP registry checks a package against the server's name, not against its repo), so the dialog's `package:` line says which file names it and that it is not verified to come from this repo.
- **Which version.** The one the command asks for (`pkg@1.2.3`, `pkg==1.2.3`, a tag such as `pkg@next`), else the one `server.json` gives, else the registry's latest.
- **What is checked.** That version's npm tarball, or its PyPI wheel for every platform (else its sdist), downloaded from the registry, checked against the registry's hash and unpacked into a temporary folder: regular files only, nothing outside that folder, and nothing installed, imported or run. The scan runs on those files. The lookups run on the package itself at that version (any advisory for it is `danger`) and on what it depends on, resolved as for a skill ([ADR 0004](adr/0004-resolve-dependencies-without-installing.md)). Of the advisories the repo published for itself, only those that name this package, or no package, count.
- **Pinning.** The command is rewritten to that version (`npx -y pkg@1.2.3`, `uvx pkg==1.2.3`), and the dialog shows the rewritten command. Only that package is pinned: its dependencies are resolved when the check runs and may differ when the server starts, and the dialog's `pinned:` line says so. An MCP server therefore does not install exactly what was checked, as a skill does.
- **Unchecked.** A container image (`docker run …`), a remote server at a URL, a repo that names no npm or PyPI package, and a command that runs none of the packages the repo names are not checked: one `unchecked:` line says why, and the command stays as given. If the tool cannot tell which version the command gets (the registry does not answer, or the command asks for a range such as `pkg@^1.2`), the dialog says `not pinned:`, the scan is unchecked, and only the malware lookup runs, on the package's name.

The hits are paths inside the package. When the model has the `check` tool's answer for it, it reads them with the `file` tool from the package checked (see Model review above); otherwise it tells you where to read the file (unpkg for npm, inspector.pypi.io for PyPI).

### Pinned commit

A skill installs exactly the commit the dialog showed, even if the repo gets a new commit before the install runs: kirby fetches that commit itself, so you do not have to answer the dialogs again ([ADR 0005](adr/0005-one-click-by-default.md)). Only if that commit can no longer be fetched (a force-push can remove one) does the install fail; nothing is installed, the result says why, and if you still want it, the model shows the dialogs again with the current commit. A plugin installs from the marketplace commit the dialog showed (below). An MCP server's command is pinned to the package version checked, but not its dependencies (see MCP servers above).

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

- **Searches and reads go through MCP tools.** The server's `stars`, `public` and `detect` tools run the same scripts, its `readme` and `file` tools read a README or one file at a commit from GitHub (or, for the model review, from an MCP server's package), and its `check` tool runs the pre-install check without a dialog, all outside Codex's sandbox, so they do not ask for network access each time. These six tools declare that they only read, and with Codex's default approval settings Codex runs them without asking. It still asks before kirby's `install` runs; "Always allow" remembers the answer.
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
| `install_skill.py` | Copies a skill folder into the chosen scope's skills directory and records the source commit in `.kirby.json`. `--check` only lists what would be installed, with the scan and the lookups (with `--json`, the dialog's lines are `check_lines`, and `review` says whether the model review runs and which files it reads); `--commit` installs the commit the dialog showed, even if the repo has moved on. Called by the mod and the Codex MCP server |
| `check_plugin.py` | The pre-install check of a marketplace plugin: fetches the marketplace (at `--commit` for one already added), follows the plugin's source, and runs the scan and the lookups on its files. Prints JSON, with `review` as above; installs nothing. Called by the mod and the Codex MCP server |
| `check_mcp.py` | The pre-install check of an MCP server: `check_mcp.py owner/repo '<mcp_args as JSON>'` finds which package the repo names and the command runs, downloads and unpacks that version without installing it, and runs the scan and the lookups on it. Prints JSON, with the command pinned to that version as `mcp_args` and `review` as above (its `sha` is the archive's sha256). `check_mcp.py --read '<JSON>'` prints one file of such a package for the `file` tool. Installs nothing. Called by the mod and the Codex MCP server |
| `lookups.py` | The advisory and malware lookups `install_skill.py --check`, `check_plugin.py` and `check_mcp.py` run: reads the dependency files, resolves versions without installing, and asks OSV.dev and GitHub. Not run on its own |

`detect.py --agent codex` looks for Codex marketplaces (`.agents/plugins/marketplace.json`) first; `install_skill.py --agent codex` installs into `.agents/skills/`.
