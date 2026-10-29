// The install step of inhale: one tool that asks the user what to do next and, to install,
// which scope, then runs the install. Searching and recommending stay in the skill's scripts.
// The dialogs show the facts the tool found and the model's wording in the user's language (see
// dialog.ts); what the tool answers is for the model, in English. Beside it, two read-only tools for
// the model review (docs/adr/0002, check.ts): `check` runs install's pre-install check without a
// dialog, and `file` reads one file where the check read it; kirby allows those two without a prompt, and
// the reviewer agent kirby:reviewer can use only them. install takes the review's result and decides from
// its own check whether one was needed.

import type { EngineInterface, Register, RenderElement } from 'claude-code'

import { checkResult, fileRequest, fileText, READ_ONLY_TOOLS, REPO_RE, REVIEWER, SHA_RE } from './check'
import type { ReviewOf } from './check'
import { CANCEL, nextOptions, readDialog, readReview, reviewNote, SCOPES } from './dialog'
import type { Kind, Scope } from './dialog'
import { alreadyAdded, findAdded, headOf, installPlugin, notListed } from './plugin'
import type { Added, Run } from './plugin'
import { callLine, resultLine } from './rows'

type $ = EngineInterface
type Input = Record<string, unknown>

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
    "user's language, in the format the inhale skill gives; without it they are in English. When the check tool " +
    "said a review is needed, pass the model review's result as review and the check's read.ref as sha.",
  inputSchema: {
    type: 'object',
    properties: {
      repo: { type: 'string' },
      kind: { type: 'string', enum: ['skill', 'plugin', 'mcp'] },
      folder: { type: 'string' },
      plugin: { type: 'string' },
      mcp_args: { type: 'array', items: { type: 'string' } },
      force: { type: 'boolean' },
      sha: { type: 'string' },
      review: {
        type: 'object',
        properties: {
          findings: {
            type: 'array',
            items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, reason: { type: 'string' } } },
          },
          could_not_run: { type: 'string' },
        },
      },
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

const CHECK = {
  name: 'check',
  description:
    'Run the pre-install check of what install would install, read-only and without a dialog, as JSON: review ' +
    '(needed, not needed, or not possible), read (what to pass the file tool, with each path) and files (the files ' +
    "the check covered) when a review is needed, findings (the dialog's facts) and blocked. Takes the same repo, kind " +
    'and folder, plugin or mcp_args as install. When review is needed, the inhale skill says how to have the files reviewed.',
  inputSchema: {
    type: 'object',
    properties: {
      repo: { type: 'string' },
      kind: { type: 'string', enum: ['skill', 'plugin', 'mcp'] },
      folder: { type: 'string' },
      plugin: { type: 'string' },
      mcp_args: { type: 'array', items: { type: 'string' } },
    },
    required: ['repo', 'kind'],
  },
} as const

