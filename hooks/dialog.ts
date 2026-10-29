// The dialogs' wording. The model writes it in the user's language (the tool's `dialog` input, in the
// format the inhale skill gives); the facts above it and the scope dialog's options stay the tool's
// own. When the wording is missing or unusable, the dialogs are in English. The model review's result
// (the tool's `review` input) also reaches the first dialog, as readReview checks it. Pure: no `$`, so
// the tests can run it directly; the rules match codex/dialog.py.

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

// The first dialog's options. A block (a malware-lookup finding) leaves Install out, so the user
// cannot pick it (docs/adr/0001).
export function nextOptions(d: Dialog, blocked: boolean): string[] {
  return blocked ? d.options.slice(0, 3) : [...d.options]
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

// What the check says about the model review: whether it was needed (another part of the check found a
// danger or warn finding), the sha it covered and the files, as the scripts' `review` gives them.
export type Review = { needed: boolean; sha?: string; files: string[] }

// The model review's limits (docs/adr/0002), in characters.
export const REVIEW_MAX = { reason: 120, findings: 5 }
const REVIEW_SHAPE = 'review must be {"findings": [...]} or {"could_not_run": "<reason>"}'
const LABEL = 'as reported by the model'

// The model's text, which may carry what it read in the files: format, private-use and unassigned
// characters go, control characters and line breaks become spaces, and runs of spaces become one.
export function clean(text: string): string {
  return text.replace(/[\p{Cf}\p{Co}\p{Cs}\p{Cn}]/gu, '').replace(/[\s\p{Cc}]/gu, ' ').replace(/ +/g, ' ').trim()
}

function reason(value: unknown): string | null {
  return typeof value === 'string' && [...value].length <= REVIEW_MAX.reason ? clean(value) || null : null
}

// The model review's lines for the first dialog; or no lines and why the result is refused, so the model
// sends it again. review is the check's own; sha is the one the model says the review read. A review the
// check did not ask for is left out, and a missing one, or one that could not run, is one unchecked line
// (docs/adr/0002, docs/adr/0005).
export function readReview(raw: unknown, sha: unknown, review: Review): { lines: string[]; problem?: string } {
  const refuse = (problem: string) => ({ lines: [], problem })
  if (!review.needed) return { lines: [] }
  if (raw === undefined || raw === null) {
    return { lines: [`model review: unchecked (${review.files.length ? 'no review result was passed' : 'kirby had no files of it to read'})`] }
  }
  const keys = raw && typeof raw === 'object' && !Array.isArray(raw) ? Object.keys(raw) : []
  const key = keys.length === 1 ? keys[0] : undefined
  if (key !== 'findings' && key !== 'could_not_run') return refuse(REVIEW_SHAPE)
  const r = raw as Record<string, unknown>
  if (key === 'could_not_run') {
    const why = reason(r.could_not_run)
    if (!why) return refuse(`review.could_not_run must be a reason of at most ${REVIEW_MAX.reason} characters`)
    return { lines: [`model review: unchecked (${why})`] }
  }
  const findings = r.findings
  if (!Array.isArray(findings) || findings.length > REVIEW_MAX.findings) {
    return refuse(`review.findings must be a list of at most ${REVIEW_MAX.findings}`)
  }
  const lines: string[] = []
  for (const [i, f] of findings.entries()) {
    const at = `review.findings[${i}]`
    const fields = f && typeof f === 'object' && !Array.isArray(f) ? Object.keys(f).sort().join() : ''
    if (fields !== 'file,line,reason') return refuse(`${at} must have exactly file, line and reason`)
    const { file, line, reason: why } = f as Record<string, unknown>
    if (typeof file !== 'string' || !review.files.includes(file)) return refuse(`${at}.file must be one of the files the check tool listed`)
    if (typeof line !== 'number' || !Number.isInteger(line) || line < 1) return refuse(`${at}.line must be a line number`)
    const text = reason(why)
    if (!text) return refuse(`${at}.reason must be one sentence of at most ${REVIEW_MAX.reason} characters`)
    lines.push(`warn: ${file}:${line}: ${text} (model review, ${LABEL})`)
  }
  if (typeof sha !== 'string' || !sha) return refuse('sha must be the one the check tool returned, which the review read')
  if (sha !== review.sha) {
    return { lines: [`model review: unchecked (it read ${sha.slice(0, 7)}, not ${String(review.sha).slice(0, 7)}, the one checked here)`] }
  }
  return { lines: lines.length ? lines : [`model review: nothing found (${LABEL})`] }
}

// The review's dialog lines for the model, in every result after the dialog opens; '' without any.
export function reviewNote(lines: readonly string[]): string {
  return lines.length ? `review: the dialog showed the user these model review lines:\n${lines.map(l => `  ${l}`).join('\n')}` : ''
}
