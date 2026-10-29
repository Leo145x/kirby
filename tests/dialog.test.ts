import { expect, test } from 'claude-code/testing'

import { CANCEL, english, nextOptions, readDialog, readReview, reviewNote, SCOPES } from '../hooks/dialog'

const GOOD = {
  about: '把 archify 裝成 skill。',
  next: '下一步？',
  options: ['取消', '先讀 README', '換一個', '安裝'],
  scope: '裝在哪個範圍？',
}

test("the model's wording is used when it is complete", async () => {
  const { dialog, problem } = readDialog(GOOD)
  expect(problem).toBe(undefined)
  expect(dialog).toEqual(GOOD)
})

test("the scope options are the tool's own", async () => {
  // Extra keys from an older skill, such as scopes, are ignored.
  const { dialog, problem } = readDialog({ ...GOOD, scopes: { user: '你所有的專案' } })
  expect(problem).toBe(undefined)
  expect('scopes' in dialog).toBe(false)
  expect(new Set([CANCEL, ...SCOPES]).size).toBe(4)
})

test('missing or unusable wording falls back to English and says why', async () => {
  expect(readDialog(undefined)).toEqual({ dialog: english(), problem: 'no dialog was given' })
  const bad = [
    { ...GOOD, next: '' },
    { ...GOOD, scope: '  ' },
    { ...GOOD, options: ['取消', '先讀 README', '安裝'] },
    { ...GOOD, options: ['取消', '取消', '換一個', '安裝'] },
    { ...GOOD, about: 'x'.repeat(601) },
  ]
  for (const raw of bad) {
    const { dialog, problem } = readDialog(raw)
    expect(dialog).toEqual(english())
    expect(typeof problem).toBe('string')
  }
})

// The model review's result as the install tool takes it (docs/adr/0002); the rules match codex/dialog.py.
const SHA = 'a'.repeat(40)
const NEEDED = { needed: true, repo: 'o/r', sha: SHA, files: ['s/SKILL.md', 's/run.sh'] }
const OK = { file: 's/run.sh', line: 1, reason: 'Runs a download.' }

test("findings are warn lines labelled as the model's", async () => {
  expect(readReview({ findings: [{ file: 's/run.sh', line: 3, reason: 'Sends the token to a host.' }] }, SHA, NEEDED))
    .toEqual({ lines: ['warn: s/run.sh:3: Sends the token to a host. (model review, as reported by the model)'] })
  expect(readReview({ findings: [] }, SHA, NEEDED)).toEqual({ lines: ['model review: nothing found (as reported by the model)'] })
})

test('a missing review, one that could not run, or one of another commit is one unchecked line', async () => {
  expect(readReview(undefined, undefined, NEEDED)).toEqual({ lines: ['model review: unchecked (no review result was passed)'] })
  expect(readReview({ could_not_run: 'no subagent tool' }, undefined, NEEDED)).toEqual({ lines: ['model review: unchecked (no subagent tool)'] })
  expect(readReview(undefined, undefined, { needed: true, files: [] }))
    .toEqual({ lines: ['model review: unchecked (kirby had no files of it to read)'] })
  expect(readReview({ findings: [] }, 'b'.repeat(40), NEEDED))
    .toEqual({ lines: ['model review: unchecked (it read bbbbbbb, not aaaaaaa, the one checked here)'] })
})

test('without a danger or warn finding no review reaches the dialog', async () => {
  for (const raw of [undefined, { findings: [OK] }, { could_not_run: 'x' }, 'junk']) {
    expect(readReview(raw, SHA, { ...NEEDED, needed: false })).toEqual({ lines: [] })
  }
})

test('hidden and control characters are stripped', async () => {
  expect(readReview({ findings: [{ ...OK, reason: 'Reads​ ~/.ssh‮ and\nposts\tit.' }] }, SHA, NEEDED))
    .toEqual({ lines: ['warn: s/run.sh:1: Reads ~/.ssh and posts it. (model review, as reported by the model)'] })
  expect(readReview({ could_not_run: 'timed\x1b[2J out' }, undefined, NEEDED)).toEqual({ lines: ['model review: unchecked (timed [2J out)'] })
})

test('anything outside the structure or the limits is refused', async () => {
  const shape = 'review must be {"findings": [...]} or {"could_not_run": "<reason>"}'
  const cases: [unknown, string | undefined, string][] = [
    ['could not run: x', SHA, shape],
    [{ findings: [], could_not_run: 'x' }, SHA, shape],
    [{ findings: Array(6).fill(OK) }, SHA, 'review.findings must be a list of at most 5'],
    [{ findings: [{ ...OK, reason: 'x'.repeat(121) }] }, SHA, 'review.findings[0].reason must be one sentence of at most 120 characters'],
    [{ findings: [{ ...OK, reason: ' ​ ' }] }, SHA, 'review.findings[0].reason must be one sentence of at most 120 characters'],
    [{ findings: [OK, { ...OK, file: 's/other.sh' }] }, SHA, 'review.findings[1].file must be one of the files the check tool listed'],
    [{ findings: [{ ...OK, line: 0 }] }, SHA, 'review.findings[0].line must be a line number'],
    [{ findings: [{ ...OK, line: 1.5 }] }, SHA, 'review.findings[0].line must be a line number'],
    [{ findings: [{ ...OK, quote: 'x' }] }, SHA, 'review.findings[0] must have exactly file, line and reason'],
    [{ could_not_run: 'x'.repeat(121) }, SHA, 'review.could_not_run must be a reason of at most 120 characters'],
    [{ findings: [OK] }, undefined, 'sha must be the one the check tool returned, which the review read'],
  ]
  for (const [raw, sha, problem] of cases) expect(readReview(raw, sha, NEEDED)).toEqual({ lines: [], problem })
  // The limits count characters, not UTF-16 units.
  expect(readReview({ findings: [{ ...OK, reason: '𠀀'.repeat(120) }] }, SHA, NEEDED).problem).toBe(undefined)
})

test("the review's lines reach the model too", async () => {
  expect(reviewNote([])).toBe('')
  expect(reviewNote(['model review: unchecked (x)']))
    .toBe('review: the dialog showed the user these model review lines:\n  model review: unchecked (x)')
})

test('a blocked install leaves Install out of the first dialog', async () => {
  const { dialog } = readDialog(GOOD)
  expect(nextOptions(dialog, false)).toEqual(['取消', '先讀 README', '換一個', '安裝'])
  expect(nextOptions(dialog, true)).toEqual(['取消', '先讀 README', '換一個'])
})
