# Model review runs in a subagent, and only when another check found something

The files a model review reads are untrusted and may carry prompt injection aimed at the reviewer, so the review never runs in the main conversation. Instead, the main model starts a subagent. The subagent reads the files at the pinned commit through kirby's read-only `check` and `file` tools.

It reports in a fixed structure: file, line, and a one-sentence reason that may not quote the file, at most 120 characters, and at most 5 findings. The install tool checks that structure and strips hidden characters before showing anything. Each model-review finding is a warn, is labelled as reported by the model, and can only add to what the dialog shows; it never removes or lowers another finding.

The review runs only when another part of the pre-install check found a danger or warn finding, including the pattern scan's combination findings (ADR 0005). Most tools are clean, and this way they don't pay the wait and the tokens. When a review should have run but no result is passed, or the model reports that it could not run, the dialog says so in one line and Install stays available (ADR 0005).

## Considered Options

- **The install tool runs `claude -p` or `codex exec` itself**: the result would reach the dialog without passing through the main model, but whether a headless run works from inside kirby's process was never checked. The subagent route works the same way in Claude Code and Codex.
- **Review before every install, and refuse to show the dialog without a result**: this was the first decision. It was dropped because it made every install slower and more expensive, and a refusal goes against ADR 0005.

## Consequences

The main model passes the result on, so the tool cannot prove that the review was not edited on the way, or that it was not skipped. The dialog labels the findings as reported by the model, and says when a review that should have run did not.
