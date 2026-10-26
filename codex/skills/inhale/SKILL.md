---
name: inhale
description: Recommend agent skills, plugins or MCP servers from the user's own GitHub stars and star lists, or from public GitHub search, and install the chosen one for Codex at the scope the user picks. Use when a task needs a capability this session lacks, or the user asks whether a skill/plugin/MCP exists for something, or asks to search their GitHub stars / star lists, or asks to install a skill, plugin or MCP server from a GitHub repo (找 skill、找 plugin、找 MCP、從我的 star 找、從公開的找、安裝這個 repo、从我的 star 找、从公开的找、安装这个 repo).
---

# Find a tool for the task

The user curates agent tooling by starring repos on GitHub and grouping them into star lists. Instead of installing everything up front, find the right repo when it is needed and install it where the user chooses.

**Tools.** Everything goes through the tools of the `kirby` MCP server: `stars`, `public`, `detect`, `readme` and `install`. They run outside the sandbox, so do not call GitHub with shell commands, and do not run the Python scripts in this plugin yourself. If a tool fails with `Is \`gh auth login\` done?`, tell the user to run `gh auth login` in a terminal.

## 0. Pick the source

The default source is `stars`. The user's wording overrides it for this request: "from my stars / my list" → `stars`; "public", "on GitHub", "anything out there" → `public`; "both / everywhere" → `both`.

With `stars`, if nothing fits, say so and offer a public search; do not run one unasked.

## 1a. Search the stars (`stars`, `both`)

Call `stars` with:

- `lists: true` — list names and sizes
- `match: ["pdf", "document", "extract"]` — keyword filter, any term matches
- `list: "<name-or-slug>"` — one list
- nothing — everything

Each line is `owner/repo ★N · pushed DATE [star lists] — description (topics: …)`. Results are cached for 24h; pass `refresh: true` if the user says they just starred something.

If the user names a list, use `list`. Otherwise try `match` with a few synonyms first, and fall back to the full index when matches are thin — descriptions are short, so judge relevance yourself rather than trusting keywords. Many starred repos are not agent tooling at all; repos in lists whose names suggest AI tooling, and repos with topics like `agent-skills`, `codex`, `claude-code`, `mcp`, are the likely candidates.

## 1b. Search public GitHub (`public`, `both`)

Call `public` with `query` and optionally `kind` (`any`, `skill`, `plugin`, `mcp`), `min_stars` (default 10) and `limit` (default 15).

- `query` is GitHub search syntax: words are ANDed, so keep it to one or two words and use `OR` for synonyms (`"diagram OR flowchart"`).
- Output is sorted by stars, which is popularity, not relevance. Drop repos that only mention the term in passing (e.g. tools that *convert PDFs into skills* when the user wants a skill that *handles PDFs*).
- Only repos tagged with an agent-tooling topic are found, and a skill inside a large multi-skill repo is invisible unless the repo is described that way. If results are thin, say so rather than guessing.

## 2. Inspect the best candidates

