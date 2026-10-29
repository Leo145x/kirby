import { expect, test } from 'claude-code/testing'

import { CANCEL, english, nextOptions, readDialog, SCOPES } from '../hooks/dialog'

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

test('a blocked install leaves Install out of the first dialog', async () => {
  const { dialog } = readDialog(GOOD)
  expect(nextOptions(dialog, false)).toEqual(['取消', '先讀 README', '換一個', '安裝'])
  expect(nextOptions(dialog, true)).toEqual(['取消', '先讀 README', '換一個'])
})
