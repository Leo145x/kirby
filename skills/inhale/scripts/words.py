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
    "plugin": {
        "en": "plugin: {name} · marketplace {marketplace} · commit {commit}",
        "zh-TW": "外掛：{name} · marketplace {marketplace} · commit {commit}",
        "zh-CN": "插件：{name} · marketplace {marketplace} · commit {commit}",
    },
    "plugin_files": {
        "en": "plugin: {name} · marketplace {marketplace} · commit {commit} · {files} files",
        "zh-TW": "外掛：{name} · marketplace {marketplace} · commit {commit} · {files} 個檔案",
        "zh-CN": "插件：{name} · marketplace {marketplace} · commit {commit} · {files} 个文件",
    },
    "plugin_description": {"en": "description: {text}", "zh-TW": "說明：{text}", "zh-CN": "说明：{text}"},
    "plugin_source_root": {"en": "source: the root of this repo", "zh-TW": "來源：這個 repo 的根目錄", "zh-CN": "来源：这个 repo 的根目录"},
    "plugin_source_folder": {"en": "source: {path}/ in this repo", "zh-TW": "來源：這個 repo 的 {path}/", "zh-CN": "来源：这个 repo 的 {path}/"},
    "plugin_source_pinned": {
        "en": "source: {source} at commit {commit}, pinned by the marketplace entry",
        "zh-TW": "來源：{source}，commit {commit}，由 marketplace 項目鎖定",
        "zh-CN": "来源：{source}，commit {commit}，由 marketplace 条目锁定",
    },
    "plugin_source_unpinned": {
        "en": "source: {source} at commit {commit} ({ref}); not pinned: the marketplace entry gives no sha, so what installs may differ from what was checked",
        "zh-TW": "來源：{source}，commit {commit}（{ref}）；未鎖定：marketplace 項目沒有給 sha，安裝的內容可能和檢查過的不同",
        "zh-CN": "来源：{source}，commit {commit}（{ref}）；未锁定：marketplace 条目没有给出 sha，安装的内容可能与检查过的不同",
    },
    "plugin_source_unpinned_default": {
        "en": "source: {source} at commit {commit} (default branch); not pinned: the marketplace entry gives no sha, so what installs may differ from what was checked",
        "zh-TW": "來源：{source}，commit {commit}（預設分支）；未鎖定：marketplace 項目沒有給 sha，安裝的內容可能和檢查過的不同",
        "zh-CN": "来源：{source}，commit {commit}（默认分支）；未锁定：marketplace 条目没有给出 sha，安装的内容可能与检查过的不同",
    },
    "plugin_source_unfetched": {
        "en": "source: {source}, which kirby could not fetch",
        "zh-TW": "來源：{source}，kirby 無法取得",
        "zh-CN": "来源：{source}，kirby 无法获取",
    },
    "plugin_dependencies": {
        "en": "installed along with it, not checked: {plugins}",
        "zh-TW": "會一起安裝、未檢查：{plugins}",
        "zh-CN": "会一起安装、未检查：{plugins}",
    },
    "marketplace_added": {
        "en": "marketplace: already added as {name}, at commit {commit}; installs from it as it is",
        "zh-TW": "marketplace：已加入，名稱 {name}，在 commit {commit}；直接從它安裝",
        "zh-CN": "marketplace：已添加，名称 {name}，在 commit {commit}；直接从它安装",
    },
    "marketplace_refreshes": {
        "en": "marketplace: already added as {name}, at commit {commit}, behind its repo; installing refreshes it to {latest}, the commit checked",
        "zh-TW": "marketplace：已加入，名稱 {name}，在 commit {commit}，落後於它的 repo；安裝時會更新到檢查過的 commit {latest}",
        "zh-CN": "marketplace：已添加，名称 {name}，在 commit {commit}，落后于它的 repo；安装时会更新到检查过的 commit {latest}",
    },
    "marketplace_refreshes_unread": {
        "en": "marketplace: already added as {name}, at a commit kirby could not read; installing refreshes it to {latest}, the commit checked",
        "zh-TW": "marketplace：已加入，名稱 {name}，kirby 讀不到它在哪個 commit；安裝時會更新到檢查過的 commit {latest}",
        "zh-CN": "marketplace：已添加，名称 {name}，kirby 读不到它在哪个 commit；安装时会更新到检查过的 commit {latest}",
    },
    "marketplace_behind_unknown": {
        "en": "unchecked: whether the marketplace {name}, at commit {commit}, is behind its repo ({why}); if it is, installing refreshes it, and the plugin is removed again if it then comes from another commit",
        "zh-TW": "未檢查：marketplace {name}（在 commit {commit}）是否落後於它的 repo（{why}）；若是，安裝時會更新它，外掛若因此來自另一個 commit 會再移除",
        "zh-CN": "未检查：marketplace {name}（在 commit {commit}）是否落后于它的 repo（{why}）；如果是，安装时会更新它，插件如果因此来自另一个 commit 会再移除",
    },
    "marketplace_behind_unknown_unread": {
        "en": "unchecked: whether the marketplace {name}, at a commit kirby could not read, is behind its repo ({why}); if it is, installing refreshes it, and the plugin is removed again if it then comes from another commit",
        "zh-TW": "未檢查：marketplace {name}（kirby 讀不到它在哪個 commit）是否落後於它的 repo（{why}）；若是，安裝時會更新它，外掛若因此來自另一個 commit 會再移除",
        "zh-CN": "未检查：marketplace {name}（kirby 读不到它在哪个 commit）是否落后于它的 repo（{why}）；如果是，安装时会更新它，插件如果因此来自另一个 commit 会再移除",
    },
    "marketplace_not_listed": {
        "en": "unchecked: whether this marketplace is already added ({why}); the check is of its repo as it stands, and the plugin is removed again if kirby cannot tell it installs from that commit",
        "zh-TW": "未檢查：這個 marketplace 是否已加入（{why}）；檢查的是它的 repo 目前的狀態，若 kirby 無法確認外掛是從那個 commit 安裝的，會再移除",
        "zh-CN": "未检查：这个 marketplace 是否已添加（{why}）；检查的是它的 repo 当前的状态，如果 kirby 无法确认插件是从那个 commit 安装的，会再移除",
    },
    "marketplace_head_unread": {
        "en": "unchecked: which commit the marketplace {name}, already added, is at ({why}); the check is of its repo as it stands, and the plugin is removed again if kirby cannot tell it installs from that commit",
        "zh-TW": "未檢查：已加入的 marketplace {name} 在哪個 commit（{why}）；檢查的是它的 repo 目前的狀態，若 kirby 無法確認外掛是從那個 commit 安裝的，會再移除",
        "zh-CN": "未检查：已添加的 marketplace {name} 在哪个 commit（{why}）；检查的是它的 repo 当前的状态，如果 kirby 无法确认插件是从那个 commit 安装的，会再移除",
    },
    "marketplace_claude_format": {
        "en": "marketplace: {file} (Claude Code format)",
        "zh-TW": "marketplace：{file}（Claude Code 格式）",
        "zh-CN": "marketplace：{file}（Claude Code 格式）",
    },
    "mcp_server": {"en": "MCP server: {command}", "zh-TW": "MCP server：{command}", "zh-CN": "MCP server：{command}"},
    "mcp_package": {
        "en": "package: {package} ({ecosystem}), named by this repo's {file}; not verified to come from this repo",
        "zh-TW": "套件：{package}（{ecosystem}），由這個 repo 的 {file} 指名；沒有驗證它來自這個 repo",
        "zh-CN": "包：{package}（{ecosystem}），由这个 repo 的 {file} 指定；没有验证它来自这个 repo",
    },
    "mcp_pinned": {
        "en": "pinned: only {name}, to {version}; its dependencies are not pinned, so they may differ from those checked when the server starts",
        "zh-TW": "已鎖定：只有 {name}，鎖定在 {version}；它的相依套件沒有鎖定，server 啟動時可能和檢查過的不同",
        "zh-CN": "已锁定：只有 {name}，锁定在 {version}；它的依赖没有锁定，server 启动时可能与检查过的不同",
    },
    "mcp_pinned_range": {
        "en": "pinned: only {name}, to {version}, the highest version matching {range}; its dependencies are not pinned, so they may differ from those checked when the server starts",
        "zh-TW": "已鎖定：只有 {name}，鎖定在符合 {range} 的最高版本 {version}；它的相依套件沒有鎖定，server 啟動時可能和檢查過的不同",
        "zh-CN": "已锁定：只有 {name}，锁定在符合 {range} 的最高版本 {version}；它的依赖没有锁定，server 启动时可能与检查过的不同",
    },
    "mcp_not_pinned": {
        "en": "not pinned: kirby could not tell which version of {name} the command installs ({why}); it installs as given",
        "zh-TW": "未鎖定：kirby 無法確定指令會安裝 {name} 的哪個版本（{why}）；會照原樣安裝",
        "zh-CN": "未锁定：kirby 无法确定命令会安装 {name} 的哪个版本（{why}）；会按原样安装",
    },
    "scope_cache": {
        "en": "prompt cache: this plugin brings an MCP server; if tool search is off in this session, loading it with /reload-plugins rebuilds the cache once.",
        "zh-TW": "prompt cache：這個外掛帶有 MCP server；如果這個工作階段關閉了 tool search，用 /reload-plugins 載入它會重建一次 cache。",
        "zh-CN": "prompt cache：这个插件带有 MCP server；如果这个会话关闭了 tool search，用 /reload-plugins 加载它会重建一次 cache。",
    },
    "scope_cache_off": {
        "en": "prompt cache: this plugin brings an MCP server; ENABLE_TOOL_SEARCH=false is set, so loading it with /reload-plugins rebuilds the cache once.",
        "zh-TW": "prompt cache：這個外掛帶有 MCP server；已設定 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 載入它會重建一次 cache。",
        "zh-CN": "prompt cache：这个插件带有 MCP server；已设置 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 加载它会重建一次 cache。",
    },
    "scope_cache_maybe": {
        "en": "prompt cache: this plugin may bring an MCP server (its source was not checked); if tool search is off in this session, loading it with /reload-plugins rebuilds the cache once.",
        "zh-TW": "prompt cache：這個外掛可能帶有 MCP server（它的來源沒有檢查）；如果這個工作階段關閉了 tool search，用 /reload-plugins 載入它會重建一次 cache。",
        "zh-CN": "prompt cache：这个插件可能带有 MCP server（它的来源没有检查）；如果这个会话关闭了 tool search，用 /reload-plugins 加载它会重建一次 cache。",
    },
    "scope_cache_maybe_off": {
        "en": "prompt cache: this plugin may bring an MCP server (its source was not checked); ENABLE_TOOL_SEARCH=false is set, so loading it with /reload-plugins rebuilds the cache once.",
        "zh-TW": "prompt cache：這個外掛可能帶有 MCP server（它的來源沒有檢查）；已設定 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 載入它會重建一次 cache。",
        "zh-CN": "prompt cache：这个插件可能带有 MCP server（它的来源没有检查）；已设置 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 加载它会重建一次 cache。",
    },
    "scope_install_at_user": {
        "en": "install at user (~/.codex/config.toml, every project)",
        "zh-TW": "安裝在 user（~/.codex/config.toml，所有專案）",
        "zh-CN": "安装在 user（~/.codex/config.toml，所有项目）",
    },
    "scope_install_at_user_skill": {
        "en": "install at user (~/.agents/skills/)",
        "zh-TW": "安裝在 user（~/.agents/skills/）",
        "zh-CN": "安装在 user（~/.agents/skills/）",
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
