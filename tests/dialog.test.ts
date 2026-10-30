import { expect, test } from 'claude-code/testing'

import { CANCEL, countReview, english, nextOptions, readDialog, readReview, reviewNote, SCOPES } from '../hooks/dialog'
import { fact, readLang, say } from '../hooks/words'
import type { Fact, Key } from '../hooks/words'

const GOOD = {
  about: '把 archify 裝成 skill。',
  next: '下一步？',
  options: ['取消', '先讀 README', '換一個', '安裝'],
  scope: '裝在哪個範圍？',
}

test("the model's wording is used when it is complete", async () => {
  const { dialog, problem } = readDialog(GOOD)
  expect(problem).toBe(undefined)
  expect(dialog).toEqual({ ...GOOD, lang: 'en' })
})

test('lang picks the language of the facts; missing or any other value is English, and not a problem', async () => {
  expect(readDialog({ ...GOOD, lang: 'zh-TW' })).toEqual({ dialog: { ...GOOD, lang: 'zh-TW' } })
  expect(readDialog({ ...GOOD, lang: 'zh-CN' }).dialog.lang).toBe('zh-CN')
  for (const lang of ['ja', 'zh-Hant', 7]) expect(readDialog({ ...GOOD, lang })).toEqual({ dialog: { ...GOOD, lang: 'en' } })
  expect(english().lang).toBe('en')
})

test('about is one sentence of at most 120 characters, counted as characters, not UTF-16 units', async () => {
  expect(readDialog({ ...GOOD, about: '𠀀'.repeat(120) }).problem).toBe(undefined)
  expect(readDialog({ ...GOOD, lang: 'zh-TW', about: 'x'.repeat(121) }))
    .toEqual({ dialog: english(), problem: 'dialog.about, when given, must be at most 120 characters' })
})

test("the scope options are the tool's own", async () => {
  // Extra keys from an older skill, such as scopes, are ignored.
  const { dialog, problem } = readDialog({ ...GOOD, scopes: { user: '你所有的專案' } })
  expect(problem).toBe(undefined)
  expect('scopes' in dialog).toBe(false)
  expect(new Set([CANCEL, ...SCOPES]).size).toBe(4)
})

test('missing or unusable wording falls back to English and says why', async () => {
  expect(readDialog(undefined)).toEqual({ dialog: english(), problem: 'no dialog was given' })
  const bad = [
    { ...GOOD, next: '' },
    { ...GOOD, scope: '  ' },
    { ...GOOD, options: ['取消', '先讀 README', '安裝'] },
    { ...GOOD, options: ['取消', '取消', '換一個', '安裝'] },
    { ...GOOD, about: 'x'.repeat(121) },
  ]
  for (const raw of bad) {
    const { dialog, problem } = readDialog(raw)
    expect(dialog).toEqual(english())
    expect(typeof problem).toBe('string')
  }
})

// The model review's result as the install tool takes it (docs/adr/0002); the rules match codex/dialog.py.
const SHA = 'a'.repeat(40)
const NEEDED = { needed: true, repo: 'o/r', sha: SHA, files: ['s/SKILL.md', 's/run.sh'] }
const OK = { file: 's/run.sh', line: 1, reason: 'Runs a download.' }

test("findings are warn lines labelled as the model's", async () => {
  expect(readReview({ findings: [{ file: 's/run.sh', line: 3, reason: 'Sends the token to a host.' }] }, SHA, NEEDED))
    .toEqual({ lines: ['warn: s/run.sh:3: Sends the token to a host. (model review, as reported by the model)'] })
  expect(readReview({ findings: [] }, SHA, NEEDED)).toEqual({ lines: ['model review: nothing found (as reported by the model)'] })
})

