# Model review runs in a subagent, and only when another check found something

The files a model review reads are untrusted and may carry prompt injection aimed at the reviewer, so the review never runs in the main conversation. Instead, the main model starts a subagent. The subagent reads the files at the pinned commit through kirby's read-only `check` and `file` tools.

It reports in a fixed structure: file, line, and a one-sentence reason that may not quote the file, at most 120 characters, and at most 5 findings. The install tool checks that structure and strips hidden characters before showing anything. Each model-review finding is a warn, is labelled as reported by the model, and can only add to what the dialog shows; it never removes or lowers another finding.

The review runs only when another part of the pre-install check found a danger or warn finding, including the pattern scan's combination findings (ADR 0005). Most tools are clean, and this way they don't pay the wait and the tokens. When a review should have run but no result is passed, or the model reports that it could not run, the dialog says so in one line and Install stays available (ADR 0005).

Decided on 2026-10-30, after the first build:

1. **No review when an install is blocked.** A known-malicious package (ADR 0001) already takes Install out of the dialog, so a review would only cost time and tokens.
2. **In Claude Code, kirby's hook allows its own `check` and `file` tools without a permission prompt.** It allows those two and nothing else, so the review never stops at a prompt; they only read GitHub and package contents and write nothing to the machine. A deny rule the user or the organization set still stands. Codex already runs them without asking, because the tools declare themselves read-only.
3. **Claude Code registers a reviewer agent, `kirby:reviewer`, that can use only `check` and `file`, and the inhale skill starts it for the review.** Even if a reviewed file carries prompt injection, the reviewer has no Bash or write tool to misuse. Its instructions are its own prompt; the main model gives it only where the files are and which. This decision is for Claude Code; in Codex the skill still gives the subagent it starts the same instructions.
4. **The dialog counts the review's findings and shows none of the reviewer's text** ([ADR 0006](0006-dialog-facts-worded-by-kirby.md)). The install tool still checks the structure and cleans the text, but a finding's reason, file and line, and the reason a review could not run, go only to the model, labelled as reported by the model. The dialog counts the findings on the warn line and says in kirby's own words that the review found nothing or did not run, giving the reason only when kirby wrote it.

## Considered Options

- **The install tool runs `claude -p` or `codex exec` itself**: the result would reach the dialog without passing through the main model, but whether a headless run works from inside kirby's process was never checked. The subagent route works the same way in Claude Code and Codex.
- **Review before every install, and refuse to show the dialog without a result**: this was the first decision. It was dropped because it made every install slower and more expensive, and a refusal goes against ADR 0005.

## Consequences

The main model passes the result on, so the tool cannot prove that the review was not edited on the way, or that it was not skipped. The dialog labels the findings as reported by the model, and says when a review that should have run did not.
