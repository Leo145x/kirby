// kirby's own wording of the dialog's fact lines, in English, 繁體中文 and 简体中文 (docs/adr/0006). The model
// only picks the language (dialog.lang); it never writes or translates a fact line. A fact is either a line
// kirby has no wording for yet, a string shown as it is in every language, or a key and the values put into
// that key's wording. Values (commands, paths, names, versions, ids, numbers) go in as they are, so they can
// be copied and looked up. Only the dialogs are worded; what the tools answer the model stays English
// (say(f, 'en')). Pure: no `$`. The same table is skills/inhale/scripts/words.py's, which the Codex server and
// the scripts use; tests/test_codex.py checks the two match, and both sides' tests give the same cases.

export type Lang = 'en' | 'zh-TW' | 'zh-CN'
export const LANGS: readonly Lang[] = ['en', 'zh-TW', 'zh-CN']

// To add a line: add its key with its wording in all three languages, here and in words.py. `{name}` takes the
// value named; a list of values is joined with the language's `list`.
// words:start
const WORDS = {
  "list": {"en": ", ", "zh-TW": "、", "zh-CN": "、"},
  "repo": {"en": "{repo} ★{stars} · pushed {pushed}", "zh-TW": "{repo} ★{stars} · {pushed} 更新", "zh-CN": "{repo} ★{stars} · {pushed} 更新"},
  "repo_archived": {
    "en": "{repo} ★{stars} · pushed {pushed} · ARCHIVED",
    "zh-TW": "{repo} ★{stars} · {pushed} 更新 · 已封存",
    "zh-CN": "{repo} ★{stars} · {pushed} 更新 · 已归档"
  },
  "skill": {
    "en": "skill: {name} · commit {commit} · {files} files",
    "zh-TW": "技能：{name} · commit {commit} · {files} 個檔案",
    "zh-CN": "技能：{name} · commit {commit} · {files} 个文件"
  },
  "scripts": {"en": "scripts: {count}, e.g. {names}", "zh-TW": "{count} 個腳本，例如 {names}", "zh-CN": "{count} 个脚本，例如 {names}"},
  "exists_fails": {
    "en": "exists: {path} (installing at local or project fails)",
    "zh-TW": "已存在：{path}（安裝在 local 或 project 會失敗）",
    "zh-CN": "已存在：{path}（安装在 local 或 project 会失败）"
  },
  "exists_replaces": {
    "en": "exists: {path} (installing at local or project replaces it)",
    "zh-TW": "已存在：{path}（安裝在 local 或 project 會取代它）",
    "zh-CN": "已存在：{path}（安装在 local 或 project 会替换它）"
  },
  "installs_at_user": {
    "en": "installs at: user (~/.codex/config.toml, every project)",
    "zh-TW": "安裝位置：user（~/.codex/config.toml，所有專案）",
    "zh-CN": "安装位置：user（~/.codex/config.toml，所有项目）"
  },
  "installs_at_user_skill": {
    "en": "installs at: user (~/.agents/skills/; Codex did not say which project this session is in)",
    "zh-TW": "安裝位置：user（~/.agents/skills/；Codex 沒有說這個工作階段在哪個專案）",
    "zh-CN": "安装位置：user（~/.agents/skills/；Codex 没有说这个会话在哪个项目）"
  }
}
// words:end

export type Key = Exclude<keyof typeof WORDS, 'list'>
type Value = string | number | readonly string[]
export type Fact = string | { key: Key; args: Record<string, Value> }

export function fact(key: Key, args: Record<string, Value> = {}): Fact {
  return { key, args }
}

// The language the model picked, or English for anything else.
export function readLang(value: unknown): Lang {
  return LANGS.find(l => l === value) ?? 'en'
}

// One fact line in the language given.
export function say(f: Fact, lang: Lang): string {
  if (typeof f === 'string') return f
  return WORDS[f.key][lang].replace(/\{(\w+)\}/g, (_, name: string) => {
    if (!(name in f.args)) throw new Error(`${f.key} needs ${name}`)
    const v = f.args[name]
    return Array.isArray(v) ? v.join(WORDS.list[lang]) : String(v)
  })
}
