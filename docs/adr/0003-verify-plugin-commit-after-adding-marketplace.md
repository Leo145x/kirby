# Plugins are pinned by checking the marketplace's commit after the install

A plugin should install the commit the dialog showed, as a skill does. Neither agent CLI gives kirby a good way to install a given commit. In Claude Code, `claude plugin marketplace add` takes `owner/repo#ref` for a branch or tag only: `#<full sha>` failed on 2026-10-29 with `Remote branch <sha> not found in upstream origin`. In Codex, `codex plugin marketplace add --ref <sha>` does check out that commit, but the marketplace then stays there for good, because `codex plugin marketplace upgrade` does not move it (tested while building #16).

So in both CLIs, kirby adds the marketplace without a ref and installs the plugin. Then it reads the HEAD of the marketplace's clone, and if that is not the checked commit, it removes the plugin and says so. A Claude Code marketplace the user added earlier gets refreshed by `claude plugin install` when it is behind its repo (seen in Claude Code 2.1.312). So kirby checks the repo's current commit, which is what the install will bring, and the dialog says that installing also refreshes that marketplace. A Codex marketplace the user added earlier is not refreshed by an install, so kirby checks the commit it is at.

## Considered Options

- **Clone the marketplace at the commit into a directory kirby manages and add it as a local path**: rejected, because the marketplace would then never update from GitHub.
- **Pin with `--ref <sha>` in Codex**: rejected, because the user's marketplace would then never update.
- **Refuse when the user's marketplace is behind, and tell them to update it first**: rejected under ADR 0005.

## Consequences

A plugin entry whose source is another repo is pinned only if the marketplace's author gave it a `sha`. kirby checks that source repo too, at the `sha` when there is one and as it stands otherwise, and when there is no `sha` the dialog says the source is not pinned. The plugins a plugin depends on, which the agent CLI installs along with it, are listed in the dialog as not checked.
