"""The Codex dialogs' wording. The model writes it in the user's language (the install tool's `dialog`
input, in the format the inhale skill gives); the facts above it and the scope dialog's options stay
the server's own. When the wording is missing or unusable, the dialogs are in English. Pure, so the
tests can run it directly; the rules match hooks/dialog.ts.
"""

SCOPES = ("local", "project", "user")
# The scope dialog's options, the same in every language.
CANCEL = "cancel"

MAX = {"about": 600, "next": 200, "option": 40, "scope": 600}


def english():
    return {
        "about": "",
        "next": "What next?",
        # In this order: cancel, read the README first, pick another, install.
        "options": ["Cancel", "Read README first", "Pick another", "Install"],
        "scope": "Install at which scope?",
    }


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
    return {"about": about, "next": nxt, "options": options, "scope": scope}, None
