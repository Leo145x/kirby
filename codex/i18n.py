"""The Codex dialog text in the user's language: English, Traditional or Simplified Chinese.

Pure, so the tests can run it directly. The language rules match hooks/i18n.ts.
"""
import re

TRADITIONAL = re.compile(r"zh[-_]?(tw|hk|mo|hant)|traditional|繁|台灣|臺灣|taiwan|香港|hong ?kong|cantonese|粵")
SIMPLIFIED = re.compile(r"zh[-_]?(cn|sg|hans)|^zh\b|simplified|简|簡|chinese|中文|mandarin|普通话")


def _match(value):
    v = (value or "").strip().lower()
    if not v:
        return None
    if TRADITIONAL.search(v):
        return "zh-TW"
    if SIMPLIFIED.search(v):
        return "zh-CN"
    return "en"


def pick_lang(lang, locale):
    """`lang` is what the model passes (the language the user writes in); `locale` is LC_ALL or LANG,
    used when it is missing. Any language other than Chinese gets English."""
    return _match(lang if isinstance(lang, str) else "") or _match(locale) or "en"


TEXT = {
    "en": {
        "options": {"cancel": "Cancel", "readme": "Read README first", "other": "Pick another", "install": "Install"},
        "next": "What next?",
        "scope": "Install at which scope?",
        "kind": "Kind: {}",
        "commit": "Version: commit {}",
        "files": "Files: {}",
        "scripts": "Scripts: {} executable file(s), e.g. {}",
        "exists": "Exists: this project already has .agents/skills/{}/; installing at local or project {}",
        "exists_force": ("fails", "replaces it"),
        "about": "About: {}",
        "command": "Command: {}",
        "where": {
            "skill": {
                "local": "this project's .agents/skills/, added to .gitignore, kept out of git",
                "project": "this project's .agents/skills/, committed to git",
                "user": "~/.agents/skills/, all your projects",
            },
            "plugin": {"user": "all your projects (~/.codex/config.toml); Codex installs plugins only for the user"},
            "mcp": {"user": "all your projects (~/.codex/config.toml); codex mcp add has no project scope"},
        },
        "no_project": "Codex did not say which project this session is in, so only user is offered.",
        "claude_format": "Note: this marketplace is in Claude Code's format. Codex reads it, "
                         "but parts made only for Claude Code (such as hooks) may not work.",
    },
    "zh-TW": {
        "options": {"cancel": "取消", "readme": "先看 README", "other": "換一個", "install": "安裝"},
        "next": "下一步要做什麼？",
        "scope": "安裝到哪個 scope？",
        "kind": "種類：{}",
        "commit": "版本：commit {}",
        "files": "檔案：{} 個",
        "scripts": "腳本：{} 個可執行檔，例如 {}",
        "exists": "已存在：這個專案已有 .agents/skills/{}/，裝在 local 或 project 會{}",
        "exists_force": ("失敗", "取代它"),
        "about": "說明：{}",
        "command": "指令：{}",
        "where": {
            "skill": {
                "local": "這個專案的 .agents/skills/，並加進 .gitignore，不進 git",
                "project": "這個專案的 .agents/skills/，會進 git",
                "user": "~/.agents/skills/，你所有的專案",
            },
            "plugin": {"user": "你所有的專案（~/.codex/config.toml）；Codex 的 plugin 只能裝在 user"},
            "mcp": {"user": "你所有的專案（~/.codex/config.toml）；codex mcp add 沒有專案層級"},
        },
        "no_project": "Codex 沒有提供這個 session 所在的專案，所以只能選 user。",
        "claude_format": "注意：這個 marketplace 是 Claude Code 的格式。Codex 讀得懂，但只為 Claude Code 寫的部分（例如 hooks）可能無法運作。",
    },
    "zh-CN": {
        "options": {"cancel": "取消", "readme": "先看 README", "other": "换一个", "install": "安装"},
        "next": "下一步要做什么？",
        "scope": "安装到哪个 scope？",
        "kind": "类型：{}",
        "commit": "版本：commit {}",
        "files": "文件：{} 个",
        "scripts": "脚本：{} 个可执行文件，例如 {}",
        "exists": "已存在：这个项目已有 .agents/skills/{}/，装在 local 或 project 会{}",
        "exists_force": ("失败", "替换它"),
        "about": "说明：{}",
        "command": "命令：{}",
        "where": {
            "skill": {
                "local": "这个项目的 .agents/skills/，并加入 .gitignore，不进 git",
                "project": "这个项目的 .agents/skills/，会进 git",
                "user": "~/.agents/skills/，你所有的项目",
            },
            "plugin": {"user": "你所有的项目（~/.codex/config.toml）；Codex 的 plugin 只能装在 user"},
            "mcp": {"user": "你所有的项目（~/.codex/config.toml）；codex mcp add 没有项目级别"},
        },
        "no_project": "Codex 没有提供这个 session 所在的项目，所以只能选 user。",
        "claude_format": "注意：这个 marketplace 是 Claude Code 的格式。Codex 读得懂，但只为 Claude Code 写的部分（例如 hooks）可能无法运行。",
    },
}
