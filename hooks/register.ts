// The install step of inhale: one tool that asks the user what to do next and, to install,
// which scope, then runs the install. Searching and recommending stay in the skill's scripts.
// The dialogs speak the user's language; what the tool answers is for the model, in English.

import type { EngineInterface, Register } from 'claude-code'

import { pickLang, TEXT } from './i18n'
import type { Kind, Scope } from './i18n'

type $ = EngineInterface
type Input = Record<string, unknown>
type Text = (typeof TEXT)['en']

const REPO_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/
const SCOPES: readonly Scope[] = ['local', 'project', 'user']
const TIMEOUT_MS = 120_000

const TOOL = {
  name: 'install',
  description:
    'Install a recommended skill, plugin or MCP server. The user picks the next step in a dialog ' +
    '(install / read the README first / pick another / cancel) and, to install, the scope (local / project / user); ' +
    'the result says what they chose. kind=skill needs folder (from detect.py); kind=plugin needs plugin (the ' +
    "marketplace plugin's name; repo is the marketplace); kind=mcp needs mcp_args, everything that follows " +
    '`claude mcp add --scope <scope>`, e.g. ["github", "--", "npx", "-y", "@modelcontextprotocol/server-github"]. ' +
    'force replaces an existing skill folder of the same name.',
  inputSchema: {
    type: 'object',
    properties: {
      repo: { type: 'string' },
      kind: { type: 'string', enum: ['skill', 'plugin', 'mcp'] },
      folder: { type: 'string' },
      plugin: { type: 'string' },
      mcp_args: { type: 'array', items: { type: 'string' } },
      force: { type: 'boolean' },
    },
    required: ['repo', 'kind'],
  },
} as const

const AFTER: Record<Kind, string> = {
  skill: 'If it does not show up in the / menu, the user starts a new session.',
  plugin: 'The user runs /reload-plugins to load it. The marketplace itself is recorded in their user settings.',
  mcp: 'The server connects in the next session; tell the user to restart Claude Code to use it.',
}

class Refusal extends Error {}

async function run($: $, argv: readonly string[]) {
  const r = await $.process.run(argv, { timeoutMs: TIMEOUT_MS })
  return { ok: r.exitCode === 0, out: [r.stdout.trim(), r.stderr.trim()].filter(Boolean).join('\n') }
}

async function repoHeader($: $, repo: string): Promise<string> {
  const r = await run($, ['gh', 'api', `repos/${repo}`, '--jq', '[.stargazers_count, .pushed_at, .archived] | @json'])
  if (!r.ok) throw new Refusal(`gh api repos/${repo} failed: ${r.out}`)
  const [stars, pushed, archived] = JSON.parse(r.out) as [number, string | null, boolean]
  return `${repo} ★${stars} · pushed ${(pushed ?? '?').slice(0, 10)}${archived ? ' · ARCHIVED' : ''}`
}

// What the install would do, and the prompt-cache note for the scope dialog.
async function preview($: $, t: Text, kind: Kind, input: Input): Promise<{ lines: string; cache: string }> {
  const repo = String(input.repo)
  const scripts = `${$.plugin.root}/skills/inhale/scripts`
  if (kind === 'skill') {
    const folder = String(input.folder ?? '')
    if (!folder) throw new Refusal('kind=skill needs folder')
    const r = await run($, ['python3', '-I', `${scripts}/install_skill.py`, repo, folder, '--scope', 'project', '--check', '--json'])
    if (!r.ok) throw new Refusal(r.out)
    const c = JSON.parse(r.out) as { name: string; commit: string; files: number; scripts: string[]; exists: boolean }
    const lines = [t.kind(`skill (${c.name})`), t.commit(c.commit), t.files(c.files)]
    if (c.scripts.length) lines.push(t.scripts(c.scripts.length, c.scripts.slice(0, 2).join(', ')))
    if (c.exists) lines.push(t.exists(c.name, input.force === true))
    return { lines: lines.join('\n'), cache: '' }
  }
  if (kind === 'plugin') {
    const name = String(input.plugin ?? '')
    if (!name) throw new Refusal('kind=plugin needs plugin')
    const r = await run($, ['python3', '-I', `${scripts}/detect.py`, repo])
    if (!r.ok) throw new Refusal(r.out)
    const units = (JSON.parse(r.out) as { install?: { type: string; name?: string; description?: string; mcpServers?: boolean | null }[] }[])[0]?.install ?? []
    const unit = units.find(u => u.type === 'plugin' && u.name === name)
    if (!unit) throw new Refusal(`${repo} has no marketplace plugin named ${name}`)
    // Tool search is off in more cases than this variable (an old model, a gateway, a HIPAA session), so
    // the note is conditional unless the variable settles it.
    const toolSearchOff = (await $.env.get('ENABLE_TOOL_SEARCH')) === 'false'
    const cache = unit.mcpServers === false ? '' : t.pluginMcp(unit.mcpServers === true, toolSearchOff)
    const lines = [t.kind(`plugin (${name})`)]
    if (unit.description) lines.push(t.about(unit.description.slice(0, 160)))
    return { lines: lines.join('\n'), cache }
  }
  const args = Array.isArray(input.mcp_args) ? input.mcp_args.filter((a): a is string => typeof a === 'string') : []
  if (args.length === 0) throw new Refusal('kind=mcp needs mcp_args')
  if (args.some(a => a === '--scope' || a === '-s' || a.startsWith('--scope='))) {
    throw new Refusal('mcp_args must not set the scope; the user picks it')
  }
  return {
    lines: [t.kind('MCP server'), t.command(`claude mcp add --scope <scope> ${args.join(' ')}`)].join('\n'),
    cache: t.mcpNote,
  }
}

