// A plugin installs the commit the dialog showed (docs/adr/0003). Claude Code's `marketplace add` takes no
// commit, so kirby adds the marketplace as usual, installs, then reads the HEAD of the marketplace's clone
// and removes the plugin again if it is not the commit checked. Claude Code's `plugin install` refreshes a
// marketplace that is behind its repo (seen with 2.1.312), so for one the user already added, the check is
// of what the install will bring, and the dialog says so (docs/adr/0005). `run` is passed in, so the tests
// can stand in for the CLI.

import type { Scope } from './dialog'

export type Run = (argv: readonly string[]) => Promise<{ ok: boolean; out: string }>
// A marketplace Claude Code already has, as `claude plugin marketplace list --json` gives it.
export type Added = { name: string; location: string; ref?: string }

const GITHUB_URL = /^(?:https:\/\/github\.com\/|git@github\.com:|ssh:\/\/git@github\.com\/)([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+?)(?:\.git)?\/?$/i
const SHA_RE = /^[0-9a-f]{40}$/

const short = (sha: string) => sha.slice(0, 7)

// The marketplace added from this GitHub repo, from the output of `claude plugin marketplace list --json`.
export function addedMarketplace(listJson: string, repo: string): Added | null {
  let listed: unknown
  try {
    listed = JSON.parse(listJson)
  } catch {
    return null
  }
  for (const m of Array.isArray(listed) ? listed : []) {
    if (!m || typeof m !== 'object') continue
    const { name, source, repo: from, url, ref, installLocation } = m as Record<string, unknown>
    const named = source === 'github' && typeof from === 'string' ? from
      : source === 'git' && typeof url === 'string' ? (url.match(GITHUB_URL)?.[1] ?? '') : ''
    if (named.toLowerCase() === repo.toLowerCase() && typeof name === 'string' && typeof installLocation === 'string') {
      return { name, location: installLocation, ref: typeof ref === 'string' ? ref : undefined }
    }
  }
  return null
}

export async function findAdded(run: Run, repo: string): Promise<Added | null> {
  const r = await run(['claude', 'plugin', 'marketplace', 'list', '--json'])
  if (!r.ok) throw new Error(`claude plugin marketplace list failed: ${r.out}`)
  return addedMarketplace(r.out, repo)
}

// The commit a marketplace's clone is at, or null if it cannot be read.
export async function headOf(run: Run, added: Added): Promise<string | null> {
  const r = await run(['git', '-C', added.location, 'rev-parse', 'HEAD'])
  return r.ok && SHA_RE.test(r.out.trim()) ? r.out.trim() : null
}

// For a marketplace already added: the commit to check (null: the repo's default branch as it stands) and
// the dialog's line about it. latest is the repo's commit now, or why it could not be read.
export function alreadyAdded(added: Added, head: string | null, latest: { sha: string } | { why: string }):
  { commit: string | null; line: string } {
  const at = head ? `at commit ${short(head)}` : 'at a commit kirby could not read'
  if ('why' in latest) {
    return {
      commit: head,
      line: `unchecked: whether the marketplace ${added.name}, ${at}, is behind its repo (${latest.why}); if it is, installing ` +
        'refreshes it, and the plugin is removed again if it then comes from another commit',
    }
  }
  if (head === latest.sha) return { commit: head, line: `marketplace: already added as ${added.name}, ${at}; installs from it as it is` }
  return {
    commit: latest.sha,
    line: `marketplace: already added as ${added.name}, ${at}, behind its repo; installing refreshes it to ${short(latest.sha)}, the commit checked`,
  }
}

type Plan = { repo: string; plugin: string; scope: Scope; sha: string; marketplace: string; added: Added | null }

// The commands run, in order, and their output; ok is false when nothing stays installed.
export async function installPlugin(run: Run, p: Plan): Promise<{ ok: boolean; shown: string[]; out: string }> {
  const shown: string[] = []
  const outs: string[] = []
  const claude = async (...args: string[]) => {
    shown.push(['claude', ...args].join(' '))
    const r = await run(['claude', ...args])
    if (r.out) outs.push(r.out)
    return r.ok
  }
  const done = (ok: boolean, why?: string) => ({ ok, shown, out: [...outs, ...(why ? [why] : [])].join('\n') })

  if (!p.added && !(await claude('plugin', 'marketplace', 'add', p.repo))) return done(false)
  const added = p.added ?? (await findAdded(run, p.repo).catch(() => null))
  const name = added?.name ?? p.marketplace
  const id = `${p.plugin}@${name}`
  if (!(await claude('plugin', 'install', id, '--scope', p.scope))) return done(false)
  const head = added ? await headOf(run, added) : null
  if (head !== p.sha) {
    await claude('plugin', 'uninstall', id, '--scope', p.scope)
    return done(false, `the marketplace ${name} has moved on: it is at commit ${head ? short(head) : 'unknown'} after the install, ` +
      `not ${short(p.sha)} as shown to the user; the plugin was removed again`)
  }
  return done(true)
}
