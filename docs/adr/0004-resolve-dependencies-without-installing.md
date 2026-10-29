# Unpinned dependencies are resolved without being installed

When a tool's dependencies are given as ranges and there is no lockfile, kirby works out which versions would be picked without downloading or running anything, then looks those versions up. It uses `npm install --package-lock-only --ignore-scripts` for npm and `uv pip compile --no-build` for Python. A trial install would be the simple way to learn the real versions, but installing a package runs its install hooks (npm's `preinstall` and `postinstall`, a Python source package's build), and that is exactly how malicious packages do their harm. So a trial install would run the attack the check is meant to catch. The versions are resolved at check time and may differ when the tool actually runs, and the dialog says so. When npm or uv is not on the user's machine, kirby still runs the malware lookup on the package names and marks the advisory lookup unchecked.

## Considered Options

- **Install into a container and inspect it**: rejected for now, because it needs Docker or something like it on the user's machine and adds a lot of moving parts.
- **Look up names only and never resolve versions**: kept only as the fallback for when npm or uv is missing.
