# The dialog's facts are worded by kirby, never by the model

The facts in the install dialog come in English, 繁體中文 or 简体中文 from kirby's own wording; the model only picks the language. The model review's own text (a finding's reason, why it could not run) stays out of the facts too: the dialog counts the review's findings, and the model gets the text. The model reads text the tool's author controls before it calls install: a repo's description in the search results (`public.py`), and an MCP server's README (`skills/inhale/SKILL.md`, section 4). If the model wrote the facts, an instruction planted in that text could soften or drop a warning in the one place the user reads before installing. That is the same reason the model review runs in a subagent (ADR 0002).

## Considered Options

- **The model translates the facts** into any language. It was rejected because of the prompt injection above. Users of other languages get English.
