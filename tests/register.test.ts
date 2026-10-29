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

const PLUGIN_CHECK = JSON.stringify({
  marketplace: 'mk', commit: 'aaaaaaa', sha: 'a'.repeat(40), lines: ['plugin: p · marketplace mk · commit aaaaaaa · 1 files', 'check: nothing found'],
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

test("a deny rule of the user's or the organization's still stops check and file", async ($, on) => {
  on('tool.check', () => ({ decision: 'deny', reason: 'denied by a rule' }))

  expect(await $.tool.check({ tool: 'mcp__kirby__file', input: {} })).toMatchObject({ decision: 'deny', reason: 'denied by a rule' })
})
