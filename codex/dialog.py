"""The Codex dialogs' wording. The model writes it in the user's language (the install tool's `dialog`
input, in the format the inhale skill gives) and picks the language of the facts above it (dialog.lang),
which kirby words itself (skills/inhale/scripts/words.py, docs/adr/0006); the scope dialog's options stay
the server's own. When the wording is missing or unusable, the dialogs and their facts are in English. The
model review's result (the install tool's `review` input), once read_review checks it, reaches the first
dialog only in kirby's words (review_facts) and the model in full (review_note). Pure, so the tests can run
it directly; the rules match hooks/dialog.ts.
"""
import re
import sys
import unicodedata
from pathlib import Path

# The wording lives beside the scripts, which can word their facts with it too.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "inhale" / "scripts"))
from words import fact, read_lang, say  # noqa: E402

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
    """The model review's result, checked, and None; or None and why it is refused, so the model sends it again.
    review is the check's own (whether it was needed, the sha and the files it covered); sha is the one the model
    says the review read. A review the check did not ask for is left out, and a missing one, or one that could not
    run, did not run (docs/adr/0002, docs/adr/0005).

    The result is what the dialog shows of the review, in kirby's words (review_facts), and what the model is told
    (review_note): {"state": "not needed"}, {"state": "found", "findings": [{file, line, reason}]},
    {"state": "nothing found"}, {"state": "did not run", "why": <kirby's reason, a fact>} or
    {"state": "did not run", "reviewer": <the reviewer's could_not_run, cleaned>}. The reviewer's own text, its
    findings' reasons and its could_not_run, reaches only the model (docs/adr/0006)."""
    if not review["needed"]:
        return {"state": "not needed"}, None
    if raw is None:
        return {"state": "did not run", "why": fact("review_no_result" if review["files"] else "review_no_files")}, None
    if not isinstance(raw, dict) or len(raw) != 1 or not ({"findings", "could_not_run"} & set(raw)):
        return None, REVIEW_SHAPE
    if "could_not_run" in raw:
        why = _reason(raw["could_not_run"])
        if not why:
            return None, f"review.could_not_run must be a reason of at most {REVIEW_MAX['reason']} characters"
        return {"state": "did not run", "reviewer": why}, None
    findings = raw["findings"]
    if not isinstance(findings, list) or len(findings) > REVIEW_MAX["findings"]:
        return None, f"review.findings must be a list of at most {REVIEW_MAX['findings']}"
    found = []
    for i, f in enumerate(findings):
        at = f"review.findings[{i}]"
        if not isinstance(f, dict) or set(f) != {"file", "line", "reason"}:
            return None, f"{at} must have exactly file, line and reason"
        if f["file"] not in review["files"]:
            return None, f"{at}.file must be one of the files the check tool listed"
        if type(f["line"]) is not int or f["line"] < 1:
            return None, f"{at}.line must be a line number"
        reason = _reason(f["reason"])
        if not reason:
            return None, f"{at}.reason must be one sentence of at most {REVIEW_MAX['reason']} characters"
        found.append({"file": f["file"], "line": f["line"], "reason": reason})
    if not isinstance(sha, str) or not sha:
        return None, "sha must be the one the check tool returned, which the review read"
    if sha != review["sha"]:
        return {"state": "did not run", "why": fact("review_other_commit", read=sha[:7], checked=review["sha"][:7])}, None
    return ({"state": "found", "findings": found} if found else {"state": "nothing found"}), None


def review_facts(facts, reviewed):
    """The facts with the review's result as the dialog shows it, in kirby's words only: its findings counted on
    the warn line, or a line saying it found nothing or did not run, with kirby's reason but never the reviewer's."""
    state = reviewed["state"]
    if state == "found":
        return count_review(facts, len(reviewed["findings"]))
    if state == "nothing found":
        return [*facts, fact("review_nothing")]
    if state == "did not run":
        return [*facts, fact("review_not_run_why", why=reviewed["why"]) if "why" in reviewed else fact("review_not_run")]
    return list(facts)


def count_review(facts, n):
    """The facts with n model review findings counted on the warn line, as the dialog shows them: it counts the
    review's findings and shows none of the reviewer's text (docs/adr/0006). Without a warn line, it makes one after
    the danger lines, or before the check's first line. The facts given are left as they are."""
    if n == 0:
        return list(facts)
    review = fact("warn_review", count=n)

    def keyed(f, test):
        return isinstance(f, dict) and test(f["key"])

    at = next((i for i, f in enumerate(facts) if keyed(f, lambda k: k == "warn")), None)
    if at is not None:
        w = facts[at]["args"]
        return [fact("warn", count=w["count"] + n, names=[*w["names"], review]) if i == at else f for i, f in enumerate(facts)]
    danger = [i for i, f in enumerate(facts) if keyed(f, lambda k: k.startswith("danger_") or k == "check_blocked")]
    first = next((i for i, f in enumerate(facts) if keyed(f, lambda k: re.match(r"(check|scan|lookup)_", k))), len(facts))
    i = danger[-1] + 1 if danger else first
    return [*facts[:i], fact("warn", count=n, names=[review]), *facts[i:]]


def review_note(reviewed):
    """The review's result for the model, in English, in every result after the dialog opens: every finding with its
    file, line and reason, and the reviewer's reason when it could not run, which the dialog left out; "" without
    a review."""
    state = reviewed["state"]
    if state == "found":
        return (f"review: the model review's findings, {LABEL} (the dialog showed the user only how many, on the warn line):\n"
                + "\n".join(f"  warn: {f['file']}:{f['line']}: {f['reason']}" for f in reviewed["findings"]))
    if state == "nothing found":
        return f"review: the dialog showed the user that the model review found nothing, {LABEL}"
    if state == "did not run":
        if "why" in reviewed:
            return f"review: the dialog showed the user that the model review did not run ({say(reviewed['why'], 'en')})"
        return f"review: the dialog showed the user that the model review did not run, without its reason, {LABEL}: {reviewed['reviewer']}"
    return ""
