// kirby's own wording of the dialog's fact lines, in English, 繁體中文 and 简体中文 (docs/adr/0006). The model
// only picks the language (dialog.lang); it never writes or translates a fact line. A fact is either a line
// kirby has no wording for yet, a string shown as it is in every language, or a key and the values put into
// that key's wording. Values (commands, paths, names, versions, ids, numbers) go in as they are, so they can
// be copied and looked up. Only the dialogs are worded; what the tools answer the model stays English
// (say(f, 'en')). Pure: no `$`. The same table is skills/inhale/scripts/words.py's, which the Codex server and
// the scripts use; tests/test_codex.py checks the two match, and both sides' tests give the same cases.

export type Lang = 'en' | 'zh-TW' | 'zh-CN'
export const LANGS: readonly Lang[] = ['en', 'zh-TW', 'zh-CN']

// To add a line: add its key with its wording in all three languages, here and in words.py. `{name}` takes the
// value named; a list of values is joined with the language's `list`.
// words:start
const WORDS = {
  "list": {"en": ", ", "zh-TW": "、", "zh-CN": "、"},
  "repo": {"en": "{repo} ★{stars} · pushed {pushed}", "zh-TW": "{repo} ★{stars} · {pushed} 更新", "zh-CN": "{repo} ★{stars} · {pushed} 更新"},
  "repo_archived": {
    "en": "{repo} ★{stars} · pushed {pushed} · ARCHIVED",
    "zh-TW": "{repo} ★{stars} · {pushed} 更新 · 已封存",
    "zh-CN": "{repo} ★{stars} · {pushed} 更新 · 已归档"
  },
  "skill": {"en": "{name} · commit {commit} · {files}", "zh-TW": "{name} · commit {commit} · {files}", "zh-CN": "{name} · commit {commit} · {files}"},
  "skill_scripts": {
    "en": "{name} · commit {commit} · {files}, {scripts}",
    "zh-TW": "{name} · commit {commit} · {files}、{scripts}",
    "zh-CN": "{name} · commit {commit} · {files}、{scripts}"
  },
  "script_count_one": {"en": "1 script", "zh-TW": "1 個腳本", "zh-CN": "1 个脚本"},
  "script_count": {"en": "{count} scripts", "zh-TW": "{count} 個腳本", "zh-CN": "{count} 个脚本"},
  "scripts": {"en": "scripts: {count}, e.g. {names}", "zh-TW": "{count} 個腳本，例如 {names}", "zh-CN": "{count} 个脚本，例如 {names}"},
  "exists_fails": {
    "en": "exists: {path} (installing at local or project fails)",
    "zh-TW": "已存在：{path}（安裝在 local 或 project 會失敗）",
    "zh-CN": "已存在：{path}（安装在 local 或 project 会失败）"
  },
  "exists_replaces": {
    "en": "exists: {path} (installing at local or project replaces it)",
    "zh-TW": "已存在：{path}（安裝在 local 或 project 會取代它）",
    "zh-CN": "已存在：{path}（安装在 local 或 project 会替换它）"
  },
  "installs_at_user": {
    "en": "installs at: user (~/.codex/config.toml, every project)",
    "zh-TW": "安裝位置：user（~/.codex/config.toml，所有專案）",
    "zh-CN": "安装位置：user（~/.codex/config.toml，所有项目）"
  },
  "installs_at_user_skill": {
    "en": "installs at: user (~/.agents/skills/; Codex did not say which project this session is in)",
    "zh-TW": "安裝位置：user（~/.agents/skills/；Codex 沒有說這個工作階段在哪個專案）",
    "zh-CN": "安装位置：user（~/.agents/skills/；Codex 没有说这个会话在哪个项目）"
  },
  "check_files_one": {"en": "1 file", "zh-TW": "1 個檔案", "zh-CN": "1 个文件"},
  "check_files": {"en": "{count} files", "zh-TW": "{count} 個檔案", "zh-CN": "{count} 个文件"},
  "check_deps_one": {"en": "1 {ecosystem} dependency", "zh-TW": "1 個 {ecosystem} 相依套件", "zh-CN": "1 个 {ecosystem} 依赖包"},
  "check_deps": {"en": "{count} {ecosystem} dependencies", "zh-TW": "{count} 個 {ecosystem} 相依套件", "zh-CN": "{count} 个 {ecosystem} 依赖包"},
  "check_nothing": {"en": "✓ check: nothing found ({files}, no npm or Python dependency files, advisory and malware lookups)", "zh-TW": "✓ 檢查：沒有發現（{files}、沒有 npm 或 Python 相依套件檔、漏洞與惡意套件查詢）", "zh-CN": "✓ 检查：没有发现（{files}、没有 npm 或 Python 依赖文件、漏洞与恶意包查询）"},
  "check_nothing_deps": {"en": "✓ check: nothing found ({files}, {deps}, advisory and malware lookups)", "zh-TW": "✓ 檢查：沒有發現（{files}、{deps}、漏洞與惡意套件查詢）", "zh-CN": "✓ 检查：没有发现（{files}、{deps}、漏洞与恶意包查询）"},
  "check_blocked": {"en": "✕ blocked: the malware lookup found a known-malicious package, so Install is not offered", "zh-TW": "✕ 已擋下：惡意套件查詢找到已知的惡意套件，所以不提供安裝", "zh-CN": "✕ 已拦下：恶意包查询找到已知的恶意包，所以不提供安装"},
  "check_unchecked": {"en": "? unchecked: pattern scan, advisory lookup and malware lookup ({why})", "zh-TW": "？未檢查：pattern 掃描、漏洞查詢和惡意套件查詢（{why}）", "zh-CN": "？未检查：pattern 扫描、漏洞查询和恶意包查询（{why}）"},
  "check_unchecked_not_pinned": {"en": "? unchecked: pattern scan, advisory lookup and malware lookup ({why}); not pinned", "zh-TW": "？未檢查：pattern 掃描、漏洞查詢和惡意套件查詢（{why}）；未鎖定版本", "zh-CN": "？未检查：pattern 扫描、漏洞查询和恶意包查询（{why}）；未锁定版本"},
  "scan_no_warn": {"en": "✓ pattern scan: no danger or warn findings", "zh-TW": "✓ pattern 掃描：沒有危險或警告的發現", "zh-CN": "✓ pattern 扫描：没有危险或警告的发现"},
  "scan_unread": {"en": "? unchecked: pattern scan of {count} binary or large files", "zh-TW": "？未檢查：{count} 個二進位或過大檔案的 pattern 掃描", "zh-CN": "？未检查：{count} 个二进制或过大文件的 pattern 扫描"},
  "scan_unchecked": {"en": "? unchecked: pattern scan ({why})", "zh-TW": "？未檢查：pattern 掃描（{why}）", "zh-CN": "？未检查：pattern 扫描（{why}）"},
  "scan_send_secrets": {"en": "may send secrets out", "zh-TW": "可能外傳密鑰", "zh-CN": "可能外传密钥"},
  "scan_download_run": {"en": "may download and run code", "zh-TW": "可能下載並執行程式碼", "zh-CN": "可能下载并执行代码"},
  "scan_download_decode": {"en": "may download and decode a payload", "zh-TW": "可能下載並解碼資料", "zh-CN": "可能下载并解码数据"},
  "scan_hidden_unicode": {"en": "hidden Unicode", "zh-TW": "隱藏 Unicode", "zh-CN": "隐藏 Unicode"},
  "scan_injection_phrase": {"en": "prompt-injection phrases", "zh-TW": "提示詞注入字句", "zh-CN": "提示词注入语句"},
  "scan_credentials": {"en": "credentials", "zh-TW": "憑證", "zh-CN": "凭据"},
  "scan_startup_files": {"en": "changes shell startup files", "zh-TW": "修改啟動檔", "zh-CN": "修改启动文件"},
  "warn": {"en": "⚠ warn ({count}): {names}", "zh-TW": "⚠ 警告 {count} 項：{names}", "zh-CN": "⚠ 警告 {count} 项：{names}"},
  "warn_review": {"en": "model review ({count})", "zh-TW": "模型審查 {count} 項", "zh-CN": "模型审查 {count} 项"},
  "review_nothing": {"en": "✓ model review: nothing found", "zh-TW": "✓ 模型審查：沒有發現", "zh-CN": "✓ 模型审查：没有发现"},
  "review_not_run": {"en": "? model review: did not run", "zh-TW": "？模型審查：未執行", "zh-CN": "？模型审查：未执行"},
  "review_not_run_why": {"en": "? model review: did not run ({why})", "zh-TW": "？模型審查：未執行（{why}）", "zh-CN": "？模型审查：未执行（{why}）"},
  "review_no_result": {"en": "no review result was passed", "zh-TW": "沒有傳入審查結果", "zh-CN": "没有传入审查结果"},
  "review_no_files": {"en": "kirby had no files of it to read", "zh-TW": "kirby 沒有它的檔案可讀", "zh-CN": "kirby 没有它的文件可读"},
  "review_other_commit": {
    "en": "it read {read}, not {checked}, the one checked here",
    "zh-TW": "它讀的是 {read}，不是這裡檢查的 {checked}",
    "zh-CN": "它读的是 {read}，不是这里检查的 {checked}"
  },
  "warn_package_vulns": {"en": "{vulns} in {package} ({ecosystem})", "zh-TW": "{package} ({ecosystem}) 的 {vulns}", "zh-CN": "{package} ({ecosystem}) 的 {vulns}"},
  "warn_repo_advisories": {"en": "advisories this repo published ({count})", "zh-TW": "這個 repo 發布的 {count} 則安全公告", "zh-CN": "这个 repo 发布的 {count} 条安全公告"},
  "danger_malware": {"en": "✕ danger: {package} ({ecosystem}) is listed as malicious ({ids})", "zh-TW": "✕ 危險：{package} ({ecosystem}) 被列為惡意套件（{ids}）", "zh-CN": "✕ 危险：{package} ({ecosystem}) 被列为恶意包（{ids}）"},
  "danger_malware_by_name": {"en": "✕ danger: {package} ({ecosystem}) is listed as malicious ({ids}); matched by name, the version was not resolved", "zh-TW": "✕ 危險：{package} ({ecosystem}) 被列為惡意套件（{ids}）；以名稱比對，版本未解析", "zh-CN": "✕ 危险：{package} ({ecosystem}) 被列为恶意包（{ids}）；按名称匹配，版本未解析"},
  "danger_vulns": {
    "en": "✕ danger: {package} ({ecosystem}) has {vulns}, worst {rating} ({ids})",
    "zh-TW": "✕ 危險：{package} ({ecosystem}) 有 {vulns}，最高評級為「{rating}」（{ids}）",
    "zh-CN": "✕ 危险：{package} ({ecosystem}) 有 {vulns}，最高评级为“{rating}”（{ids}）"
  },
  "rating_critical": {"en": "critical", "zh-TW": "嚴重", "zh-CN": "严重"},
  "rating_high": {"en": "high", "zh-TW": "高", "zh-CN": "高"},
  "rating_moderate": {"en": "moderate", "zh-TW": "中等", "zh-CN": "中等"},
  "rating_low": {"en": "low", "zh-TW": "低", "zh-CN": "低"},
  "danger_commit_malware": {"en": "✕ danger: this commit is listed as malicious ({ids})", "zh-TW": "✕ 危險：這個 commit 被列為惡意（{ids}）", "zh-CN": "✕ 危险：这个 commit 被列为恶意（{ids}）"},
  "danger_package_affected": {"en": "✕ danger: {package} ({ecosystem}) is affected by {vulns} ({ids})", "zh-TW": "✕ 危險：{package} ({ecosystem}) 受 {vulns}影響（{ids}）", "zh-CN": "✕ 危险：{package} ({ecosystem}) 受 {vulns}影响（{ids}）"},
  "danger_commit_vulns": {"en": "✕ danger: this commit is affected by {vulns} ({ids})", "zh-TW": "✕ 危險：這個 commit 受 {vulns}影響（{ids}）", "zh-CN": "✕ 危险：这个 commit 受 {vulns}影响（{ids}）"},
  "danger_more": {"en": "✕ danger: {count} more, listed for the model", "zh-TW": "✕ 危險：另有 {count} 項，已交給模型", "zh-CN": "✕ 危险：另有 {count} 项，已交给模型"},
  "lookup_vulns_one": {"en": "1 published vulnerability", "zh-TW": "1 個已公開漏洞", "zh-CN": "1 个已公开漏洞"},
  "lookup_vulns": {"en": "{count} published vulnerabilities", "zh-TW": "{count} 個已公開漏洞", "zh-CN": "{count} 个已公开漏洞"},
  "lookup_deps": {"en": "dependencies: {files}", "zh-TW": "相依套件：{files}", "zh-CN": "依赖包：{files}"},
  "lookup_deps_file": {"en": "{file}: {count} {ecosystem}", "zh-TW": "{file}：{count} 個 {ecosystem}", "zh-CN": "{file}：{count} 个 {ecosystem}"},
  "lookup_deps_file_resolved": {"en": "{file}: {count} {ecosystem}, versions resolved at check time", "zh-TW": "{file}：{count} 個 {ecosystem}，版本是檢查當下算出的", "zh-CN": "{file}：{count} 个 {ecosystem}，版本是检查时算出的"},
  "lookup_deps_file_names": {"en": "{file}: {count} {ecosystem}, names only", "zh-TW": "{file}：{count} 個 {ecosystem}，只有名稱", "zh-CN": "{file}：{count} 个 {ecosystem}，只有名称"},
  "lookup_deps_file_unreadable": {"en": "{file}: {count} {ecosystem}, could not be read", "zh-TW": "{file}：{count} 個 {ecosystem}，無法讀取", "zh-CN": "{file}：{count} 个 {ecosystem}，无法读取"},
  "lookup_nothing": {"en": "✓ advisory and malware lookups: nothing found", "zh-TW": "✓ 漏洞、惡意套件查詢：沒有發現", "zh-CN": "✓ 漏洞、恶意包查询：没有发现"},
  "lookup_nothing_rest": {"en": "✓ advisory and malware lookups: nothing found in the rest", "zh-TW": "✓ 漏洞、惡意套件查詢：其餘沒有發現", "zh-CN": "✓ 漏洞、恶意包查询：其余没有发现"},
  "lookup_advisory_nothing": {"en": "✓ advisory lookup: nothing found", "zh-TW": "✓ 漏洞查詢：沒有發現", "zh-CN": "✓ 漏洞查询：没有发现"},
  "lookup_advisory_nothing_rest": {"en": "✓ advisory lookup: nothing found in the rest", "zh-TW": "✓ 漏洞查詢：其餘沒有發現", "zh-CN": "✓ 漏洞查询：其余没有发现"},
  "lookup_malware_nothing": {"en": "✓ malware lookup: nothing found", "zh-TW": "✓ 惡意套件查詢：沒有發現", "zh-CN": "✓ 恶意包查询：没有发现"},
  "lookup_malware_nothing_rest": {"en": "✓ malware lookup: nothing found in the rest", "zh-TW": "✓ 惡意套件查詢：其餘沒有發現", "zh-CN": "✓ 恶意包查询：其余没有发现"},
  "lookup_unchecked_advisory": {"en": "? unchecked: advisory lookup for {parts} ({why})", "zh-TW": "？未檢查：{parts} 的漏洞查詢（{why}）", "zh-CN": "？未检查：{parts} 的漏洞查询（{why}）"},
  "lookup_unchecked_malware": {"en": "? unchecked: malware lookup for {parts} ({why})", "zh-TW": "？未檢查：{parts} 的惡意套件查詢（{why}）", "zh-CN": "？未检查：{parts} 的恶意包查询（{why}）"},
  "lookup_unchecked_both": {"en": "? unchecked: advisory and malware lookups for {parts} ({why})", "zh-TW": "？未檢查：{parts} 的漏洞、惡意套件查詢（{why}）", "zh-CN": "？未检查：{parts} 的漏洞、恶意包查询（{why}）"},
  "lookup_unchecked_split": {"en": "? unchecked: advisory lookup for {advisory}; malware lookup for {malware} ({why})", "zh-TW": "？未檢查：{advisory} 的漏洞查詢；{malware} 的惡意套件查詢（{why}）", "zh-CN": "？未检查：{advisory} 的漏洞查询；{malware} 的恶意包查询（{why}）"},
  "lookup_part_commit": {"en": "this commit", "zh-TW": "這個 commit", "zh-CN": "这个 commit"},
  "lookup_part_package": {"en": "the package {package} ({ecosystem})", "zh-TW": "套件 {package} ({ecosystem})", "zh-CN": "包 {package} ({ecosystem})"},
  "lookup_part_repo_advisories": {"en": "this repo's advisories", "zh-TW": "這個 repo 的安全公告", "zh-CN": "这个 repo 的安全公告"},
  "lookup_part_dependencies": {"en": "the dependencies of {package}", "zh-TW": "{package} 的相依套件", "zh-CN": "{package} 的依赖包"},
  "lookup_part_more_files": {"en": "more dependency files ({files})", "zh-TW": "其他相依套件檔（{files}）", "zh-CN": "其他依赖文件（{files}）"},
  "lookup_part_ratings": {"en": "the rating of advisories ({count})", "zh-TW": "{count} 則安全公告的評級", "zh-CN": "{count} 条安全公告的评级"},
  "why_remote": {
    "en": "a remote server at a URL; its code does not install here",
    "zh-TW": "URL 上的遠端 server；它的程式碼不會安裝在這裡",
    "zh-CN": "URL 上的远程 server；它的代码不会安装在这里"
  },
  "why_container": {
    "en": "the command runs a container image, which kirby does not check",
    "zh-TW": "指令執行的是 container image，kirby 不檢查它",
    "zh-CN": "命令运行的是 container image，kirby 不检查它"
  },
  "why_package_files": {
    "en": "could not read this repo's package files: {error}",
    "zh-TW": "讀不到這個 repo 的套件檔：{error}",
    "zh-CN": "读不到这个 repo 的包文件：{error}"
  },
  "why_no_package": {
    "en": "this repo names no npm or PyPI package in a server.json, package.json or pyproject.toml",
    "zh-TW": "這個 repo 的 server.json、package.json 或 pyproject.toml 沒有寫任何 npm 或 PyPI 套件",
    "zh-CN": "这个 repo 的 server.json、package.json 或 pyproject.toml 没有写任何 npm 或 PyPI 包"
  },
  "why_none_named": {
    "en": "the command runs none of the packages this repo names: {names}",
    "zh-TW": "指令執行的不是這個 repo 寫的任何套件：{names}",
    "zh-CN": "命令运行的不是这个 repo 写的任何包：{names}"
  },
  "why_range": {
    "en": "the command asks for {spec}, a range kirby does not resolve",
    "zh-TW": "指令要求 {spec}，kirby 不解析這種範圍",
    "zh-CN": "命令要求 {spec}，kirby 不解析这种范围"
  },
  "why_source_other": {
    "en": "its source is {what}, which kirby does not fetch",
    "zh-TW": "kirby 不抓取這個來源：{what}",
    "zh-CN": "kirby 不获取这个来源：{what}"
  },
  "why_needs_python": {
    "en": "could not be read (needs Python 3.11 or later)",
    "zh-TW": "無法讀取（需要 Python 3.11 以上）",
    "zh-CN": "无法读取（需要 Python 3.11 或更高版本）"
  },
  "why_unreadable": {"en": "could not be read ({error})", "zh-TW": "無法讀取（{error}）", "zh-CN": "无法读取（{error}）"},
  "why_elsewhere": {
    "en": "some dependencies come from outside the npm registry, so versions were not resolved",
    "zh-TW": "有些相依套件來自 npm registry 以外，所以沒有算出版本",
    "zh-CN": "有些依赖来自 npm registry 以外，所以没有算出版本"
  },
  "why_tool_missing": {
    "en": "{tool} not found, so versions were not resolved",
    "zh-TW": "找不到 {tool}，所以沒有算出版本",
    "zh-CN": "找不到 {tool}，所以没有算出版本"
  },
  "why_unresolved": {
    "en": "{tool} could not resolve the versions: {error}",
    "zh-TW": "{tool} 無法算出版本：{error}",
    "zh-CN": "{tool} 无法算出版本：{error}"
  },
  "why_at_most": {"en": "kirby reads at most {count}", "zh-TW": "kirby 最多讀 {count} 個", "zh-CN": "kirby 最多读 {count} 个"},
  "why_no_record": {"en": "OSV.dev did not return the record", "zh-TW": "OSV.dev 沒有傳回紀錄", "zh-CN": "OSV.dev 没有返回记录"},
  "plugin": {
    "en": "plugin: {name} · marketplace {marketplace} · commit {commit}",
    "zh-TW": "外掛：{name} · marketplace {marketplace} · commit {commit}",
    "zh-CN": "插件：{name} · marketplace {marketplace} · commit {commit}"
  },
  "plugin_files": {
    "en": "plugin: {name} · marketplace {marketplace} · commit {commit} · {files} files",
    "zh-TW": "外掛：{name} · marketplace {marketplace} · commit {commit} · {files} 個檔案",
    "zh-CN": "插件：{name} · marketplace {marketplace} · commit {commit} · {files} 个文件"
  },
  "plugin_description": {"en": "description: {text}", "zh-TW": "說明：{text}", "zh-CN": "说明：{text}"},
  "plugin_source_root": {"en": "source: the root of this repo", "zh-TW": "來源：這個 repo 的根目錄", "zh-CN": "来源：这个 repo 的根目录"},
  "plugin_source_folder": {"en": "source: {path}/ in this repo", "zh-TW": "來源：這個 repo 的 {path}/", "zh-CN": "来源：这个 repo 的 {path}/"},
  "plugin_source_pinned": {
    "en": "source: {source} at commit {commit}, pinned by the marketplace entry",
    "zh-TW": "來源：{source}，commit {commit}，由 marketplace 項目鎖定",
    "zh-CN": "来源：{source}，commit {commit}，由 marketplace 条目锁定"
  },
  "plugin_source_unpinned": {
    "en": "source: {source} at commit {commit} ({ref}); not pinned: the marketplace entry gives no sha, so what installs may differ from what was checked",
    "zh-TW": "來源：{source}，commit {commit}（{ref}）；未鎖定：marketplace 項目沒有給 sha，安裝的內容可能和檢查過的不同",
    "zh-CN": "来源：{source}，commit {commit}（{ref}）；未锁定：marketplace 条目没有给出 sha，安装的内容可能与检查过的不同"
  },
  "plugin_source_unpinned_default": {
    "en": "source: {source} at commit {commit} (default branch); not pinned: the marketplace entry gives no sha, so what installs may differ from what was checked",
    "zh-TW": "來源：{source}，commit {commit}（預設分支）；未鎖定：marketplace 項目沒有給 sha，安裝的內容可能和檢查過的不同",
    "zh-CN": "来源：{source}，commit {commit}（默认分支）；未锁定：marketplace 条目没有给出 sha，安装的内容可能与检查过的不同"
  },
  "plugin_source_unfetched": {
    "en": "source: {source}, which kirby could not fetch",
    "zh-TW": "來源：{source}，kirby 無法取得",
    "zh-CN": "来源：{source}，kirby 无法获取"
  },
  "plugin_source_other": {"en": "source: {what}", "zh-TW": "來源：{what}", "zh-CN": "来源：{what}"},
  "source_kind": {"en": "a {kind} source", "zh-TW": "{kind} 來源", "zh-CN": "{kind} 来源"},
  "source_outside_github": {"en": "a git repo outside GitHub", "zh-TW": "GitHub 以外的 git repo", "zh-CN": "GitHub 以外的 git repo"},
  "source_none": {"en": "an entry with no source", "zh-TW": "沒有寫來源的項目", "zh-CN": "没有写来源的条目"},
  "source_path_outside": {
    "en": "the path {path}, which is not inside {repo}",
    "zh-TW": "路徑 {path}，不在 {repo} 裡",
    "zh-CN": "路径 {path}，不在 {repo} 里"
  },
  "source_path_outside_repo": {
    "en": "the path {path}, which is not inside the repo",
    "zh-TW": "路徑 {path}，不在 repo 裡",
    "zh-CN": "路径 {path}，不在 repo 里"
  },
  "plugin_dependencies": {
    "en": "installed along with it, not checked: {plugins}",
    "zh-TW": "會一起安裝、未檢查：{plugins}",
    "zh-CN": "会一起安装、未检查：{plugins}"
  },
  "marketplace_added": {
    "en": "marketplace: already added as {name}, at commit {commit}; installs from it as it is",
    "zh-TW": "marketplace：已加入，名稱 {name}，在 commit {commit}；直接從它安裝",
    "zh-CN": "marketplace：已添加，名称 {name}，在 commit {commit}；直接从它安装"
  },
  "marketplace_refreshes": {
    "en": "marketplace: already added as {name}, at commit {commit}, behind its repo; installing refreshes it to {latest}, the commit checked",
    "zh-TW": "marketplace：已加入，名稱 {name}，在 commit {commit}，落後於它的 repo；安裝時會更新到檢查過的 commit {latest}",
    "zh-CN": "marketplace：已添加，名称 {name}，在 commit {commit}，落后于它的 repo；安装时会更新到检查过的 commit {latest}"
  },
  "marketplace_refreshes_unread": {
    "en": "marketplace: already added as {name}, at a commit kirby could not read; installing refreshes it to {latest}, the commit checked",
    "zh-TW": "marketplace：已加入，名稱 {name}，kirby 讀不到它在哪個 commit；安裝時會更新到檢查過的 commit {latest}",
    "zh-CN": "marketplace：已添加，名称 {name}，kirby 读不到它在哪个 commit；安装时会更新到检查过的 commit {latest}"
  },
  "marketplace_behind_unknown": {
    "en": "? unchecked: whether the marketplace {name}, at commit {commit}, is behind its repo ({why}); if it is, installing refreshes it, and the plugin is removed again if it then comes from another commit",
    "zh-TW": "？未檢查：marketplace {name}（在 commit {commit}）是否落後於它的 repo（{why}）；若是，安裝時會更新它，外掛若因此來自另一個 commit 會再移除",
    "zh-CN": "？未检查：marketplace {name}（在 commit {commit}）是否落后于它的 repo（{why}）；如果是，安装时会更新它，插件如果因此来自另一个 commit 会再移除"
  },
  "marketplace_behind_unknown_unread": {
    "en": "? unchecked: whether the marketplace {name}, at a commit kirby could not read, is behind its repo ({why}); if it is, installing refreshes it, and the plugin is removed again if it then comes from another commit",
    "zh-TW": "？未檢查：marketplace {name}（kirby 讀不到它在哪個 commit）是否落後於它的 repo（{why}）；若是，安裝時會更新它，外掛若因此來自另一個 commit 會再移除",
    "zh-CN": "？未检查：marketplace {name}（kirby 读不到它在哪个 commit）是否落后于它的 repo（{why}）；如果是，安装时会更新它，插件如果因此来自另一个 commit 会再移除"
  },
  "marketplace_not_listed": {
    "en": "? unchecked: whether this marketplace is already added ({why}); the check is of its repo as it stands, and the plugin is removed again if kirby cannot tell it installs from that commit",
    "zh-TW": "？未檢查：這個 marketplace 是否已加入（{why}）；檢查的是它的 repo 目前的狀態，若 kirby 無法確認外掛是從那個 commit 安裝的，會再移除",
    "zh-CN": "？未检查：这个 marketplace 是否已添加（{why}）；检查的是它的 repo 当前的状态，如果 kirby 无法确认插件是从那个 commit 安装的，会再移除"
  },
  "marketplace_head_unread": {
    "en": "? unchecked: which commit the marketplace {name}, already added, is at ({why}); the check is of its repo as it stands, and the plugin is removed again if kirby cannot tell it installs from that commit",
    "zh-TW": "？未檢查：已加入的 marketplace {name} 在哪個 commit（{why}）；檢查的是它的 repo 目前的狀態，若 kirby 無法確認外掛是從那個 commit 安裝的，會再移除",
    "zh-CN": "？未检查：已添加的 marketplace {name} 在哪个 commit（{why}）；检查的是它的 repo 当前的状态，如果 kirby 无法确认插件是从那个 commit 安装的，会再移除"
  },
  "marketplace_claude_format": {
    "en": "marketplace: {file} (Claude Code format)",
    "zh-TW": "marketplace：{file}（Claude Code 格式）",
    "zh-CN": "marketplace：{file}（Claude Code 格式）"
  },
  "mcp_server": {"en": "MCP server: {command}", "zh-TW": "MCP server：{command}", "zh-CN": "MCP server：{command}"},
  "mcp_package": {
    "en": "package: {package} ({ecosystem}), named by this repo's {file}; not verified to come from this repo",
    "zh-TW": "套件：{package}（{ecosystem}），由這個 repo 的 {file} 指名；沒有驗證它來自這個 repo",
    "zh-CN": "包：{package}（{ecosystem}），由这个 repo 的 {file} 指定；没有验证它来自这个 repo"
  },
  "mcp_pinned": {
    "en": "pinned: only {name}, to {version}; its dependencies are not pinned, so they may differ from those checked when the server starts",
    "zh-TW": "已鎖定：只有 {name}，鎖定在 {version}；它的相依套件沒有鎖定，server 啟動時可能和檢查過的不同",
    "zh-CN": "已锁定：只有 {name}，锁定在 {version}；它的依赖没有锁定，server 启动时可能与检查过的不同"
  },
  "mcp_pinned_range": {
    "en": "pinned: only {name}, to {version}, the highest version matching {range}; its dependencies are not pinned, so they may differ from those checked when the server starts",
    "zh-TW": "已鎖定：只有 {name}，鎖定在符合 {range} 的最高版本 {version}；它的相依套件沒有鎖定，server 啟動時可能和檢查過的不同",
    "zh-CN": "已锁定：只有 {name}，锁定在符合 {range} 的最高版本 {version}；它的依赖没有锁定，server 启动时可能与检查过的不同"
  },
  "mcp_not_pinned": {
    "en": "not pinned: kirby could not tell which version of {name} the command installs ({why}); it installs as given",
    "zh-TW": "未鎖定：kirby 無法確定指令會安裝 {name} 的哪個版本（{why}）；會照原樣安裝",
    "zh-CN": "未锁定：kirby 无法确定命令会安装 {name} 的哪个版本（{why}）；会按原样安装"
  },
  "scope_cache": {
    "en": "prompt cache: this plugin brings an MCP server; if tool search is off in this session, loading it with /reload-plugins rebuilds the cache once.",
    "zh-TW": "prompt cache：這個外掛帶有 MCP server；如果這個工作階段關閉了 tool search，用 /reload-plugins 載入它會重建一次 cache。",
    "zh-CN": "prompt cache：这个插件带有 MCP server；如果这个会话关闭了 tool search，用 /reload-plugins 加载它会重建一次 cache。"
  },
  "scope_cache_off": {
    "en": "prompt cache: this plugin brings an MCP server; ENABLE_TOOL_SEARCH=false is set, so loading it with /reload-plugins rebuilds the cache once.",
    "zh-TW": "prompt cache：這個外掛帶有 MCP server；已設定 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 載入它會重建一次 cache。",
    "zh-CN": "prompt cache：这个插件带有 MCP server；已设置 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 加载它会重建一次 cache。"
  },
  "scope_cache_maybe": {
    "en": "prompt cache: this plugin may bring an MCP server (its source was not checked); if tool search is off in this session, loading it with /reload-plugins rebuilds the cache once.",
    "zh-TW": "prompt cache：這個外掛可能帶有 MCP server（它的來源沒有檢查）；如果這個工作階段關閉了 tool search，用 /reload-plugins 載入它會重建一次 cache。",
    "zh-CN": "prompt cache：这个插件可能带有 MCP server（它的来源没有检查）；如果这个会话关闭了 tool search，用 /reload-plugins 加载它会重建一次 cache。"
  },
  "scope_cache_maybe_off": {
    "en": "prompt cache: this plugin may bring an MCP server (its source was not checked); ENABLE_TOOL_SEARCH=false is set, so loading it with /reload-plugins rebuilds the cache once.",
    "zh-TW": "prompt cache：這個外掛可能帶有 MCP server（它的來源沒有檢查）；已設定 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 載入它會重建一次 cache。",
    "zh-CN": "prompt cache：这个插件可能带有 MCP server（它的来源没有检查）；已设置 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 加载它会重建一次 cache。"
  },
  "scope_install_at_user": {
    "en": "install at user (~/.codex/config.toml, every project)",
    "zh-TW": "安裝在 user（~/.codex/config.toml，所有專案）",
    "zh-CN": "安装在 user（~/.codex/config.toml，所有项目）"
  },
  "scope_install_at_user_skill": {
    "en": "install at user (~/.agents/skills/)",
    "zh-TW": "安裝在 user（~/.agents/skills/）",
    "zh-CN": "安装在 user（~/.agents/skills/）"
  }
}
// words:end