test('a missing review, one that could not run, or one of another commit is one unchecked line', async () => {
  expect(readReview(undefined, undefined, NEEDED)).toEqual({ lines: ['model review: unchecked (no review result was passed)'] })
  expect(readReview({ could_not_run: 'no subagent tool' }, undefined, NEEDED)).toEqual({ lines: ['model review: unchecked (no subagent tool)'] })
  expect(readReview(undefined, undefined, { needed: true, files: [] }))
    .toEqual({ lines: ['model review: unchecked (kirby had no files of it to read)'] })
  expect(readReview({ findings: [] }, 'b'.repeat(40), NEEDED))
    .toEqual({ lines: ['model review: unchecked (it read bbbbbbb, not aaaaaaa, the one checked here)'] })
})

test('without a danger or warn finding no review reaches the dialog', async () => {
  for (const raw of [undefined, { findings: [OK] }, { could_not_run: 'x' }, 'junk']) {
    expect(readReview(raw, SHA, { ...NEEDED, needed: false })).toEqual({ lines: [] })
  }
})

test('hidden and control characters are stripped', async () => {
  expect(readReview({ findings: [{ ...OK, reason: 'Reads​ ~/.ssh‮ and\nposts\tit.' }] }, SHA, NEEDED))
    .toEqual({ lines: ['warn: s/run.sh:1: Reads ~/.ssh and posts it. (model review, as reported by the model)'] })
  expect(readReview({ could_not_run: 'timed\x1b[2J out' }, undefined, NEEDED)).toEqual({ lines: ['model review: unchecked (timed [2J out)'] })
})

test('anything outside the structure or the limits is refused', async () => {
  const shape = 'review must be {"findings": [...]} or {"could_not_run": "<reason>"}'
  const cases: [unknown, string | undefined, string][] = [
    ['could not run: x', SHA, shape],
    [{ findings: [], could_not_run: 'x' }, SHA, shape],
    [{ findings: Array(6).fill(OK) }, SHA, 'review.findings must be a list of at most 5'],
    [{ findings: [{ ...OK, reason: 'x'.repeat(121) }] }, SHA, 'review.findings[0].reason must be one sentence of at most 120 characters'],
    [{ findings: [{ ...OK, reason: ' ​ ' }] }, SHA, 'review.findings[0].reason must be one sentence of at most 120 characters'],
    [{ findings: [OK, { ...OK, file: 's/other.sh' }] }, SHA, 'review.findings[1].file must be one of the files the check tool listed'],
    [{ findings: [{ ...OK, line: 0 }] }, SHA, 'review.findings[0].line must be a line number'],
    [{ findings: [{ ...OK, line: 1.5 }] }, SHA, 'review.findings[0].line must be a line number'],
    [{ findings: [{ ...OK, quote: 'x' }] }, SHA, 'review.findings[0] must have exactly file, line and reason'],
    [{ could_not_run: 'x'.repeat(121) }, SHA, 'review.could_not_run must be a reason of at most 120 characters'],
    [{ findings: [OK] }, undefined, 'sha must be the one the check tool returned, which the review read'],
  ]
  for (const [raw, sha, problem] of cases) expect(readReview(raw, sha, NEEDED)).toEqual({ lines: [], problem })
  // The limits count characters, not UTF-16 units.
  expect(readReview({ findings: [{ ...OK, reason: '𠀀'.repeat(120) }] }, SHA, NEEDED).problem).toBe(undefined)
})

test("the review's lines reach the model too", async () => {
  expect(reviewNote([])).toBe('')
  expect(reviewNote(['model review: unchecked (x)']))
    .toBe('review: the dialog showed the user these model review lines:\n  model review: unchecked (x)')
})

