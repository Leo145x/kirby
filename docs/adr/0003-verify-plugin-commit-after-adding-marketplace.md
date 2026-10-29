# Claude Code plugins are pinned by checking the marketplace's commit after adding it

A plugin should install the commit the dialog showed, as a skill does. Claude Code's `claude plugin marketplace add` takes `owner/repo#ref` for a branch or tag only: on 2026-10-29, `Leo145x/kirby#<full sha>` failed with `Remote branch <sha> not found in upstream origin`. So in Claude Code, kirby adds the marketplace as usual, then reads the HEAD of the clone Claude Code made. If it is not the checked commit, kirby removes the marketplace and installs nothing. Codex is pinned directly: `codex plugin marketplace add <repo> --ref <sha>` checked out exactly that commit in the same test.

## Considered Options

- **Clone the marketplace at the commit into a directory kirby manages and add it as a local path**: rejected, because the marketplace would then never update from GitHub.
- **Don't pin plugins in Claude Code and say so in the dialog**: rejected, because then a plugin's check could describe a different commit from the one that gets installed.

## Consequences

A plugin entry whose source is another repo is pinned only if the marketplace's author gave it a `sha`. kirby checks that source repo too, at the `sha` when there is one and as it stands otherwise, and when there is no `sha` the dialog says the source is not pinned.
