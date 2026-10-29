# Installing is one click by default; only a block stops it

The pre-install check exists so the user knows what they are installing, not so that installing becomes a chore. Each limit kirby runs into becomes one line in the dialog, never a refusal or an extra step for the user. That covers a part that could not run, a version that is not pinned, a package the repo only claims as its own, and a marketplace that installing will refresh. The one exception is a block (ADR 0001). When the pre-install check finds nothing, the dialog says so in a single line.

Where kirby can remove a stop by doing more work itself, it does. A skill installs the commit the dialog showed even if the repo has moved on since, because kirby copies the files itself and can fetch that commit. A plugin is installed through the agent CLI, which fetches from GitHub itself, so kirby checks the commit after the install and removes the plugin if that commit is not the one checked (ADR 0003).

## Considered Options

- **Refuse whenever kirby cannot be sure, and tell the user what to run**: this was the first design for marketplaces that are behind and for missing model reviews. It was rejected because every refusal sends the user off to run a command or answer the dialog again, and the user said that makes kirby feel restrictive.

## Consequences

The model review runs only when another check found a danger or warn finding (ADR 0002). This is why the pattern scan has combination findings: one tool hitting `network` together with `env-secret`, `exec` or `decode` is a warn, although each of those rules alone is info. Without them, a skill that reads a secret and sends it out would trigger no model review at all.
