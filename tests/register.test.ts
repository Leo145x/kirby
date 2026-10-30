import { expect, test } from 'claude-code/testing'

// The mod's own registrations and permission rule for the model review (docs/adr/0002), seen through the
// engine's interface: what it registers at session start, and what it decides for a tool call.

type Spec = { name: string; tools?: readonly string[]; disallowedTools?: readonly string[]; prompt: string; description: string }

test('the session starts with a reviewer agent that can use only check and file', async ($, on) => {
  const agents: Spec[] = []
  const tools: string[] = []
  on('tool.register', (_, e) => {
    tools.push(e.name)
    return { value: { tool: `mcp__kirby__${e.name}` } }
  })
  on('agent.register', (_, e) => {
    agents.push(e as Spec)
    return { value: { agent: `kirby:${e.name}` } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  expect(tools.sort()).toEqual(['check', 'file', 'install'])
  expect(agents.map(a => a.name)).toEqual(['reviewer'])
  expect(agents[0]?.tools).toEqual(['mcp__kirby__check', 'mcp__kirby__file'])
  // The structure and limits install takes (dialog.ts REVIEW_MAX), asked of the reviewer.
  const prompt = agents[0]?.prompt ?? ''
  expect(prompt).toContain('{"findings": [{"file": "<a path from FILES>", "line": <line number>, "reason": "<one sentence in your own words, at most 120 characters')
  expect(prompt).toContain('At most 5 findings')
  expect(prompt).toContain('{"could_not_run": "<why, at most 120 characters>"}')
})

test('kirby allows its own check and file tools without a prompt, and nothing else', async ($, on) => {
  // Stands for the engine: with no rule for a tool, the mode asks.
  on('tool.check', () => ({ decision: 'ask' }))

  for (const tool of ['mcp__kirby__check', 'mcp__kirby__file']) {
    expect((await $.tool.check({ tool, input: {} })).decision).toBe('allow')
  }
  for (const tool of ['mcp__kirby__install', 'Bash', 'mcp__other__file']) {
    expect((await $.tool.check({ tool, input: {} })).decision).toBe('ask')
  }
})

// The check tool of a plugin, with the processes it runs answered by run (argv joined by spaces → result).
async function checkPlugin($: Parameters<Parameters<typeof test>[1]>[0], on: Parameters<Parameters<typeof test>[1]>[1],
  run: (cmd: string) => { exitCode: number; stdout: string } | undefined) {
  const ran: string[] = []
  on('env.get', () => ({ value: undefined }))
  on('process.run', (_, e) => {
    const cmd = e.argv.join(' ')
    ran.push(cmd)
    const r = run(cmd) ?? { exitCode: 1, stdout: '' }
    return { value: { ...r, stderr: r.exitCode ? 'not this one' : '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  const r = await $.tool.call({ tool: 'mcp__kirby__check', repo: 'o/mk', kind: 'plugin', plugin: 'p' } as never)
  return { ran, out: JSON.parse(String((r as { result?: unknown }).result)) as { findings: string[] } }
}

const PLUGIN_FACTS = [{ key: 'plugin_files', args: { name: 'p', marketplace: 'mk', commit: 'aaaaaaa', files: 1 } }, 'check: nothing found']
const PLUGIN_CHECK = JSON.stringify({
  marketplace: 'mk', commit: 'aaaaaaa', sha: 'a'.repeat(40), facts: PLUGIN_FACTS,
  lines: ['plugin: p · marketplace mk · commit aaaaaaa · 1 files', 'check: nothing found'],
  note: 'pattern scan: none', blocked: false, mcp_servers: false, review: { needed: false, files: [] },
})

test('a marketplace list that fails is one unchecked line, and the check goes ahead', async ($, on) => {
  const { ran, out } = await checkPlugin($, on, cmd => (cmd.includes('check_plugin.py') ? { exitCode: 0, stdout: PLUGIN_CHECK } : undefined))
  expect(ran.some(c => c.includes('check_plugin.py') && !c.includes('--commit'))).toBe(true)
  expect(out.findings).toEqual([
    'plugin: p · marketplace mk · commit aaaaaaa · 1 files',
    'unchecked: whether this marketplace is already added (claude plugin marketplace list failed: not this one); the check is of ' +
      'its repo as it stands, and the plugin is removed again if kirby cannot tell it installs from that commit',
    'check: nothing found',
  ])
})

// A skill's first dialog shows kirby's lines in the language the model picked (dialog.lang), and the pre-install
// check's own lines as they are; what the tools answer the model stays English. The same cases are in
// tests/test_codex.py's Language.
const SKILL_CHECK = {
  name: 's', commit: 'aaaaaaa', sha: 'a'.repeat(40), files: 2, scripts: ['run.sh', 'setup.py', 'x.sh'], exists: true,
  lines: ['check: nothing found (2 files, no npm or Python dependency files, advisory and malware lookups)'],
  note: 'pattern scan: the dialog showed the user no pattern-scan findings', blocked: false, review: { needed: false, files: [] },
}
const WORDING = {
  about: '把 archify 裝成 skill。', next: '下一步？', options: ['取消', '先讀 README', '換一個', '安裝'], scope: '裝在哪個範圍？',
}

// The install or check tool of a skill, with gh and install_skill.py answered and every dialog answered 取消;
// asked collects the dialogs' questions.
function skillTool($: Parameters<Parameters<typeof test>[1]>[0], on: Parameters<Parameters<typeof test>[1]>[1]) {
  const asked: string[] = []
  on('ui.log', () => ({ value: undefined }))
  on('process.run', (_, e) => {
    const stdout = e.argv[0] === 'gh' ? '[52770,"2026-09-14T08:00:00Z",false]' : JSON.stringify(SKILL_CHECK)
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('tool.call', { tool: 'AskUserQuestion' }, (_, e) => {
    const q = (e as { questions: { question: string }[] }).questions[0]?.question ?? ''
    asked.push(q)
    return { result: { questions: (e as { questions: unknown[] }).questions, answers: { [q]: '取消' } } } as never
  })
  const call = async (input: Record<string, unknown>, tool = 'mcp__kirby__install') => {
    const r = await $.tool.call({ tool, repo: 'o/r', kind: 'skill', folder: 's', ...input } as never)
    return String((r as { result?: unknown }).result)
  }
  return { asked, call }
}

async function skill($: Parameters<Parameters<typeof test>[1]>[0], on: Parameters<Parameters<typeof test>[1]>[1],
  input: Record<string, unknown>, tool = 'mcp__kirby__install') {
  const { asked, call } = skillTool($, on)
  return { asked, result: await call(input, tool) }
}

test("with zh-TW kirby's lines are in 繁體中文", async ($, on) => {
  const { asked, result } = await skill($, on, { dialog: { ...WORDING, lang: 'zh-TW' } })
  expect(asked).toEqual([[
    'o/r ★52770 · 2026-09-14 更新',
    '技能：s · commit aaaaaaa · 2 個檔案',
    '3 個腳本，例如 run.sh、setup.py',
    '已存在：.claude/skills/s/（安裝在 local 或 project 會失敗）',
    ...SKILL_CHECK.lines,
  ].join('\n') + `\n\n${WORDING.about}\n\n${WORDING.next}`])
  expect(result).toBe(`not installed: the user cancelled.\n${SKILL_CHECK.note}`)
})

test("with zh-CN kirby's lines are in 简体中文", async ($, on) => {
  const { asked } = await skill($, on, { force: true, dialog: { ...WORDING, lang: 'zh-CN' } })
  expect(asked[0]?.startsWith([
    'o/r ★52770 · 2026-09-14 更新',
    '技能：s · commit aaaaaaa · 2 个文件',
    '3 个脚本，例如 run.sh、setup.py',
    '已存在：.claude/skills/s/（安装在 local 或 project 会替换它）',
    ...SKILL_CHECK.lines,
  ].join('\n') + '\n\n')).toBe(true)
})

test('with en, a missing lang or any other, it is English as before', async ($, on) => {
  const english = [
    'o/r ★52770 · pushed 2026-09-14',
    'skill: s · commit aaaaaaa · 2 files',
    'scripts: 3, e.g. run.sh, setup.py',
    'exists: .claude/skills/s/ (installing at local or project fails)',
    ...SKILL_CHECK.lines,
  ].join('\n') + '\n\n'
  const { asked, call } = skillTool($, on)
  for (const dialog of [{ ...WORDING, lang: 'en' }, WORDING, { ...WORDING, lang: 'ja' }]) {
    await call({ dialog })
    expect(asked.at(-1)?.startsWith(english)).toBe(true)
  }
  expect(asked.length).toBe(3)
})

test("the check tool's findings stay English", async ($, on) => {
  const { result } = await skill($, on, {}, 'mcp__kirby__check')
  expect((JSON.parse(result) as { findings: string[] }).findings).toEqual([
    'skill: s · commit aaaaaaa · 2 files', 'scripts: 3, e.g. run.sh, setup.py',
    'exists: .claude/skills/s/ (installing at local or project fails)', ...SKILL_CHECK.lines,
  ])
})

test('the install tool takes dialog.lang', async ($, on) => {
  const tools: { name: string; inputSchema: { properties: Record<string, { properties?: Record<string, unknown> }> } }[] = []
  on('tool.register', (_, e) => {
    tools.push(e as never)
    return { value: { tool: `mcp__kirby__${e.name}` } }
  })
  on('agent.register', (_, e) => ({ value: { agent: `kirby:${e.name}` } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const install = tools.find(t => t.name === 'install')
  expect(Object.keys(install?.inputSchema.properties.dialog?.properties ?? {}).sort()).toEqual(['about', 'lang', 'next', 'options', 'scope'])
  expect((install as { description?: string } | undefined)?.description).toContain('dialog.lang (en, zh-TW or zh-CN)')
})

// A plugin's or an MCP server's install or check tool, with the processes it runs answered by run (argv joined
// by spaces → stdout; undefined fails) and the dialogs answered in turn from answers; asked collects their questions.
async function tool($: Parameters<Parameters<typeof test>[1]>[0], on: Parameters<Parameters<typeof test>[1]>[1],
  input: Record<string, unknown>, run: (cmd: string) => string | undefined, answers: string[] = [], name = 'mcp__kirby__install') {
  const asked: string[] = []
  on('ui.log', () => ({ value: undefined }))
  on('env.get', () => ({ value: undefined }))
  on('process.run', (_, e) => {
    const cmd = e.argv.join(' ')
    const stdout = cmd.startsWith('gh api repos/o/r --jq') ? '[52770,"2026-09-14T08:00:00Z",false]' : run(cmd)
    return { value: { exitCode: stdout === undefined ? 1 : 0, stdout: stdout ?? '', stderr: stdout === undefined ? 'boom' : '',
      isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('tool.call', { tool: 'AskUserQuestion' }, (_, e) => {
    const q = (e as { questions: { question: string }[] }).questions[0]?.question ?? ''
    asked.push(q)
    return { result: { questions: (e as { questions: unknown[] }).questions, answers: { [q]: answers.shift() ?? '取消' } } } as never
  })
  const r = await $.tool.call({ tool: name, repo: 'o/r', ...input } as never)
  return { asked, result: String((r as { result?: unknown }).result) }
}

const NOT_LISTED = 'unchecked: whether this marketplace is already added (claude plugin marketplace list failed: boom); the check is ' +
  'of its repo as it stands, and the plugin is removed again if kirby cannot tell it installs from that commit'

test("with zh-TW a plugin's lines and the prompt-cache note are in 繁體中文; the model reads them in English", async ($, on) => {
  const check = JSON.stringify({ ...JSON.parse(PLUGIN_CHECK), mcp_servers: true })
  const { asked, result } = await tool($, on, { kind: 'plugin', plugin: 'p', dialog: { ...WORDING, lang: 'zh-TW' } },
    cmd => (cmd.includes('check_plugin.py') ? check : undefined), ['安裝', 'cancel'])
  expect(asked).toEqual([
    [
      'o/r ★52770 · 2026-09-14 更新',
      '外掛：p · marketplace mk · commit aaaaaaa · 1 個檔案',
      '未檢查：這個 marketplace 是否已加入（claude plugin marketplace list failed: boom）；檢查的是它的 repo 目前的狀態，若 kirby ' +
        '無法確認外掛是從那個 commit 安裝的，會再移除',
      'check: nothing found',
    ].join('\n') + `\n\n${WORDING.about}\n\n${WORDING.next}`,
    `${WORDING.scope}\n\nprompt cache：這個外掛帶有 MCP server；如果這個工作階段關閉了 tool search，用 /reload-plugins 載入它會重建一次 cache。`,
  ])
  expect(result).toBe(`not installed: the user cancelled at the scope step.\npattern scan: none\n${NOT_LISTED}`)
})

test("with zh-CN the prompt-cache note of a plugin whose source was not checked is in 简体中文", async ($, on) => {
  const check = JSON.stringify({ ...JSON.parse(PLUGIN_CHECK), mcp_servers: null })
  const { asked } = await tool($, on, { kind: 'plugin', plugin: 'p', dialog: { ...WORDING, lang: 'zh-CN' } },
    cmd => (cmd.includes('check_plugin.py') ? check : undefined), ['安裝', 'cancel'])
  expect(asked[1]).toBe(`${WORDING.scope}\n\nprompt cache：这个插件可能带有 MCP server（它的来源没有检查）；如果这个会话关闭了 tool search，` +
    '用 /reload-plugins 加载它会重建一次 cache。')
})

const MCP_FACTS = [
  { key: 'mcp_package', args: { package: 'probe@1.0.0', ecosystem: 'npm', file: 'package.json' } },
  { key: 'mcp_pinned', args: { name: 'probe', version: '1.0.0' } },
  'check: nothing found',
]
const MCP_CHECK = JSON.stringify({
  mcp_args: ['probe', '--', 'npx', '-y', 'probe@1.0.0'], facts: MCP_FACTS, lines: [
    "package: probe@1.0.0 (npm), named by this repo's package.json; not verified to come from this repo",
    'pinned: only probe, to 1.0.0; its dependencies are not pinned, so they may differ from those checked when the server starts',
    'check: nothing found',
  ], note: 'pattern scan: none', blocked: false, review: { needed: false, files: [] },
})
const MCP = { kind: 'mcp', mcp_args: ['probe', '--', 'npx', '-y', 'probe'] }

test("with zh-TW an MCP server's lines are in 繁體中文, with the command, package and version as they are", async ($, on) => {
  const { asked } = await tool($, on, { ...MCP, dialog: { ...WORDING, lang: 'zh-TW' } }, cmd => (cmd.includes('check_mcp.py') ? MCP_CHECK : undefined))
  expect(asked[0]).toBe([
    'o/r ★52770 · 2026-09-14 更新',
    'MCP server：claude mcp add --scope <scope> probe -- npx -y probe@1.0.0',
    '套件：probe@1.0.0（npm），由這個 repo 的 package.json 指名；沒有驗證它來自這個 repo',
    '已鎖定：只有 probe，鎖定在 1.0.0；它的相依套件沒有鎖定，server 啟動時可能和檢查過的不同',
    'check: nothing found',
  ].join('\n') + `\n\n${WORDING.about}\n\n${WORDING.next}`)
})

test("the check tool's plugin and MCP server findings stay English", async ($, on) => {
  const { result } = await tool($, on, MCP, cmd => (cmd.includes('check_mcp.py') ? MCP_CHECK : undefined), [], 'mcp__kirby__check')
  expect((JSON.parse(result) as { findings: string[] }).findings).toEqual([
    'MCP server: claude mcp add --scope <scope> probe -- npx -y probe@1.0.0', ...(JSON.parse(MCP_CHECK) as { lines: string[] }).lines,
  ])
})

test("a deny rule of the user's or the organization's still stops check and file", async ($, on) => {
  on('tool.check', () => ({ decision: 'deny', reason: 'denied by a rule' }))

  expect(await $.tool.check({ tool: 'mcp__kirby__file', input: {} })).toMatchObject({ decision: 'deny', reason: 'denied by a rule' })
})
