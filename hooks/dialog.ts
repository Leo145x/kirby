// The dialogs' wording. The model writes it in the user's language (the tool's `dialog` input, in the
// format the inhale skill gives); the facts above it and the scope dialog's options stay the tool's
// own. When the wording is missing or unusable, the dialogs are in English. Pure: no `$`, so the tests
// can run it directly.

export type Kind = 'skill' | 'plugin' | 'mcp'
export type Scope = 'local' | 'project' | 'user'

export const SCOPES: readonly Scope[] = ['local', 'project', 'user']
// The scope dialog's options, the same in every language.
export const CANCEL = 'cancel'

export type Dialog = {
  about: string
  next: string
  // In this order: cancel, read the README first, pick another, install.
  options: readonly [string, string, string, string]
  scope: string
}

export function english(): Dialog {
  return {
    about: '',
    next: 'What next?',
    options: ['Cancel', 'Read README first', 'Pick another', 'Install'],
    scope: 'Install at which scope?',
  }
}

const MAX = { about: 600, next: 200, option: 40, scope: 600 }

function text(value: unknown, max: number): string | null {
  return typeof value === 'string' && value.trim() !== '' && value.length <= max ? value.trim() : null
}

// The model's wording, or English and why the wording could not be used.
export function readDialog(raw: unknown): { dialog: Dialog; problem?: string } {
  const fallback = (problem: string) => ({ dialog: english(), problem })
  if (!raw || typeof raw !== 'object') return fallback('no dialog was given')
  const d = raw as Record<string, unknown>

  const next = text(d.next, MAX.next)
  if (!next) return fallback(`dialog.next must be a question of at most ${MAX.next} characters`)
  const scope = text(d.scope, MAX.scope)
  if (!scope) return fallback(`dialog.scope must be a question of at most ${MAX.scope} characters`)
  const about = d.about === undefined ? '' : text(d.about, MAX.about)
  if (about === null) return fallback(`dialog.about, when given, must be at most ${MAX.about} characters`)
  const options = Array.isArray(d.options) ? d.options.map(o => text(o, MAX.option)) : []
  if (options.length !== 4 || options.some(o => o === null) || new Set(options).size !== 4) {
    return fallback(`dialog.options must be 4 distinct labels of at most ${MAX.option} characters`)
  }
  return { dialog: { about, next, options: options as unknown as Dialog['options'], scope } }
}
