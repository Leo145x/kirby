// A plugin installs the commit the dialog showed (docs/adr/0003). Claude Code's `marketplace add` takes no
// commit, so kirby adds the marketplace as usual, reads the HEAD of the clone Claude Code made, and removes
// the marketplace again if it is not the commit checked. A marketplace the user already added is left as it
// is: the check describes the commit it is at, and kirby installs from it only while it is still there.
// Claude Code's `plugin install` updates a marketplace that is behind its repo (tried with 2.1.312), so the
// HEAD is read again after the install too. `run` is passed in, so the tests can stand in for the CLI.

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

// Why kirby will not install from a marketplace already added whose repo has moved on (latest), or null.
export function behind(repo: string, added: Added, head: string, latest: string): string | null {
  if (head === latest) return null
  return (
    `the marketplace ${added.name} is already added, at commit ${short(head)}, but ${repo} is now at ${short(latest)}. ` +
    'Claude Code updates a marketplace when it installs from it, so the plugin would come from a commit nobody checked, ' +
    `and kirby leaves the marketplace as it is. The user can update it with \`claude plugin marketplace update ${added.name}\` ` +
    'and then ask again.'
  )
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
  const moved = `the marketplace ${name} has moved on`
  // Only a marketplace kirby added itself is removed again.
  const removal = async () => !p.added && (await claude('plugin', 'marketplace', 'remove', name))

  const head = added ? await headOf(run, added) : null
  if (head !== p.sha) {
    const removed = await removal()
    return done(false, `${moved}: it is now at commit ${head ? short(head) : 'unknown'}, not ${short(p.sha)} as shown to the ` +
      `user; nothing installed${removed ? ', and the marketplace was removed again' : ''}`)
  }
  const id = `${p.plugin}@${name}`
  if (!(await claude('plugin', 'install', id, '--scope', p.scope))) return done(false)
  const after = await headOf(run, added!)
  if (after !== p.sha) {
    await claude('plugin', 'uninstall', id, '--scope', p.scope)
    const removed = await removal()
    return done(false, `${moved}: Claude Code updated it to commit ${after ? short(after) : 'unknown'} while installing, not ` +
      `${short(p.sha)} as shown to the user; the plugin was uninstalled again${removed ? ', and the marketplace removed' : ''}`)
  }
  return done(true)
}
