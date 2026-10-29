# Model review runs in a subagent, and the install tool will not show the dialog without its result

The files a model review reads are untrusted and may carry prompt injection aimed at the reviewer, so the review runs in a subagent that the main model starts, never in the main conversation. The subagent reads the files at the pinned commit through kirby's read-only `check` and `file` tools. It reports in a fixed structure: file, line, and a one-sentence reason that may not quote the file, with a length limit and a cap on the number of findings. The install tool checks that structure and strips hidden characters before it shows anything. Each model-review finding is a warn, is labelled as reported by the model, and can only add to what the dialog shows; it never removes or lowers another finding. The install tool refuses to show the dialog when no review result is passed. The main model may instead report that the review could not run and give a reason, and the dialog then shows the model review as unchecked with that reason.

## Considered Options

- **The install tool runs `claude -p` or `codex exec` itself**: the result would reach the dialog without passing through the main model, but whether a headless run works from inside kirby's process was never checked. The subagent route works the same way in Claude Code and Codex.
- **Mark a missing review as unchecked and show the dialog anyway**: rejected, because the main model could then skip the review without saying so.

## Consequences

The main model passes the result on, so the tool cannot prove that the review was not edited on the way. The dialog labelling those findings as reported by the model is what keeps that honest.
