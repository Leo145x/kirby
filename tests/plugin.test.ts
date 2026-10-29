import { expect, test } from 'claude-code/testing'

import { addedMarketplace, behind, installPlugin } from '../hooks/plugin'
import type { Run } from '../hooks/plugin'

const SHA = 'a'.repeat(40)
const NEW = 'b'.repeat(40)
const LOC = '/home/u/.claude/plugins/marketplaces/mk'
const LISTED = JSON.stringify([
  { name: 'other', source: 'github', repo: 'o/other', installLocation: '/x/other' },
  { name: 'mk', source: 'github', repo: 'O/MK', installLocation: LOC },
])

// Claude Code's CLI and git as the install sees them: heads are what `git rev-parse HEAD` gives, call by call;
// listed is what `claude plugin marketplace list --json` gives, call by call (the last one stays).
function fake(heads: string[], listed: string[] = [LISTED]) {
  const ran: string[][] = []
  const run: Run = async argv => {
    ran.push([...argv])
    if (argv[0] === 'git') return { ok: true, out: heads.shift() ?? '' }
    if (argv.join(' ') === 'claude plugin marketplace list --json') return { ok: true, out: listed.length > 1 ? listed.shift()! : listed[0]! }
    return { ok: true, out: `ran ${argv[2]}` }
  }
  return { run, ran, claude: () => ran.filter(a => a[0] === 'claude' && a[3] !== 'list').map(a => a.join(' ')) }
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

test("a marketplace behind its repo is not installed from, since Claude Code's install would update it", async () => {
  const added = { name: 'mk', location: LOC }
  expect(behind('o/mk', added, SHA, SHA)).toBe(null)
  expect(behind('o/mk', added, SHA, NEW)).toBe(
    'the marketplace mk is already added, at commit aaaaaaa, but o/mk is now at bbbbbbb. Claude Code updates a marketplace ' +
      'when it installs from it, so the plugin would come from a commit nobody checked, and kirby leaves the marketplace ' +
      'as it is. The user can update it with `claude plugin marketplace update mk` and then ask again.',
  )
})

test('a new marketplace is added, its clone checked against the commit shown, then the plugin installed', async () => {
  const f = fake([SHA, SHA])
  const r = await installPlugin(f.run, { ...plan, added: null })
  expect(f.claude()).toEqual(['claude plugin marketplace add o/mk', 'claude plugin install p@mk --scope local'])
  expect(f.ran.filter(a => a[0] === 'git')).toEqual([['git', '-C', LOC, 'rev-parse', 'HEAD'], ['git', '-C', LOC, 'rev-parse', 'HEAD']])
  expect(r).toEqual({ ok: true, shown: ['claude plugin marketplace add o/mk', 'claude plugin install p@mk --scope local'], out: 'ran marketplace\nran install' })
})

test('a new marketplace at another commit is removed again and nothing is installed', async () => {
  const f = fake([NEW])
  const r = await installPlugin(f.run, { ...plan, added: null })
  expect(f.claude()).toEqual(['claude plugin marketplace add o/mk', 'claude plugin marketplace remove mk'])
  expect(r.ok).toBe(false)
  // The output of add, then of remove, then why.
  expect(r.out).toBe('ran marketplace\nran marketplace\nthe marketplace mk has moved on: it is now at commit bbbbbbb, not aaaaaaa as ' +
    'shown to the user; nothing installed, and the marketplace was removed again')
})

test('a marketplace already added is installed from as it is, and not added or removed', async () => {
  const f = fake([SHA, SHA], [LISTED])
  const r = await installPlugin(f.run, { ...plan, added: { name: 'mk', location: LOC } })
  expect(f.claude()).toEqual(['claude plugin install p@mk --scope local'])
  expect(r.ok).toBe(true)
  const moved = fake([NEW], [LISTED])
  const m = await installPlugin(moved.run, { ...plan, added: { name: 'mk', location: LOC } })
  expect(moved.claude()).toEqual([])
  expect(m.out).toBe('the marketplace mk has moved on: it is now at commit bbbbbbb, not aaaaaaa as shown to the user; nothing installed')
})

test('an install that moved the marketplace is uninstalled again', async () => {
  const f = fake([SHA, NEW])
  const r = await installPlugin(f.run, { ...plan, added: null })
  expect(f.claude()).toEqual(['claude plugin marketplace add o/mk', 'claude plugin install p@mk --scope local',
    'claude plugin uninstall p@mk --scope local', 'claude plugin marketplace remove mk'])
  expect(r.ok).toBe(false)
  expect(r.out.endsWith('\nthe marketplace mk has moved on: Claude Code updated it to commit bbbbbbb while installing, not ' +
    'aaaaaaa as shown to the user; the plugin was uninstalled again, and the marketplace removed')).toBe(true)
})
