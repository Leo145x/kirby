import { expect, test } from 'claude-code/testing'

import { addedMarketplace, alreadyAdded, headOf, installPlugin } from '../hooks/plugin'
import type { Run } from '../hooks/plugin'

const SHA = 'a'.repeat(40)
const NEW = 'b'.repeat(40)
const LOC = '/home/u/.claude/plugins/marketplaces/mk'
const LISTED = JSON.stringify([
  { name: 'other', source: 'github', repo: 'o/other', installLocation: '/x/other' },
  { name: 'mk', source: 'github', repo: 'O/MK', installLocation: LOC },
])
const ADDED = { name: 'mk', location: LOC }

// Claude Code's CLI and git as the install sees them: heads are what `git rev-parse HEAD` gives, call by call;
// snapshot is the `.gcs-sha` of a marketplace that is not a git clone.
function fake(heads: string[], snapshot?: string) {
  const ran: string[][] = []
  const run: Run = async argv => {
    ran.push([...argv])
    if (argv[0] === 'git') {
      const head = heads.shift()
      return head === undefined ? { ok: false, out: 'fatal: not a git repository' } : { ok: true, out: head }
    }
    if (argv[0] === 'python3') {
      return snapshot !== undefined && argv.at(-1) === `${LOC}/.gcs-sha` ? { ok: true, out: snapshot } : { ok: false, out: 'No such file' }
    }
    if (argv.join(' ') === 'claude plugin marketplace list --json') return { ok: true, out: LISTED }
    return { ok: true, out: `ran ${argv[2]}` }
  }
  return { run, claude: () => ran.filter(a => a[0] === 'claude' && a[3] !== 'list').map(a => a.join(' ')) }
}

const plan = { repo: 'o/mk', plugin: 'p', scope: 'local' as const, sha: SHA, marketplace: 'mk' }

test('the marketplace already added from a repo is found by its source, whatever the case', async () => {
  expect(addedMarketplace(LISTED, 'o/mk')).toEqual({ name: 'mk', location: LOC, ref: undefined })
  const git = JSON.stringify([{ name: 'g', source: 'git', url: 'git@github.com:o/mk.git', ref: 'v1', installLocation: '/g' }])
  expect(addedMarketplace(git, 'o/mk')).toEqual({ name: 'g', location: '/g', ref: 'v1' })
  expect(addedMarketplace(LISTED, 'o/nope')).toBe(null)
  expect(addedMarketplace('[{"name": "d", "source": "directory", "path": "/o/mk"}]', 'o/mk')).toBe(null)
  expect(addedMarketplace('not json', 'o/mk')).toBe(null)
})

test('a marketplace already added is checked at what the install will bring, and the dialog says so', async () => {
  expect(alreadyAdded(ADDED, SHA, { sha: SHA })).toEqual({
    commit: SHA, line: 'marketplace: already added as mk, at commit aaaaaaa; installs from it as it is',
  })
  // Claude Code's install refreshes a marketplace that is behind its repo, so the repo's commit is the one checked.
  expect(alreadyAdded(ADDED, SHA, { sha: NEW })).toEqual({
    commit: NEW, line: 'marketplace: already added as mk, at commit aaaaaaa, behind its repo; installing refreshes it to bbbbbbb, the commit checked',
  })
  expect(alreadyAdded(ADDED, SHA, { why: 'gh api: HTTP 502' })).toEqual({
    commit: SHA, line: 'unchecked: whether the marketplace mk, at commit aaaaaaa, is behind its repo (gh api: HTTP 502); if it is, ' +
      'installing refreshes it, and the plugin is removed again if it then comes from another commit',
  })
  expect(alreadyAdded(ADDED, null, { why: 'gh api: HTTP 502' }).commit).toBe(null)
  // The clone's commit could not be read, so kirby does not know it is behind and must not say so.
  expect(alreadyAdded(ADDED, null, { sha: NEW })).toEqual({
    commit: NEW, line: 'marketplace: already added as mk, at a commit kirby could not read; installing refreshes it to bbbbbbb, the commit checked',
  })
})

test('a new marketplace is added, the plugin installed, and the clone checked against the commit shown', async () => {
  const f = fake([SHA])
  const r = await installPlugin(f.run, { ...plan, added: null })
  expect(f.claude()).toEqual(['claude plugin marketplace add o/mk', 'claude plugin install p@mk --scope local'])
  expect(r).toEqual({ ok: true, shown: ['claude plugin marketplace add o/mk', 'claude plugin install p@mk --scope local'], out: 'ran marketplace\nran install' })
})

test('a marketplace already added is installed from, not added again', async () => {
  const f = fake([SHA])
  const r = await installPlugin(f.run, { ...plan, added: ADDED })
  expect(f.claude()).toEqual(['claude plugin install p@mk --scope local'])
  expect(r.ok).toBe(true)
})

// Claude Code 2.1.312's install can replace the official marketplace's clone with a snapshot that is not a git
// repo and records its commit in .gcs-sha (seen 2026-10-30).
test('the commit of a marketplace that is a snapshot, not a git clone, is read from its .gcs-sha', async () => {
  expect(await headOf(fake([], `${SHA}\n`).run, ADDED)).toBe(SHA)
  expect(await headOf(fake([], 'not a sha').run, ADDED)).toBe(null)
  expect(await headOf(fake([]).run, ADDED)).toBe(null)
  const f = fake([], SHA)
  const r = await installPlugin(f.run, { ...plan, added: ADDED })
  expect(f.claude()).toEqual(['claude plugin install p@mk --scope local'])
  expect(r.ok).toBe(true)
})

test('a plugin that came from another commit is removed again, and the marketplace left as it is', async () => {
  for (const added of [null, ADDED]) {
    const f = fake([NEW])
    const r = await installPlugin(f.run, { ...plan, added })
    expect(f.claude()).toEqual([...(added ? [] : ['claude plugin marketplace add o/mk']), 'claude plugin install p@mk --scope local',
      'claude plugin uninstall p@mk --scope local'])
    expect(r.ok).toBe(false)
    expect(r.out.endsWith('\nthe marketplace mk has moved on: it is at commit bbbbbbb after the install, not aaaaaaa as shown to the ' +
      'user; the plugin was removed again')).toBe(true)
  }
})