const FILE = {
  name: 'file',
  description:
    'One file at the commit or package the pre-install check covered, raw and read-only: for reading a hit the scan ' +
    'reported, or for the model review. For a repo, pass repo and ref, the full commit sha. For an MCP server\'s ' +
    "package, pass package and ref as the check tool's read gives them (ref is the sha256 of the archive checked) " +
    'and path inside the package.',
  inputSchema: {
    type: 'object',
    properties: {
      repo: { type: 'string' },
      path: { type: 'string' },
      ref: { type: 'string' },
      package: {
        type: 'object',
        properties: { ecosystem: { type: 'string', enum: ['npm', 'PyPI'] }, name: { type: 'string' }, version: { type: 'string' } },
      },
    },
    required: ['path', 'ref'],
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
// pre-install check as the model reads it in every result (so it can explain a finding), and whether
// the malware lookup blocked it; for a skill or a plugin the commit shown, which is the one installed;
// for a plugin also its marketplace's name and, if the user already added it, where it is; for an MCP
// server the command to run, with the package checked pinned to the version checked; and what the model
// review reads and whether it is needed, the check's own.
type Plan = {
  lines: string; cache: string; scan: string; review: ReviewOf; commit?: string; blocked?: boolean; marketplace?: string
  added?: Added | null; mcpArgs?: string[]
}

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
      check_lines: string[]; scan_note: string; lookup_note: string; blocked: boolean; review: ReviewOf
    }
    const lines = [`skill: ${c.name} · commit ${c.commit} · ${c.files} files`]
    if (c.scripts.length) lines.push(`scripts: ${c.scripts.length}, e.g. ${c.scripts.slice(0, 2).join(', ')}`)
    if (c.exists) {
      lines.push(`exists: .claude/skills/${c.name}/ (installing at local or project ${input.force === true ? 'replaces it' : 'fails'})`)
    }
    lines.push(...c.check_lines)
    return {
      lines: lines.join('\n'), cache: '', scan: `${c.scan_note}\n${c.lookup_note}`, review: c.review, commit: c.sha, blocked: c.blocked === true,
    }
  }
  if (kind === 'plugin') {
    const name = String(input.plugin ?? '')
    if (!name) throw new Refusal('kind=plugin needs plugin')
    const runner: Run = argv => run($, argv)
    // For a marketplace already added, the check is of what the install will bring: Claude Code's install
    // refreshes one that is behind its repo (plugin.ts).
    let about: string[] = []
    const added = await findAdded(runner, repo).catch((e: Error) => {
      about = [notListed(e.message)]
      return null
    })
    let commit: string | null = null
    if (added) {
      const head = await headOf(runner, added)
      const r = await run($, ['gh', 'api', `repos/${repo}/commits/${added.ref ?? 'HEAD'}`, '--jq', '.sha'])
      const latest = r.ok && SHA_RE.test(r.out.trim()) ? { sha: r.out.trim() } : { why: `gh api: ${r.out.split('\n')[0] || 'no answer'}` }
      const a = alreadyAdded(added, head, latest)
      commit = a.commit
      about = [a.line]
    }
    const r = await run($, ['python3', '-I', `${scripts}/check_plugin.py`, '--agent', 'claude', ...(commit ? ['--commit', commit] : []), '--', repo, name])
    if (!r.ok) throw new Refusal(r.out)
    const c = JSON.parse(r.out) as {
      marketplace: string; commit: string; sha: string; lines: string[]; note: string; blocked: boolean; mcp_servers: boolean | null
      review: ReviewOf
    }
    // Tool search is off in more cases than this variable (an old model, a gateway, a HIPAA session), so
    // the note is conditional unless the variable settles it.
    const toolSearchOff = (await $.env.get('ENABLE_TOOL_SEARCH')) === 'false'
    const cache = c.mcp_servers === false ? '' : pluginCacheNote(c.mcp_servers === true, toolSearchOff)
    return {
      lines: [c.lines[0], ...about, ...c.lines.slice(1)].join('\n'), cache, scan: [c.note, ...about].join('\n'), review: c.review,
      commit: c.sha, blocked: c.blocked === true, marketplace: added?.name ?? c.marketplace, added,
    }
  }
  const args = Array.isArray(input.mcp_args) ? input.mcp_args.filter((a): a is string => typeof a === 'string') : []
  if (args.length === 0) throw new Refusal('kind=mcp needs mcp_args')
  if (args.some(a => a === '--scope' || a === '-s' || a.startsWith('--scope='))) {
    throw new Refusal('mcp_args must not set the scope; the user picks it')
  }
  // The check gives back the command with the package it checked pinned to the version checked.
  const r = await run($, ['python3', '-I', `${scripts}/check_mcp.py`, '--', repo, JSON.stringify(args)])
  if (!r.ok) throw new Refusal(r.out)
  const c = JSON.parse(r.out) as { mcp_args: string[]; lines: string[]; note: string; blocked: boolean; review: ReviewOf }
  return {
    lines: [`MCP server: claude mcp add --scope <scope> ${c.mcp_args.join(' ')}`, ...c.lines].join('\n'), cache: '', scan: c.note,
    review: c.review, blocked: c.blocked === true, mcpArgs: c.mcp_args,
  }
}