export type Key = Exclude<keyof typeof WORDS, 'list'>
// A value can be a fact itself (a name, a count with its noun), said in the same language; a list can hold facts.
export type Keyed = { key: Key; args: Record<string, Value> }
type Value = string | number | Keyed | readonly (string | Keyed)[]
export type Fact = string | Keyed

export function fact(key: Key, args: Record<string, Value> = {}): Keyed {
  return { key, args }
}

// n of something, with its noun: key's `_one` wording for 1 ("1 file"), else key's with count ("3 files").
export function counted(key: Key, n: number, args: Record<string, Value> = {}): Keyed {
  return n === 1 ? fact(`${key}_one` as Key, args) : fact(key, { count: n, ...args })
}

// The language the model picked, or English for anything else.
export function readLang(value: unknown): Lang {
  return LANGS.find(l => l === value) ?? 'en'
}

// One fact line in the language given.
export function say(f: Fact, lang: Lang): string {
  if (typeof f === 'string') return f
  const one = (v: string | number | Keyed): string => (typeof v === 'object' ? say(v, lang) : String(v))
  return WORDS[f.key][lang].replace(/\{(\w+)\}/g, (_, name: string) => {
    if (!(name in f.args)) throw new Error(`${f.key} needs ${name}`)
    const v = f.args[name]
    return Array.isArray(v) ? v.map(one).join(WORDS.list[lang]) : one(v as string | number | Keyed)
  })
}