// kirby's own wording of a fact line, in the language the model picked (docs/adr/0006). The same cases are
// in tests/test_codex.py, so both sides give the same lines.
const SEVEN_WARN = fact('warn', {
  count: 7,
  names: ['scan_send_secrets', 'scan_download_run', 'scan_download_decode', 'scan_injection_phrase', 'scan_hidden_unicode',
    'scan_credentials', 'scan_startup_files'].map(k => fact(k as Key)),
})
const LODASH = fact('danger_vulns', {
  package: 'lodash@4.17.15', ecosystem: 'npm', vulns: fact('lookup_vulns', { count: 2 }), rating: 'high',
  ids: ['GHSA-35jh-r3h4-6jhm', 'GHSA-p6mc-m468-83gw'],
})
const WARN_WITH_REVIEW = fact('warn', {
  count: 3, names: [fact('scan_send_secrets'), fact('scan_hidden_unicode'), fact('warn_review', { count: 1 })],
})
const SPLIT = fact('lookup_unchecked_split', {
  advisory: [fact('lookup_part_commit'), 'package-lock.json'], malware: ['package-lock.json'], why: 'OSV.dev: timed out',
})
const ZH_TW: [Fact, string][] = [
  [fact('repo', { repo: 'o/r', stars: 52770, pushed: '2026-09-14' }), 'o/r ★52770 · 2026-09-14 更新'],
  [fact('repo_archived', { repo: 'o/r', stars: 3, pushed: '?' }), 'o/r ★3 · ? 更新 · 已封存'],
  [fact('skill', { name: 'security-audit', commit: 'b673708', files: 23 }), '技能：security-audit · commit b673708 · 23 個檔案'],
  [fact('scripts', { count: 6, names: ['run.sh', 'setup.py'] }), '6 個腳本，例如 run.sh、setup.py'],
  [fact('exists_fails', { path: '.claude/skills/s/' }), '已存在：.claude/skills/s/（安裝在 local 或 project 會失敗）'],
  [fact('exists_replaces', { path: '.agents/skills/s/' }), '已存在：.agents/skills/s/（安裝在 local 或 project 會取代它）'],
  [fact('installs_at_user'), '安裝位置：user（~/.codex/config.toml，所有專案）'],
  [fact('installs_at_user_skill'), '安裝位置：user（~/.agents/skills/；Codex 沒有說這個工作階段在哪個專案）'],
  [fact('plugin', { name: 'p', marketplace: 'mk', commit: 'aaaaaaa' }), '外掛：p · marketplace mk · commit aaaaaaa'],
  [fact('plugin_dependencies', { plugins: ['audit-logger', 'vault@shared'] }), '會一起安裝、未檢查：audit-logger、vault@shared'],
  [fact('plugin_source_unpinned_default', { source: 'x/src', commit: 'bbbbbbb' }),
    '來源：x/src，commit bbbbbbb（預設分支）；未鎖定：marketplace 項目沒有給 sha，安裝的內容可能和檢查過的不同'],
  [fact('marketplace_claude_format', { file: '.claude-plugin/marketplace.json' }), 'marketplace：.claude-plugin/marketplace.json（Claude Code 格式）'],
  [fact('mcp_server', { command: 'codex mcp add probe -- npx -y probe@1.0.0' }), 'MCP server：codex mcp add probe -- npx -y probe@1.0.0'],
  [fact('mcp_not_pinned', { name: 'srv', why: 'no version of srv matches ^9' }),
    '未鎖定：kirby 無法確定指令會安裝 srv 的哪個版本（no version of srv matches ^9）；會照原樣安裝'],
  [fact('scope_cache_off'), 'prompt cache：這個外掛帶有 MCP server；已設定 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 載入它會重建一次 cache。'],
  [fact('scope_install_at_user_skill'), '安裝在 user（~/.agents/skills/）'],
  ['check: nothing found (2 files)', 'check: nothing found (2 files)'],
  // The pre-install check's summary (#26), from the mock-ups in #24.
  [SEVEN_WARN, '⚠ 警告 7 項：可能外傳密鑰、可能下載並執行程式碼、可能下載並解碼資料、提示詞注入字句、隱藏 Unicode、憑證、修改啟動檔'],
  [fact('lookup_nothing'), '✓ 漏洞、惡意套件查詢：沒有發現'],
  [fact('danger_malware', { package: 'flatmap-stream', ecosystem: 'npm', ids: ['MAL-2025-20690'] }),
    '✕ 危險：flatmap-stream (npm) 被列為惡意套件（MAL-2025-20690）'],
  [LODASH, '✕ 危險：lodash@4.17.15 (npm) 有 2 個已公開漏洞，最嚴重為 high（GHSA-35jh-r3h4-6jhm、GHSA-p6mc-m468-83gw）'],
  [WARN_WITH_REVIEW, '⚠ 警告 3 項：可能外傳密鑰、隱藏 Unicode、模型審查 1 項'],
  [fact('check_nothing', { files: fact('check_files', { count: 23 }) }), '✓ 檢查：沒有發現（23 個檔案、沒有 npm 或 Python 相依套件檔、漏洞與惡意套件查詢）'],
  [fact('check_blocked'), '✕ 已擋下：惡意套件查詢找到已知的惡意套件，所以不提供安裝'],
  [fact('check_unchecked', { why: 'a remote server at a URL' }), '？ 未檢查：pattern 掃描、漏洞查詢和惡意套件查詢（a remote server at a URL）'],
  [SPLIT, '？ 未檢查：這個 commit、package-lock.json 的漏洞查詢；package-lock.json 的惡意套件查詢（OSV.dev: timed out）'],
]
const ZH_CN: [Fact, string][] = [
  [fact('repo', { repo: 'o/r', stars: 52770, pushed: '2026-09-14' }), 'o/r ★52770 · 2026-09-14 更新'],
  [fact('repo_archived', { repo: 'o/r', stars: 3, pushed: '?' }), 'o/r ★3 · ? 更新 · 已归档'],
  [fact('skill', { name: 'security-audit', commit: 'b673708', files: 23 }), '技能：security-audit · commit b673708 · 23 个文件'],
  [fact('scripts', { count: 6, names: ['run.sh', 'setup.py'] }), '6 个脚本，例如 run.sh、setup.py'],
  [fact('exists_fails', { path: '.claude/skills/s/' }), '已存在：.claude/skills/s/（安装在 local 或 project 会失败）'],
  [fact('exists_replaces', { path: '.agents/skills/s/' }), '已存在：.agents/skills/s/（安装在 local 或 project 会替换它）'],
  [fact('installs_at_user'), '安装位置：user（~/.codex/config.toml，所有项目）'],
  [fact('installs_at_user_skill'), '安装位置：user（~/.agents/skills/；Codex 没有说这个会话在哪个项目）'],
  [fact('plugin', { name: 'p', marketplace: 'mk', commit: 'aaaaaaa' }), '插件：p · marketplace mk · commit aaaaaaa'],
  [fact('plugin_dependencies', { plugins: ['audit-logger', 'vault@shared'] }), '会一起安装、未检查：audit-logger、vault@shared'],
  [fact('plugin_source_unpinned_default', { source: 'x/src', commit: 'bbbbbbb' }),
    '来源：x/src，commit bbbbbbb（默认分支）；未锁定：marketplace 条目没有给出 sha，安装的内容可能与检查过的不同'],
  [fact('marketplace_claude_format', { file: '.claude-plugin/marketplace.json' }), 'marketplace：.claude-plugin/marketplace.json（Claude Code 格式）'],
  [fact('mcp_server', { command: 'codex mcp add probe -- npx -y probe@1.0.0' }), 'MCP server：codex mcp add probe -- npx -y probe@1.0.0'],
  [fact('mcp_not_pinned', { name: 'srv', why: 'no version of srv matches ^9' }),
    '未锁定：kirby 无法确定命令会安装 srv 的哪个版本（no version of srv matches ^9）；会按原样安装'],
  [fact('scope_cache_off'), 'prompt cache：这个插件带有 MCP server；已设置 ENABLE_TOOL_SEARCH=false，所以用 /reload-plugins 加载它会重建一次 cache。'],
  [fact('scope_install_at_user_skill'), '安装在 user（~/.agents/skills/）'],
  ['check: nothing found (2 files)', 'check: nothing found (2 files)'],
  [SEVEN_WARN, '⚠ 警告 7 项：可能外传密钥、可能下载并执行代码、可能下载并解码数据、提示词注入语句、隐藏 Unicode、凭据、修改启动文件'],
  [fact('lookup_nothing'), '✓ 漏洞、恶意包查询：没有发现'],
  [fact('danger_malware', { package: 'flatmap-stream', ecosystem: 'npm', ids: ['MAL-2025-20690'] }),
    '✕ 危险：flatmap-stream (npm) 被列为恶意包（MAL-2025-20690）'],
  [LODASH, '✕ 危险：lodash@4.17.15 (npm) 有 2 个已公开漏洞，最严重为 high（GHSA-35jh-r3h4-6jhm、GHSA-p6mc-m468-83gw）'],
  [WARN_WITH_REVIEW, '⚠ 警告 3 项：可能外传密钥、隐藏 Unicode、模型审查 1 项'],
  [fact('check_nothing', { files: fact('check_files', { count: 23 }) }), '✓ 检查：没有发现（23 个文件、没有 npm 或 Python 依赖文件、漏洞与恶意包查询）'],
  [fact('check_blocked'), '✕ 已拦下：恶意包查询找到已知的恶意包，所以不提供安装'],
  [fact('check_unchecked', { why: 'a remote server at a URL' }), '？ 未检查：pattern 扫描、漏洞查询和恶意包查询（a remote server at a URL）'],
  [SPLIT, '？ 未检查：这个 commit、package-lock.json 的漏洞查询；package-lock.json 的恶意包查询（OSV.dev: timed out）'],
]
const EN: [Fact, string][] = [
  [fact('repo', { repo: 'o/r', stars: 52770, pushed: '2026-09-14' }), 'o/r ★52770 · pushed 2026-09-14'],
  [fact('repo_archived', { repo: 'o/r', stars: 3, pushed: '?' }), 'o/r ★3 · pushed ? · ARCHIVED'],
  [fact('skill', { name: 'security-audit', commit: 'b673708', files: 23 }), 'skill: security-audit · commit b673708 · 23 files'],
  [fact('scripts', { count: 6, names: ['run.sh', 'setup.py'] }), 'scripts: 6, e.g. run.sh, setup.py'],
  [fact('exists_fails', { path: '.claude/skills/s/' }), 'exists: .claude/skills/s/ (installing at local or project fails)'],
  [fact('exists_replaces', { path: '.agents/skills/s/' }), 'exists: .agents/skills/s/ (installing at local or project replaces it)'],
  [fact('installs_at_user'), 'installs at: user (~/.codex/config.toml, every project)'],
  [fact('installs_at_user_skill'), 'installs at: user (~/.agents/skills/; Codex did not say which project this session is in)'],
  [fact('plugin', { name: 'p', marketplace: 'mk', commit: 'aaaaaaa' }), 'plugin: p · marketplace mk · commit aaaaaaa'],
  [fact('plugin_dependencies', { plugins: ['audit-logger', 'vault@shared'] }), 'installed along with it, not checked: audit-logger, vault@shared'],
  [fact('plugin_source_unpinned_default', { source: 'x/src', commit: 'bbbbbbb' }),
    'source: x/src at commit bbbbbbb (default branch); not pinned: the marketplace entry gives no sha, so what installs may differ from what was checked'],
  [fact('marketplace_claude_format', { file: '.claude-plugin/marketplace.json' }), 'marketplace: .claude-plugin/marketplace.json (Claude Code format)'],
  [fact('mcp_server', { command: 'codex mcp add probe -- npx -y probe@1.0.0' }), 'MCP server: codex mcp add probe -- npx -y probe@1.0.0'],
  [fact('mcp_not_pinned', { name: 'srv', why: 'no version of srv matches ^9' }),
    'not pinned: kirby could not tell which version of srv the command installs (no version of srv matches ^9); it installs as given'],
  [fact('scope_cache_off'),
    'prompt cache: this plugin brings an MCP server; ENABLE_TOOL_SEARCH=false is set, so loading it with /reload-plugins rebuilds the cache once.'],
  [fact('scope_install_at_user_skill'), 'install at user (~/.agents/skills/)'],
  ['check: nothing found (2 files)', 'check: nothing found (2 files)'],
  [SEVEN_WARN, '⚠ warn (7): may send secrets out, may download and run code, may download and decode a payload, ' +
    'prompt-injection phrases, hidden Unicode, credentials, changes shell startup files'],
  [fact('lookup_nothing'), '✓ advisory and malware lookups: nothing found'],
  [fact('danger_malware', { package: 'flatmap-stream', ecosystem: 'npm', ids: ['MAL-2025-20690'] }),
    '✕ danger: flatmap-stream (npm) is listed as malicious (MAL-2025-20690)'],
  [LODASH, '✕ danger: lodash@4.17.15 (npm) has 2 published vulnerabilities, worst high (GHSA-35jh-r3h4-6jhm, GHSA-p6mc-m468-83gw)'],
  [WARN_WITH_REVIEW, '⚠ warn (3): may send secrets out, hidden Unicode, model review (1)'],
  [fact('check_nothing', { files: fact('check_files', { count: 23 }) }),
    '✓ check: nothing found (23 files, no npm or Python dependency files, advisory and malware lookups)'],
  [fact('check_blocked'), '✕ blocked: the malware lookup found a known-malicious package, so Install is not offered'],
  [fact('check_unchecked', { why: 'a remote server at a URL' }),
    '? unchecked: pattern scan, advisory lookup and malware lookup (a remote server at a URL)'],
  [SPLIT, '? unchecked: advisory lookup for this commit, package-lock.json; malware lookup for package-lock.json (OSV.dev: timed out)'],
]

