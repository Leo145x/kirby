import { expect, test } from 'claude-code/testing'

import { pickLang, TEXT } from '../hooks/i18n'

test('the language setting picks the dialog language', async () => {
  for (const v of ['zh-TW', 'zh_TW', 'zh-Hant', 'zh-HK', '繁體中文', 'Traditional Chinese', 'taiwanese']) {
    expect(pickLang(v, undefined)).toBe('zh-TW')
  }
  for (const v of ['zh-CN', 'zh', 'zh-Hans', '简体中文', 'Simplified Chinese', 'chinese', '中文']) {
    expect(pickLang(v, undefined)).toBe('zh-CN')
  }
  for (const v of ['english', 'en', 'japanese', 'spanish']) expect(pickLang(v, undefined)).toBe('en')
})

test('with no setting the locale decides, and English is the fallback', async () => {
  expect(pickLang(undefined, 'zh_TW.UTF-8')).toBe('zh-TW')
  expect(pickLang('', 'zh_CN.UTF-8')).toBe('zh-CN')
  expect(pickLang(undefined, 'en_US.UTF-8')).toBe('en')
  expect(pickLang(undefined, undefined)).toBe('en')
  // An explicit setting wins over the locale.
  expect(pickLang('japanese', 'zh_TW.UTF-8')).toBe('en')
})

test('every language has distinct option labels', async () => {
  for (const t of Object.values(TEXT)) expect(new Set(Object.values(t.options)).size).toBe(4)
})
