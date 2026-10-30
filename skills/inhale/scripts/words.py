"""kirby's own wording of the dialog's fact lines, in English, 繁體中文 and 简体中文 (docs/adr/0006).

The model only picks the language (the install tool's dialog.lang); it never writes or translates a fact
line. A fact is either a line kirby has no wording for yet, a string shown as it is in every language, or
{"key": …, "args": {…}}: a key and the values put into that key's wording. Values (commands, paths, names,
versions, ids, numbers) go in as they are, so they can be copied and looked up. Only the dialogs are worded;
what the tools answer the model stays English (say(f, "en")).

The Codex server uses this module, and a script can too: it can give its facts beside its English lines,
and each side words them. The table is hooks/words.ts's; tests/test_codex.py checks the two match, and both
sides' tests give the same cases. To add a line: add its key with its wording in all three languages, here
and in words.ts. `{name}` takes the value named; a list of values is joined with the language's `list`.
"""
import re

LANGS = ("en", "zh-TW", "zh-CN")

WORDS = {
    "list": {"en": ", ", "zh-TW": "、", "zh-CN": "、"},
    "repo": {"en": "{repo} ★{stars} · pushed {pushed}", "zh-TW": "{repo} ★{stars} · {pushed} 更新", "zh-CN": "{repo} ★{stars} · {pushed} 更新"},
    "repo_archived": {
        "en": "{repo} ★{stars} · pushed {pushed} · ARCHIVED",
        "zh-TW": "{repo} ★{stars} · {pushed} 更新 · 已封存",
        "zh-CN": "{repo} ★{stars} · {pushed} 更新 · 已归档",
    },
    "skill": {
        "en": "skill: {name} · commit {commit} · {files} files",
        "zh-TW": "技能：{name} · commit {commit} · {files} 個檔案",
        "zh-CN": "技能：{name} · commit {commit} · {files} 个文件",
    },
    "scripts": {"en": "scripts: {count}, e.g. {names}", "zh-TW": "{count} 個腳本，例如 {names}", "zh-CN": "{count} 个脚本，例如 {names}"},
    "exists_fails": {
        "en": "exists: {path} (installing at local or project fails)",
        "zh-TW": "已存在：{path}（安裝在 local 或 project 會失敗）",
        "zh-CN": "已存在：{path}（安装在 local 或 project 会失败）",
    },
    "exists_replaces": {
        "en": "exists: {path} (installing at local or project replaces it)",
        "zh-TW": "已存在：{path}（安裝在 local 或 project 會取代它）",
        "zh-CN": "已存在：{path}（安装在 local 或 project 会替换它）",
    },
    "installs_at_user": {
        "en": "installs at: user (~/.codex/config.toml, every project)",
        "zh-TW": "安裝位置：user（~/.codex/config.toml，所有專案）",
        "zh-CN": "安装位置：user（~/.codex/config.toml，所有项目）",
    },
    "installs_at_user_skill": {
        "en": "installs at: user (~/.agents/skills/; Codex did not say which project this session is in)",
        "zh-TW": "安裝位置：user（~/.agents/skills/；Codex 沒有說這個工作階段在哪個專案）",
        "zh-CN": "安装位置：user（~/.agents/skills/；Codex 没有说这个会话在哪个项目）",
    },
}


def fact(key, **args):
    if key not in WORDS or key == "list":
        raise KeyError(f"no wording for {key}")
    return {"key": key, "args": args}


def read_lang(value):
    """The language the model picked, or English for anything else."""
    return value if isinstance(value, str) and value in LANGS else "en"


def say(f, lang):
    """One fact line in the language given."""
    if isinstance(f, str):
        return f

    def value(m):
        name = m.group(1)
        if name not in f["args"]:
            raise KeyError(f"{f['key']} needs {name}")
        v = f["args"][name]
        return WORDS["list"][lang].join(v) if isinstance(v, list) else str(v)

    return re.sub(r"\{(\w+)\}", value, WORDS[f["key"]][lang])