Call `detect` with `repos` (at most 5) and `match` (the task's keywords). It returns JSON.

- It reports `kinds` (`marketplace`, `plugin-without-marketplace`, `skill`, `mcp`, `other`) and an `install` entry per installable unit.
- A repo can hold dozens of skills and only 15 get descriptions fetched, matching ones first.
- Skills marked `internal: true` live under dot-directories and are usually the repo's own development tooling — mention them only if nothing else fits. Drop candidates whose kind is `other`.
- A plugin whose `marketplaceFile` is `.claude-plugin/marketplace.json` was made for Claude Code. Codex can install it, but parts made only for Claude Code (such as hooks) may not work; say so.

## 3. Recommend, then wait

Present a short ranked list.

**Required: every repo you mention — recommended or ruled out, from the stars or from public search — starts with its `header` line from `detect`, copied verbatim**, e.g. `owner/repo ★1234 · pushed 2026-10-21`. For a repo you did not inspect, copy the same `owner/repo ★N · pushed DATE` from the `stars` / `public` line. Never omit or estimate these numbers.

For each recommendation also give: where it came from (`[★ star list name]`, `[★ starred]` or `[public]`), what it is (plugin / skill / MCP), what it would install, and why it fits the task. Flag anything that runs code (plugin hooks, MCP servers, bundled scripts).

For `[public]` results say plainly that the user has not vetted this repo; suggest they look at it before installing.

**Never install without the user's explicit choice in their reply.** Do not present repos that came from neither source.

## 4. Install through the `install` tool

When the user picks a recommendation, call `install`. If the user names a repo to install without a search, call `detect` on it first for the kind and folder, then `install`. Never run `codex plugin add`, `codex mcp add` or copy skill files yourself: the tool shows the user two dialogs, first the next step and then the scope, and installs only after both. Above your wording the tool puts the facts it found (repo, stars, commit, files, scripts, an existing folder, the marketplace format) in English.

Always pass `dialog`, the wording of both dialogs in the language the user writes in:

```json
"dialog": {
  "about": "<optional: a line or two on what this install brings and anything worth noticing>",
  "next": "<the question for the next step>",
  "options": ["<cancel>", "<read the README first>", "<pick another>", "<install>"],
  "scope": "<the question for the scope>"
}
```

- For a plugin whose `marketplaceFile` is `.claude-plugin/marketplace.json`, say in `about` that parts made only for Claude Code (such as hooks) may not work in Codex.
- The tool reads the answer by position, so `options` is always in that order and each label plainly says that action in the user's language. The four options differ from each other.
- The scope dialog's options are `cancel` and the scopes on offer, fixed by the tool. `scope` is only the question, e.g. `要安裝到哪個範圍？`: do not explain the scopes in it or in `about`. A plugin or an MCP server offers only `user`, and so does a skill when Codex does not say which project the session is in.
- Limits: `next` 200 characters, `about` and `scope` 600, an option 40.
- Without `dialog`, or when it is incomplete, the dialogs are in English and the result ends with a `note:` saying why; fix it on the next call.

- **Skill**: `{ "repo": "owner/repo", "kind": "skill", "folder": "<folder from detect>" }`. Add `"force": true` only after the user agrees to replace an existing folder of the same name. Scopes: `local` and `project` install into this project's `.agents/skills/` (`local` also adds it to `.gitignore`), `user` into `~/.agents/skills/`.
- **Plugin**: `{ "repo": "<marketplace owner/repo>", "kind": "plugin", "plugin": "<plugin name>" }`. Codex installs plugins for the user only (`~/.codex/config.toml`, all the user's projects).
- **MCP server**: first read the README (`readme`) for the launch command and the env vars or API keys it needs; ask the user for any key. Then `{ "repo": "owner/repo", "kind": "mcp", "mcp_args": ["<name>", "--", "<command>", "<arg>", …] }`, everything that follows `codex mcp add` (`--env KEY=VALUE` goes before `--`; a remote server is `["<name>", "--url", "<url>"]`). Codex adds MCP servers for the user only (`~/.codex/config.toml`; `codex mcp add` has no project scope).

Act on the result:

- `not installed: … read the README first`: summarise the README (`readme`) and end your turn, even if you read it earlier. Call `install` again only after the user replies that they still want it.
- `not installed: … a different one`: ask which other recommendation to look at.
- `not installed: … cancelled` / `dismissed`: stop.
- `installed (scope …)`: report exactly what was added and where, the `next:` line, and how to remove it (delete the skill folder; `codex plugin remove <plugin>@<marketplace>`; `codex mcp remove <name>`).
- `install failed` with `has moved on`: the repo got a new commit after the user saw the dialog, so nothing was installed. Say so; call the install tool again only if the user still wants it, so they see the new commit.
- `install failed`: show the output; do not retry with other flags unasked.
