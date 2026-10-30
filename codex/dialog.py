"""The Codex dialogs' wording. The model writes it in the user's language (the install tool's `dialog`
input, in the format the inhale skill gives) and picks the language of the facts above it (dialog.lang),
which kirby words itself (skills/inhale/scripts/words.py, docs/adr/0006); the scope dialog's options stay
the server's own. When the wording is missing or unusable, the dialogs and their facts are in English. The
model review's result (the install tool's `review` input) also reaches the first dialog, as read_review
checks it. Pure, so the tests can run it directly; the rules match hooks/dialog.ts.
"""
import re
import sys
import unicodedata
from pathlib import Path

# The wording lives beside the scripts, which can word their facts with it too.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "inhale" / "scripts"))
from words import read_lang  # noqa: E402

SCOPES = ("local", "project", "user")
# The scope dialog's cancel option, the same in every language (the server words its install option, server.py).
CANCEL = "cancel"

# In characters (code points), as hooks/dialog.ts counts them too.
MAX = {"about": 120, "next": 200, "option": 40, "scope": 600}
# The model review's limits (docs/adr/0002), in characters.
REVIEW_MAX = {"reason": 120, "findings": 5}
REVIEW_SHAPE = 'review must be {"findings": [...]} or {"could_not_run": "<reason>"}'
LABEL = "as reported by the model"


def english():
    return {
        "about": "",
        "next": "What next?",
        # In this order: cancel, read the README first, pick another, install.
        "options": ["Cancel", "Read README first", "Pick another", "Install"],
        "scope": "Install at which scope?",
        # The language of the facts, which kirby words.
        "lang": "en",
    }


def next_options(d, blocked):
    """The first dialog's options. A block (a malware-lookup finding) leaves Install out, so the user
    cannot pick it (docs/adr/0001)."""
    return list(d["options"][:3] if blocked else d["options"])


def _text(value, limit):
    return value.strip() if isinstance(value, str) and value.strip() and len(value) <= limit else None


def read_dialog(raw):
    """The model's wording and None, or English and why the wording could not be used."""
    def fallback(problem):
        return english(), problem

    if not isinstance(raw, dict):
        return fallback("no dialog was given")
    nxt = _text(raw.get("next"), MAX["next"])
    if not nxt:
        return fallback(f"dialog.next must be a question of at most {MAX['next']} characters")
    scope = _text(raw.get("scope"), MAX["scope"])
    if not scope:
        return fallback(f"dialog.scope must be a question of at most {MAX['scope']} characters")
    about = "" if raw.get("about") is None else _text(raw.get("about"), MAX["about"])
    if about is None:
        return fallback(f"dialog.about, when given, must be at most {MAX['about']} characters")
    given = raw.get("options")
    options = [_text(o, MAX["option"]) for o in given] if isinstance(given, list) else []
    if len(options) != 4 or None in options or len(set(options)) != 4:
        return fallback(f"dialog.options must be 4 distinct labels of at most {MAX['option']} characters")
    return {"about": about, "next": nxt, "options": options, "scope": scope, "lang": read_lang(raw.get("lang"))}, None


def clean(text):
    """The model's text, which may carry what it read in the files: format, private-use and unassigned
    characters go, control characters and line breaks become spaces, and runs of spaces become one."""
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cf", "Co", "Cs", "Cn"))
    text = "".join(" " if ch.isspace() or unicodedata.category(ch) == "Cc" else ch for ch in text)
    return re.sub(" +", " ", text).strip()


def _reason(value):
    return clean(value) or None if isinstance(value, str) and len(value) <= REVIEW_MAX["reason"] else None


def read_review(raw, sha, review):
    """The model review's lines for the first dialog, and None; or no lines and why the result is refused, so
    the model sends it again. review is the check's own (whether it was needed, the sha and the files it
    covered); sha is the one the model says the review read. A review the check did not ask for is left out,
    and a missing one, or one that could not run, is one unchecked line (docs/adr/0002, docs/adr/0005)."""
    if not review["needed"]:
        return [], None
    if raw is None:
        why = "no review result was passed" if review["files"] else "kirby had no files of it to read"
        return [f"model review: unchecked ({why})"], None
    if not isinstance(raw, dict) or len(raw) != 1 or not ({"findings", "could_not_run"} & set(raw)):
        return [], REVIEW_SHAPE
    if "could_not_run" in raw:
        why = _reason(raw["could_not_run"])
        if not why:
            return [], f"review.could_not_run must be a reason of at most {REVIEW_MAX['reason']} characters"
        return [f"model review: unchecked ({why})"], None
    findings = raw["findings"]
    if not isinstance(findings, list) or len(findings) > REVIEW_MAX["findings"]:
        return [], f"review.findings must be a list of at most {REVIEW_MAX['findings']}"
    lines = []
    for i, f in enumerate(findings):
        at = f"review.findings[{i}]"
        if not isinstance(f, dict) or set(f) != {"file", "line", "reason"}:
            return [], f"{at} must have exactly file, line and reason"
        if f["file"] not in review["files"]:
            return [], f"{at}.file must be one of the files the check tool listed"
        if type(f["line"]) is not int or f["line"] < 1:
            return [], f"{at}.line must be a line number"
        reason = _reason(f["reason"])
        if not reason:
            return [], f"{at}.reason must be one sentence of at most {REVIEW_MAX['reason']} characters"
        lines.append(f"warn: {f['file']}:{f['line']}: {reason} (model review, {LABEL})")
    if not isinstance(sha, str) or not sha:
        return [], "sha must be the one the check tool returned, which the review read"
    if sha != review["sha"]:
        return [f"model review: unchecked (it read {sha[:7]}, not {review['sha'][:7]}, the one checked here)"], None
    return lines or [f"model review: nothing found ({LABEL})"], None


def review_note(lines):
    """The review's dialog lines for the model, in every result after the dialog opens; "" without any."""
    return "review: the dialog showed the user these model review lines:\n" + "\n".join(f"  {l}" for l in lines) if lines else ""
