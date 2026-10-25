// The dialog text in the user's language: English, Traditional or Simplified Chinese.
// Pure: no `$`, so the tests can run it directly.

export type Lang = 'en' | 'zh-TW' | 'zh-CN'
export type Kind = 'skill' | 'plugin' | 'mcp'
export type Scope = 'local' | 'project' | 'user'

const TRADITIONAL = /zh[-_]?(tw|hk|mo|hant)|traditional|繁|台灣|臺灣|taiwan|香港|hong ?kong|cantonese|粵/
const SIMPLIFIED = /zh[-_]?(cn|sg|hans)|^zh\b|simplified|简|簡|chinese|中文|mandarin|普通话/

function match(value: string): Lang | null {
  const v = value.trim().toLowerCase()
  if (!v) return null
  if (TRADITIONAL.test(v)) return 'zh-TW'
  if (SIMPLIFIED.test(v)) return 'zh-CN'
  return 'en'
}

// `setting` is Claude Code's `language` setting, free text ("zh-TW", "japanese", "繁體中文");
// `locale` is the shell's LC_ALL or LANG ("zh_TW.UTF-8"), used when the setting is unset.
// Any language other than Chinese gets English.
export function pickLang(setting: unknown, locale: string | undefined): Lang {
  return match(typeof setting === 'string' ? setting : '') ?? match(locale ?? '') ?? 'en'
}

type Text = {
  options: { cancel: string; readme: string; other: string; install: string }
  next: string
  scope: string
  kind: (kind: string) => string
  commit: (sha: string) => string
  files: (n: number) => string
  scripts: (n: number, examples: string) => string
  exists: (name: string, force: boolean) => string
  about: (text: string) => string
  command: (cmd: string) => string
  where: Record<Kind, Record<Scope, string>>
  mcpNote: string
  pluginMcp: (sure: boolean, toolSearchOff: boolean) => string
}

export const TEXT: Record<Lang, Text> = {
  en: {
    options: { cancel: 'Cancel', readme: 'Read README first', other: 'Pick another', install: 'Install' },
    next: 'What next?',
    scope: 'Install at which scope?',
    kind: k => `Kind: ${k}`,
    commit: sha => `Version: commit ${sha}`,
    files: n => `Files: ${n}`,
    scripts: (n, ex) => `Scripts: ${n} executable file(s), e.g. ${ex}`,
    exists: (name, force) =>
      `Exists: this project already has .claude/skills/${name}/; installing at local or project ${force ? 'replaces it' : 'fails'}`,
    about: t => `About: ${t}`,
    command: c => `Command: ${c}`,
    where: {
      skill: {
        local: "this project's .claude/skills/, added to .gitignore, kept out of git",
        project: "this project's .claude/skills/, committed to git",
        user: '~/.claude/skills/, all your projects',
      },
      plugin: {
        local: 'only you, only this project (.claude/settings.local.json)',
        project: 'shared with the project (.claude/settings.json, committed to git)',
        user: 'all your projects (~/.claude/settings.json)',
      },
      mcp: {
        local: 'only you, only this project',
        project: 'shared with the project (.mcp.json, committed to git)',
        user: 'all your projects',
      },
    },
    mcpNote: "Note: MCP config takes effect after a restart; this session's prompt cache is not affected.",
    pluginMcp: (sure, off) =>
      (sure ? 'Note: this plugin brings an MCP server. ' : 'Note: cannot tell whether this plugin brings an MCP server (its source is in another repo). If it does: ') +
      (off
        ? 'ENABLE_TOOL_SEARCH=false is set, so loading it with /reload-plugins rebuilds the prompt cache once.'
        : 'if tool search is off in this session, loading it with /reload-plugins rebuilds the prompt cache once; with tool search on (the default) the cache is not affected.'),
  },
  'zh-TW': {
    options: { cancel: '取消', readme: '先看 README', other: '換一個', install: '安裝' },
    next: '下一步要做什麼？',
    scope: '安裝到哪個 scope？',
    kind: k => `種類：${k}`,
    commit: sha => `版本：commit ${sha}`,
    files: n => `檔案：${n} 個`,
    scripts: (n, ex) => `腳本：${n} 個可執行檔，例如 ${ex}`,
    exists: (name, force) => `已存在：這個專案已有 .claude/skills/${name}/，裝在 local 或 project 會${force ? '取代它' : '失敗'}`,
    about: t => `說明：${t}`,
    command: c => `指令：${c}`,
    where: {
      skill: {
        local: '這個專案的 .claude/skills/，並加進 .gitignore，不進 git',
        project: '這個專案的 .claude/skills/，會進 git',
        user: '~/.claude/skills/，你所有的專案',
      },
      plugin: {
        local: '只有你、只在這個專案啟用（.claude/settings.local.json）',
        project: '專案共用（.claude/settings.json，會進 git）',
        user: '你所有的專案（~/.claude/settings.json）',
      },
      mcp: {
        local: '只有你、只在這個專案',
        project: '專案共用（.mcp.json，會進 git）',
        user: '你所有的專案',
      },
    },
    mcpNote: '注意：MCP 設定要重開 session 才生效，這個 session 的 prompt cache 不受影響。',
    pluginMcp: (sure, off) =>
      (sure ? '注意：這個 plugin 帶有 MCP server。' : '注意：無法確定這個 plugin 是否帶有 MCP server（來源在其他 repo）。若有，') +
      (off
        ? '目前 ENABLE_TOOL_SEARCH=false，用 /reload-plugins 載入後，prompt cache 會重建一次。'
        : '如果這個 session 的 tool search 是關閉的，用 /reload-plugins 載入後，prompt cache 會重建一次；開著（預設）則不影響。'),
  },
  'zh-CN': {
    options: { cancel: '取消', readme: '先看 README', other: '换一个', install: '安装' },
    next: '下一步要做什么？',
    scope: '安装到哪个 scope？',
    kind: k => `类型：${k}`,
    commit: sha => `版本：commit ${sha}`,
    files: n => `文件：${n} 个`,
    scripts: (n, ex) => `脚本：${n} 个可执行文件，例如 ${ex}`,
    exists: (name, force) => `已存在：这个项目已有 .claude/skills/${name}/，装在 local 或 project 会${force ? '替换它' : '失败'}`,
    about: t => `说明：${t}`,
    command: c => `命令：${c}`,
    where: {
      skill: {
        local: '这个项目的 .claude/skills/，并加入 .gitignore，不进 git',
        project: '这个项目的 .claude/skills/，会进 git',
        user: '~/.claude/skills/，你所有的项目',
      },
      plugin: {
        local: '只有你、只在这个项目启用（.claude/settings.local.json）',
        project: '项目共享（.claude/settings.json，会进 git）',
        user: '你所有的项目（~/.claude/settings.json）',
      },
      mcp: {
        local: '只有你、只在这个项目',
        project: '项目共享（.mcp.json，会进 git）',
        user: '你所有的项目',
      },
    },
    mcpNote: '注意：MCP 配置要重启 session 才生效，这个 session 的 prompt cache 不受影响。',
    pluginMcp: (sure, off) =>
      (sure ? '注意：这个 plugin 带有 MCP server。' : '注意：无法确定这个 plugin 是否带有 MCP server（来源在其他 repo）。如果有，') +
      (off
        ? '当前 ENABLE_TOOL_SEARCH=false，用 /reload-plugins 加载后，prompt cache 会重建一次。'
        : '如果这个 session 的 tool search 是关闭的，用 /reload-plugins 加载后，prompt cache 会重建一次；开启（默认）则不影响。'),
  },
}