function command($: $, kind: Kind, input: Input, scope: Scope, plan: Plan): string[] {
  const repo = String(input.repo)
  if (kind === 'skill') {
    const argv = ['python3', '-I', `${$.plugin.root}/skills/inhale/scripts/install_skill.py`, repo, String(input.folder), '--scope', scope, '--commit', String(plan.commit)]
    return input.force === true ? [...argv, '--force'] : argv
  }
  return ['claude', 'mcp', 'add', '--scope', scope, ...(plan.mcpArgs ?? [])]
}

async function ask($: $, question: string, options: readonly string[]): Promise<string | null> {
  return $.ui.ask(question, { options, header: 'kirby' }).catch(() => null)
}

// The repo and the kind asked for, or why not.
function target(input: Input): { repo: string; kind: Kind } | { problem: string } {
  const repo = String(input.repo ?? '')
  const kind = (['skill', 'plugin', 'mcp'] as const).find(k => k === input.kind)
  if (!REPO_RE.test(repo)) return { problem: `not an owner/repo: ${JSON.stringify(input.repo)}` }
  if (!kind) return { problem: 'kind must be skill, plugin or mcp' }
  return { repo, kind }
}

// install's pre-install check without a dialog, for the model review (docs/adr/0002).
async function check($: $, input: Input): Promise<string> {
  const t = target(input)
  if ('problem' in t) return `not checked: ${t.problem}`
  try {
    const plan = await preview($, t.kind, input)
    return checkResult(plan.lines.split('\n'), plan.review, plan.blocked === true)
  } catch (err) {
    if (err instanceof Refusal) return `not checked: ${err.message}`
    throw err
  }
}

async function file($: $, input: Input): Promise<string> {
  const req = fileRequest(input, `${$.plugin.root}/skills/inhale/scripts`)
  if ('problem' in req) return req.problem
  const r = await run($, req.argv)
  return r.ok ? fileText(r.out) : r.out || 'no output'
}

async function install($: $, input: Input): Promise<string> {
  const t = target(input)
  if ('problem' in t) return `not installed: ${t.problem}`
  const { repo, kind } = t

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
  // Whether a review was needed is the check's own finding, not the model's (docs/adr/0002).
  const reviewed = readReview(input.review, input.sha, plan.review)
  if (reviewed.problem) return `not installed: ${reviewed.problem}; call this tool again with review as the inhale skill describes.${note}`
  const reviewText = reviewNote(reviewed.lines)

  // Every answer from here on also tells the model what the pre-install check showed the user.
  const tail = `\n${plan.scan}${reviewText ? `\n${reviewText}` : ''}${note}`

  // Cancel comes first so a stray Enter already queued when the dialog opens cancels.
  const about = d.about ? `\n\n${d.about}` : ''
  const blocked = plan.blocked === true
  const facts = [plan.lines, ...reviewed.lines].join('\n')
  const next = await ask($, `${header}\n${facts}${about}\n\n${d.next}`, nextOptions(d, blocked))
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
    await Promise.all([TOOL, CHECK, FILE].map(t => $.tool.register(t)))
    // Without the reviewer the skill passes could_not_run, and the dialog says the review is unchecked.
    await $.agent.register(REVIEWER).catch(err => $.ui.log(`kirby:reviewer not registered: ${String(err)}`, { to: 'debug' }))
    return next(e)
  })

  // check and file only read GitHub and package contents, so the review never stops at a permission prompt
  // (docs/adr/0002). Nothing else is allowed, and a deny rule of the user's or the organization's still stands.
  for (const tool of READ_ONLY_TOOLS) {
    on('tool.check', { tool }, async ($, e, next) => {
      const below = await next(e)
      return below.decision === 'deny' ? below : { decision: 'allow', reason: 'kirby allows its own read-only check and file tools' }
    })
  }

  on('tool.call', { tool: 'mcp__kirby__install' }, async ($, e: Input) => ({ result: await install($, e) }))
  on('tool.call', { tool: 'mcp__kirby__check' }, async ($, e: Input) => ({ result: await check($, e) }))
  on('tool.call', { tool: 'mcp__kirby__file' }, async ($, e: Input) => ({ result: await file($, e) }))

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