test("kirby words each fact line in the language picked; a line it has no wording for stays as it is", async () => {
  for (const [f, line] of ZH_TW) expect(say(f, 'zh-TW')).toBe(line)
  for (const [f, line] of ZH_CN) expect(say(f, 'zh-CN')).toBe(line)
  for (const [f, line] of EN) expect(say(f, 'en')).toBe(line)
})

// For #28: the dialog counts the model review's findings on the warn line (docs/adr/0006). The same cases are in
// tests/test_codex.py.
test('a model review count joins the warn line, or makes one after the danger lines', async () => {
  const warn = fact('warn', { count: 1, names: [fact('scan_hidden_unicode')] })
  const nothing = fact('lookup_nothing')
  expect(countReview(['skill: s', warn, nothing], 2).map(f => say(f, 'zh-TW')))
    .toEqual(['skill: s', '⚠ 警告 3 項：隱藏 Unicode、模型審查 2 項', '✓ 漏洞、惡意套件查詢：沒有發現'])
  const danger = fact('danger_malware', { package: 'x', ecosystem: 'npm', ids: ['MAL-1'] })
  expect(countReview(['skill: s', danger, nothing], 1).map(f => say(f, 'en'))).toEqual([
    'skill: s', '✕ danger: x (npm) is listed as malicious (MAL-1)', '⚠ warn (1): model review (1)',
    '✓ advisory and malware lookups: nothing found',
  ])
  expect(countReview(['skill: s', fact('scan_no_warn'), nothing], 1).map(f => say(f, 'en'))).toEqual([
    'skill: s', '⚠ warn (1): model review (1)', '✓ pattern scan: no danger or warn findings',
    '✓ advisory and malware lookups: nothing found',
  ])
  expect(countReview(['skill: s', warn], 0)).toEqual(['skill: s', warn])
  expect(warn.args.count).toBe(1)
})

test('a value is put in as it is, even one that looks like a placeholder', async () => {
  expect(say(fact('skill', { name: '{commit}', commit: 'b673708', files: 1 }), 'en')).toBe('skill: {commit} · commit b673708 · 1 files')
})

test('the language is en, zh-TW or zh-CN; anything else is en', async () => {
  for (const l of ['en', 'zh-TW', 'zh-CN']) expect(readLang(l)).toBe(l)
  for (const l of [undefined, 'zh-tw', 'ja', 'zh', 1, null]) expect(readLang(l)).toBe('en')
})

test('a blocked install leaves Install out of the first dialog', async () => {
  const { dialog } = readDialog(GOOD)
  expect(nextOptions(dialog, false)).toEqual(['取消', '先讀 README', '換一個', '安裝'])
  expect(nextOptions(dialog, true)).toEqual(['取消', '先讀 README', '換一個'])
})
