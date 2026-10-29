import { expect, test } from 'claude-code/testing'

import { checkResult, fileRequest, fileText } from '../hooks/check'
import type { Package } from '../hooks/check'

const SHA = 'a'.repeat(40)
const DIGEST = 'e'.repeat(64)
const SCRIPTS = '/k/skills/inhale/scripts'
const PACKAGE: Package = { ecosystem: 'npm', name: '@o/srv', version: '1.2.3' }

test('check gives what the review reads and the other findings', async () => {
  const lines = ['skill: s · commit aaaaaaa · 2 files', 'warn: credentials ×1 (run.sh:1)']
  expect(JSON.parse(checkResult(lines, { needed: true, repo: 'o/r', sha: SHA, files: ['s/SKILL.md', 's/run.sh'] }, false))).toEqual({
    review: 'needed', read: { repo: 'o/r', ref: SHA }, files: ['s/SKILL.md', 's/run.sh'], findings: lines, blocked: false,
  })
  expect(JSON.parse(checkResult([], { needed: true, package: PACKAGE, sha: DIGEST, files: ['dist/index.js'] }, false)).read)
    .toEqual({ package: PACKAGE, ref: DIGEST })
})

test('check says when no review is needed or possible, and lists at most 200 files', async () => {
  const quiet = JSON.parse(checkResult(['check: nothing found (…)'], { needed: false, repo: 'o/r', sha: SHA, files: ['a'] }, false))
  expect(quiet).toEqual({ review: 'not needed', findings: ['check: nothing found (…)'], blocked: false })
  expect(JSON.parse(checkResult([], { needed: true, files: [] }, false)).review)
    .toBe('not possible: kirby has no files of it to read; call install without review')
  const many = JSON.parse(checkResult([], { needed: true, repo: 'o/r', sha: SHA, files: Array.from({ length: 250 }, (_, i) => `${i}.md`) }, false))
  expect([many.files.length, many.more_files]).toEqual([200, 50])
})

test('the file tool reads a repo at a commit, or the package the check unpacked', async () => {
  expect(fileRequest({ repo: 'o/r', path: 'skills/s/run me.sh', ref: SHA }, SCRIPTS)).toEqual({
    argv: ['gh', 'api', `repos/o/r/contents/skills/s/run%20me.sh?ref=${SHA}`, '-H', 'Accept: application/vnd.github.raw'],
  })
  expect(fileRequest({ package: PACKAGE, path: 'dist/index.js', ref: DIGEST }, SCRIPTS)).toEqual({
    argv: ['python3', '-I', `${SCRIPTS}/check_mcp.py`, '--read', JSON.stringify({ ...PACKAGE, sha: DIGEST, path: 'dist/index.js' })],
  })
})

test('the file tool refuses anything else before running anything', async () => {
  const repo = { repo: 'o/r', path: 'a.sh', ref: SHA }
  const pkg = { package: PACKAGE, path: 'a.js', ref: DIGEST }
  for (const bad of [
    { ...repo, path: '../x' }, { ...repo, path: '/etc/passwd' }, { ...repo, ref: 'main' }, { ...repo, repo: 'o/r/x' },
    { ...pkg, ref: SHA }, { ...pkg, path: '../x' }, { ...pkg, package: { ...PACKAGE, ecosystem: 'cargo' } },
    { ...pkg, package: { ...PACKAGE, version: '' } }, { ...pkg, repo: 'o/r' },
  ]) {
    expect(typeof (fileRequest(bad, SCRIPTS) as { problem?: string }).problem).toBe('string')
  }
})

test('a long file is cut', async () => {
  expect(fileText('x'.repeat(20_001))).toBe(`${'x'.repeat(20_000)}\n\n[truncated at 20000 characters]`)
  expect(fileText('short')).toBe('short')
})