function command($: $, kind: Kind, input: Input, scope: Scope): string[] {
  const repo = String(input.repo)
  if (kind === 'skill') {
    const argv = ['python3', '-I', `${$.plugin.root}/skills/inhale/scripts/install_skill.py`, repo, String(input.folder), '--scope', scope]
    return input.force === true ? [...argv, '--force'] : argv
  }
  if (kind === 'plugin') return ['claude', 'plugin', 'install', String(input.plugin), '--marketplace', repo, '--scope', scope]
  return ['claude', 'mcp', 'add', '--scope', scope, ...(input.mcp_args as string[])]
}

async function ask($: $, question: string, options: readonly string[]): Promise<string | null> {
  return $.ui.ask(question, { options, header: 'kirby' }).catch(() => null)
}

async function install($: $, input: Input): Promise<string> {
  const repo = String(input.repo ?? '')
  const kind = (['skill', 'plugin', 'mcp'] as const).find(k => k === input.kind)
  if (!REPO_RE.test(repo)) return `not installed: not an owner/repo: ${JSON.stringify(input.repo)}`
  if (!kind) return `not installed: kind must be skill, plugin or mcp`

  const lang = pickLang(await $.settings.read({ key: 'language' }), (await $.env.get('LC_ALL')) || (await $.env.get('LANG')))
  const t = TEXT[lang]
  const o = t.options

  let header: string
  let plan: { lines: string; cache: string }
  try {
    header = await repoHeader($, repo)
    plan = await preview($, t, kind, input)
  } catch (err) {
    if (err instanceof Refusal) return `not installed: ${err.message}`
    throw err
  }

  // Cancel comes first so a stray Enter already queued when the dialog opens cancels.
  const next = await ask($, `${header}\n\n${plan.lines}\n\n${t.next}`, [o.cancel, o.readme, o.other, o.install])
  $.ui.log(`install ${repo} (${kind}, ${lang}): next step ${JSON.stringify(next)}`, { to: 'debug' })
  if (next === o.readme) {
    return `not installed: the user wants to read the README first. Summarise it (gh api repos/${repo}/readme -H 'Accept: application/vnd.github.raw'), then call this tool again if they still want it.`
  }
  if (next === o.other) return 'not installed: the user wants a different one. Ask which of the other recommendations to look at.'
  if (next !== o.install) {
    return `not installed: the user ${next === null ? 'dismissed the dialog' : next === o.cancel ? 'cancelled' : `answered ${JSON.stringify(next)}`}.`
  }

  const where = SCOPES.map(s => `${s.padEnd(8)}${t.where[kind][s]}`).join('\n')
  const picked = await ask($, `${t.scope}\n\n${where}${plan.cache ? `\n\n${plan.cache}` : ''}`, [o.cancel, ...SCOPES])
  $.ui.log(`install ${repo} (${kind}): scope ${JSON.stringify(picked)}`, { to: 'debug' })
  const scope = SCOPES.find(s => s === picked)
  if (!scope) return `not installed: the user ${picked === null ? 'dismissed the scope dialog' : 'cancelled at the scope step'}.`

  const argv = command($, kind, input, scope)
  const r = await run($, argv)
  const shown = argv.map(a => (a.includes(' ') ? JSON.stringify(a) : a)).join(' ')
  if (!r.ok) return `install failed (scope ${scope}): ${shown}\n${r.out}`
  return `installed (scope ${scope}): ${shown}\n${r.out}\nnext: ${AFTER[kind]}`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register(TOOL)
    return next(e)
  })

  on('tool.call', { tool: 'mcp__kirby__install' }, async ($, e: Input) => ({ result: await install($, e) }))
}
