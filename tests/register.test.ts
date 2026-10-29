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

test("a deny rule of the user's or the organization's still stops check and file", async ($, on) => {
  on('tool.check', () => ({ decision: 'deny', reason: 'denied by a rule' }))

  expect(await $.tool.check({ tool: 'mcp__kirby__file', input: {} })).toMatchObject({ decision: 'deny', reason: 'denied by a rule' })
})
