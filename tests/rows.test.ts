import { expect, test } from 'claude-code/testing'

import { callLine, resultLine } from '../hooks/rows'

const SCAN = 'pattern scan: the dialog showed the user no pattern-scan findings in the npm package x@1.0.0 (x-1.0.0.tgz) (a pattern match, not a safety review)'

test('the call line names the repo and what is installed, not the dialog wording', async () => {
  const dialog = { about: '安裝 security-audit skill', next: '下一步？', options: ['取消', '先讀', '換一個', '安裝'], scope: '範圍？' }
  expect(callLine({ repo: 'cloudflare/security-audit-skill', kind: 'skill', folder: 'skills/security-audit', dialog }))
    .toBe('kirby install cloudflare/security-audit-skill (skill security-audit)')
  expect(callLine({ repo: 'anthropics/claude-plugins-official', kind: 'plugin', plugin: 'agent-sdk-dev' }))
    .toBe('kirby install anthropics/claude-plugins-official (plugin agent-sdk-dev)')
  expect(callLine({ repo: 'modelcontextprotocol/servers', kind: 'mcp', mcp_args: ['kirby-e2e', '--', 'npx'] }))
    .toBe('kirby install modelcontextprotocol/servers (mcp kirby-e2e)')
  expect(callLine({ repo: 'a/b' })).toBe('kirby install a/b')
  expect(callLine(undefined)).toBe('kirby install ')
})

test('an installed skill shows the scope and where it went', async () => {
  const text = [
    'installed (scope user): python3 -I /k/skills/inhale/scripts/install_skill.py cloudflare/security-audit-skill skills/security-audit --scope user --commit c1c8a8c1471069fb0e188eeaff69b8e8db6564a8',
    'installed cloudflare/security-audit-skill:skills/security-audit@c1c8a8c -> /home/u/.claude/skills/security-audit (20 files)',
    '  top level: SKILL.md',
    'next: If it does not show up in the / menu, the user starts a new session.',
  ].join('\n')
  expect(resultLine(text)).toBe('installed (scope user) -> /home/u/.claude/skills/security-audit (20 files)')
  // However the engine stores the result.
  expect(resultLine([{ type: 'text', text }])).toBe(resultLine(text))
  expect(resultLine({ content: [{ type: 'text', text }] })).toBe(resultLine(text))
})

test('other results keep their first clause', async () => {
  expect(resultLine(`installed (scope local): claude mcp add --scope local kirby-e2e -- npx\nAdded stdio MCP server\n${SCAN}`))
    .toBe('installed (scope local)')
  expect(resultLine(`install failed (scope local): python3 -I x.py\n.claude/skills/x already exists; pass --force to replace it\n${SCAN}`))
    .toBe('install failed (scope local)')
  expect(resultLine(`not installed: the user cancelled at the scope step.\n${SCAN}`))
    .toBe('not installed: the user cancelled at the scope step.')
  expect(resultLine("not installed: the user wants to read the README first. Summarise it for them (gh api repos/a/b.js/readme) and end your turn.\npattern scan: x"))
    .toBe('not installed: the user wants to read the README first.')
  expect(resultLine('not installed: a/b has no marketplace plugin named x')).toBe('not installed: a/b has no marketplace plugin named x')
  expect(resultLine(undefined)).toBe('')
})
