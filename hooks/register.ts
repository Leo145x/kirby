// The install step of inhale: one tool that asks the user what to do next and, to install,
// which scope, then runs the install. Searching and recommending stay in the skill's scripts.
// The dialogs show the facts the tool found and the model's wording in the user's language (see
// dialog.ts); what the tool answers is for the model, in English.

import type { EngineInterface, Register, RenderElement } from 'claude-code'

import { CANCEL, nextOptions, readDialog, SCOPES } from './dialog'
import type { Kind, Scope } from './dialog'
import { behind, findAdded, headOf, installPlugin } from './plugin'
import type { Added, Run } from './plugin'
import { callLine, resultLine } from './rows'

type $ = EngineInterface
type Input = Record<string, unknown>

const REPO_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/
const TIMEOUT_MS = 120_000

const TOOL = {
  name: 'install',
  description:
    'Install a recommended skill, plugin or MCP server. The user picks the next step in a dialog ' +
    '(install / read the README first / pick another / cancel) and, to install, the scope (local / project / user); ' +
    'the result says what they chose. kind=skill needs folder (from detect.py); kind=plugin needs plugin (the ' +
    "marketplace plugin's name; repo is the marketplace); kind=mcp needs mcp_args, everything that follows " +
    '`claude mcp add --scope <scope>`, e.g. ["github", "--", "npx", "-y", "@modelcontextprotocol/server-github"]. ' +
    'force replaces an existing skill folder of the same name. dialog is the wording of both dialogs in the ' +
    "user's language, in the format the inhale skill gives; without it they are in English.",
  inputSchema: {
    type: 'object',
    properties: {
      repo: { type: 'string' },
      kind: { type: 'string', enum: ['skill', 'plugin', 'mcp'] },
      folder: { type: 'string' },
      plugin: { type: 'string' },
      mcp_args: { type: 'array', items: { type: 'string' } },
      force: { type: 'boolean' },
      dialog: {
        type: 'object',
        properties: {
          about: { type: 'string' },
          next: { type: 'string' },
          options: { type: 'array', items: { type: 'string' } },
          scope: { type: 'string' },
        },
      },
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

function pluginCacheNote(sure: boolean, toolSearchOff: boolean): string {
  return (
    (sure ? 'prompt cache: this plugin brings an MCP server; ' : 'prompt cache: this plugin may bring an MCP server (its source was not checked); ') +
    (toolSearchOff
      ? 'ENABLE_TOOL_SEARCH=false is set, so loading it with /reload-plugins rebuilds the cache once.'
      : 'if tool search is off in this session, loading it with /reload-plugins rebuilds the cache once.')
  )
}

// The facts about what the install would do, the prompt-cache note for the scope dialog, the
// pre-install check as the model reads it in every result (so it can explain a finding), and for a
// skill or a plugin the commit shown, which is the one installed, and whether the malware lookup blocked
// it; for a plugin also its marketplace's name and, if the user already added it, where it is.
type Plan = { lines: string; cache: string; scan: string; commit?: string; blocked?: boolean; marketplace?: string; added?: Added | null }

const MCP_NOT_SCANNED = "scan: not scanned; the server runs what this command fetches when it starts, not this repo's files"

async function preview($: $, kind: Kind, input: Input): Promise<Plan> {
  const repo = String(input.repo)
  const scripts = `${$.plugin.root}/skills/inhale/scripts`
  if (kind === 'skill') {
    const folder = String(input.folder ?? '')
    if (!folder) throw new Refusal('kind=skill needs folder')
    const r = await run($, ['python3', '-I', `${scripts}/install_skill.py`, repo, folder, '--scope', 'project', '--check', '--json'])
    if (!r.ok) throw new Refusal(r.out)
    const c = JSON.parse(r.out) as {
      name: string; commit: string; sha: string; files: number; scripts: string[]; exists: boolean
      scan_lines: string[]; scan_note: string; lookup_lines: string[]; lookup_note: string; blocked: boolean
    }
    const lines = [`skill: ${c.name} · commit ${c.commit} · ${c.files} files`]
    if (c.scripts.length) lines.push(`scripts: ${c.scripts.length}, e.g. ${c.scripts.slice(0, 2).join(', ')}`)
    if (c.exists) {
      lines.push(`exists: .claude/skills/${c.name}/ (installing at local or project ${input.force === true ? 'replaces it' : 'fails'})`)
    }
    lines.push(...c.scan_lines, ...c.lookup_lines)
    return { lines: lines.join('\n'), cache: '', scan: `${c.scan_note}\n${c.lookup_note}`, commit: c.sha, blocked: c.blocked === true }
  }
  if (kind === 'plugin') {
    const name = String(input.plugin ?? '')
    if (!name) throw new Refusal('kind=plugin needs plugin')
    const runner: Run = argv => run($, argv)
    // A marketplace already added is left as it is: the check describes the commit it is at. Claude Code's
    // install would update one that is behind its repo, so that one is not installed from (plugin.ts).
    const added = await findAdded(runner, repo).catch((e: Error) => { throw new Refusal(e.message) })
    let head: string | null = null
    if (added) {
      head = await headOf(runner, added)
      if (!head) throw new Refusal(`could not read the commit of the marketplace ${added.name} in ${added.location}`)
      const latest = await run($, ['gh', 'api', `repos/${repo}/commits/${added.ref ?? 'HEAD'}`, '--jq', '.sha'])
      if (!latest.ok) throw new Refusal(`could not tell whether the marketplace ${added.name} is behind ${repo}: ${latest.out}`)
      const why = behind(repo, added, head, latest.out.trim())
      if (why) throw new Refusal(why)
    }
    const r = await run($, ['python3', '-I', `${scripts}/check_plugin.py`, '--agent', 'claude', ...(head ? ['--commit', head] : []), '--', repo, name])
    if (!r.ok) throw new Refusal(r.out)
    const c = JSON.parse(r.out) as {
      marketplace: string; commit: string; sha: string; lines: string[]; note: string; blocked: boolean; mcp_servers: boolean | null
    }
    // Tool search is off in more cases than this variable (an old model, a gateway, a HIPAA session), so
    // the note is conditional unless the variable settles it.
    const toolSearchOff = (await $.env.get('ENABLE_TOOL_SEARCH')) === 'false'
    const cache = c.mcp_servers === false ? '' : pluginCacheNote(c.mcp_servers === true, toolSearchOff)
    const about = added ? [`marketplace: already added as ${added.name}, at commit ${c.commit}; installs from it as it is, without updating it`] : []
    return {
      lines: [c.lines[0], ...about, ...c.lines.slice(1)].join('\n'), cache, scan: c.note, commit: c.sha,
      blocked: c.blocked === true, marketplace: added?.name ?? c.marketplace, added,
    }
  }
  const args = Array.isArray(input.mcp_args) ? input.mcp_args.filter((a): a is string => typeof a === 'string') : []
  if (args.length === 0) throw new Refusal('kind=mcp needs mcp_args')
  if (args.some(a => a === '--scope' || a === '-s' || a.startsWith('--scope='))) {
    throw new Refusal('mcp_args must not set the scope; the user picks it')
  }
  return { lines: `MCP server: claude mcp add --scope <scope> ${args.join(' ')}\n${MCP_NOT_SCANNED}`, cache: '', scan: MCP_NOT_SCANNED }
}

function command($: $, kind: Kind, input: Input, scope: Scope, plan: Plan): string[] {
  const repo = String(input.repo)
  if (kind === 'skill') {
    const argv = ['python3', '-I', `${$.plugin.root}/skills/inhale/scripts/install_skill.py`, repo, String(input.folder), '--scope', scope, '--commit', String(plan.commit)]
    return input.force === true ? [...argv, '--force'] : argv
  }
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

  const { dialog: d, problem } = readDialog(input.dialog)
  const [cancel, readme, other, go] = d.options
  // Tells the model why its wording was not used, so the next call can fix it.
  const note = problem ? `\nnote: the dialogs were in English because ${problem}; pass dialog as the inhale skill describes.` : ''

  let header: string
  let plan: Plan
  try {
    header = await repoHeader($, repo)
    plan = await preview($, kind, input)
  } catch (err) {
    if (err instanceof Refusal) return `not installed: ${err.message}${note}`
    throw err
  }

  // Every answer from here on also tells the model what the pre-install check showed the user.
  const tail = `\n${plan.scan}${note}`

  // Cancel comes first so a stray Enter already queued when the dialog opens cancels.
  const about = d.about ? `\n\n${d.about}` : ''
  const blocked = plan.blocked === true
  const next = await ask($, `${header}\n${plan.lines}${about}\n\n${d.next}`, nextOptions(d, blocked))
  $.ui.log(`install ${repo} (${kind}): next step ${JSON.stringify(next)}${problem ? ` (English: ${problem})` : ''}`, { to: 'debug' })
  if (next === readme) {
    return `not installed: the user wants to read the README first. Summarise it for them (gh api repos/${repo}/readme -H 'Accept: application/vnd.github.raw') and end your turn. Call this tool again only after they reply that they still want it.${tail}`
  }
  if (next === other) return `not installed: the user wants a different one. Ask which of the other recommendations to look at.${tail}`
  // A blocked install was not offered: typed text that matches the Install label does not install either.
  if (next !== go || blocked) {
    return `not installed: the user ${next === null ? 'dismissed the dialog' : next === cancel ? 'cancelled' : `answered ${JSON.stringify(next)}`}.${tail}`
  }

  const picked = await ask($, `${d.scope}${plan.cache ? `\n\n${plan.cache}` : ''}`, [CANCEL, ...SCOPES])
  $.ui.log(`install ${repo} (${kind}): scope ${JSON.stringify(picked)}`, { to: 'debug' })
  const scope = SCOPES.find(s => s === picked)
  if (!scope) return `not installed: the user ${picked === null ? 'dismissed the scope dialog' : 'cancelled at the scope step'}.${tail}`

  if (kind === 'plugin') {
    const p = await installPlugin(argv => run($, argv), {
      repo, plugin: String(input.plugin), scope, sha: String(plan.commit), marketplace: String(plan.marketplace), added: plan.added ?? null,
    })
    if (!p.ok) return `install failed (scope ${scope}): ${[...p.shown, p.out].filter(Boolean).join('\n')}${tail}`
    return `installed (scope ${scope}): ${p.shown.join('\n')}\n${p.out}\nnext: ${AFTER[kind]}${tail}`
  }
  const argv = command($, kind, input, scope, plan)
  const r = await run($, argv)
  const shown = argv.map(a => (a.includes(' ') ? JSON.stringify(a) : a)).join(' ')
  if (!r.ok) return `install failed (scope ${scope}): ${shown}\n${r.out}${tail}`
  return `installed (scope ${scope}): ${shown}\n${r.out}\nnext: ${AFTER[kind]}${tail}`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register(TOOL)
    return next(e)
  })

  on('tool.call', { tool: 'mcp__kirby__install' }, async ($, e: Input) => ({ result: await install($, e) }))

  // One short line each for the call and its result; expanded (ctrl+o) and errors draw as usual.
  // The terminal's own rows lead with these marks, so ours do too.
  on('ui.render', { component: 'ToolUse', props: { tool: 'mcp__kirby__install' } }, ($, e, next) => {
    if (e.props.isExpanded) return next(e)
    const { Text } = $.ui.resolve(e)
    const mark = e.surface === 'terminal' ? '● ' : ''
    return h(Text, null, mark + callLine(e.props.input)) as RenderElement
  })
  on('ui.render', { component: 'ToolResult', props: { tool: 'mcp__kirby__install' } }, ($, e, next) => {
    if (e.props.isExpanded || e.props.isErrored) return next(e)
    const { Text } = $.ui.resolve(e)
    const mark = e.surface === 'terminal' ? '  ⎿  ' : ''
    return h(Text, { dimColor: true }, mark + resultLine(e.props.output)) as RenderElement
  })
}
