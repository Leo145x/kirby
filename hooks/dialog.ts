// The dialogs' wording. The model writes it in the user's language (the tool's `dialog` input, in the
// format the inhale skill gives) and picks the language of the facts above it (dialog.lang), which kirby
// words itself (words.ts, docs/adr/0006); the scope dialog's options stay the tool's own. When the wording
// is missing or unusable, the dialogs and their facts are in English. The model review's result (the
// tool's `review` input), once readReview checks it, reaches the first dialog only in kirby's words
// (reviewFacts) and the model in full (reviewNote). Pure: no `$`, so the
// tests can run it directly; the rules match codex/dialog.py.

import { fact, readLang, say } from './words'
import type { Fact, Keyed, Lang } from './words'

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
  // The language of the facts, which kirby words.
  lang: Lang
}

export function english(): Dialog {
  return {
    about: '',
    next: 'What next?',
    options: ['Cancel', 'Read README first', 'Pick another', 'Install'],
    scope: 'Install at which scope?',
    lang: 'en',
  }
}

// The first dialog's options. A block (a malware-lookup finding) leaves Install out, so the user
// cannot pick it (docs/adr/0001).
export function nextOptions(d: Dialog, blocked: boolean): string[] {
  return blocked ? d.options.slice(0, 3) : [...d.options]
}

// In characters (code points, as Python counts them), not UTF-16 units.
export const MAX = { about: 120, next: 200, option: 40, scope: 600 }

function text(value: unknown, max: number): string | null {
  return typeof value === 'string' && value.trim() !== '' && [...value].length <= max ? value.trim() : null
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
  return { dialog: { about, next, options: options as unknown as Dialog['options'], scope, lang: readLang(d.lang) } }
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

// What the model review's result comes to, once checked: what the dialog shows of it (in kirby's words, through
// reviewFacts) and what the model is told (reviewNote). The reviewer's own text is in `findings` and `reviewer`,
// which reach only the model (docs/adr/0006).
export type ReviewFinding = { file: string; line: number; reason: string }
export type Reviewed =
  | { state: 'not needed' }
  | { state: 'found'; findings: ReviewFinding[] }
  | { state: 'nothing found' }
  // why: kirby's own reason, worded in the dialog's language.
  | { state: 'did not run'; why: Keyed }
  // reviewer: the reason the reviewer gave (could_not_run), cleaned; the dialog does not show it.
  | { state: 'did not run'; reviewer: string }

// The model review's result, checked; or why it is refused, so the model sends it again. review is the check's
// own; sha is the one the model says the review read. A review the check did not ask for is left out, and a
// missing one, or one that could not run, did not run (docs/adr/0002, docs/adr/0005).
export function readReview(raw: unknown, sha: unknown, review: Review): { reviewed?: Reviewed; problem?: string } {
  const refuse = (problem: string) => ({ problem })
  if (!review.needed) return { reviewed: { state: 'not needed' } }
  if (raw === undefined || raw === null) {
    return { reviewed: { state: 'did not run', why: fact(review.files.length ? 'review_no_result' : 'review_no_files') } }
  }
  const keys = raw && typeof raw === 'object' && !Array.isArray(raw) ? Object.keys(raw) : []
  const key = keys.length === 1 ? keys[0] : undefined
  if (key !== 'findings' && key !== 'could_not_run') return refuse(REVIEW_SHAPE)
  const r = raw as Record<string, unknown>
  if (key === 'could_not_run') {
    const why = reason(r.could_not_run)
    if (!why) return refuse(`review.could_not_run must be a reason of at most ${REVIEW_MAX.reason} characters`)
    return { reviewed: { state: 'did not run', reviewer: why } }
  }
  const findings = r.findings
  if (!Array.isArray(findings) || findings.length > REVIEW_MAX.findings) {
    return refuse(`review.findings must be a list of at most ${REVIEW_MAX.findings}`)
  }
  const found: ReviewFinding[] = []
  for (const [i, f] of findings.entries()) {
    const at = `review.findings[${i}]`
    const fields = f && typeof f === 'object' && !Array.isArray(f) ? Object.keys(f).sort().join() : ''
    if (fields !== 'file,line,reason') return refuse(`${at} must have exactly file, line and reason`)
    const { file, line, reason: why } = f as Record<string, unknown>
    if (typeof file !== 'string' || !review.files.includes(file)) return refuse(`${at}.file must be one of the files the check tool listed`)
    if (typeof line !== 'number' || !Number.isInteger(line) || line < 1) return refuse(`${at}.line must be a line number`)
    const text = reason(why)
    if (!text) return refuse(`${at}.reason must be one sentence of at most ${REVIEW_MAX.reason} characters`)
    found.push({ file, line, reason: text })
  }
  if (typeof sha !== 'string' || !sha) return refuse('sha must be the one the check tool returned, which the review read')
  if (sha !== review.sha) {
    const why = fact('review_other_commit', { read: sha.slice(0, 7), checked: String(review.sha).slice(0, 7) })
    return { reviewed: { state: 'did not run', why } }
  }
  return { reviewed: found.length ? { state: 'found', findings: found } : { state: 'nothing found' } }
}

// The facts with the review's result as the dialog shows it, in kirby's words only: its findings counted on the warn
// line, or a line saying it found nothing or did not run, with kirby's reason but never the reviewer's.
export function reviewFacts(facts: readonly Fact[], r: Reviewed): Fact[] {
  switch (r.state) {
    case 'not needed': return [...facts]
    case 'found': return countReview(facts, r.findings.length)
    case 'nothing found': return [...facts, fact('review_nothing')]
    case 'did not run': return [...facts, 'why' in r ? fact('review_not_run_why', { why: r.why }) : fact('review_not_run')]
  }
}

// The facts with n model review findings counted on the warn line, as the dialog shows them: it counts the review's
// findings and shows none of the reviewer's text (docs/adr/0006). Without a warn line, it makes one after the
// danger lines, or before the check's first line. The facts given are left as they are.
export function countReview(facts: readonly Fact[], n: number): Fact[] {
  if (n === 0) return [...facts]
  const review = fact('warn_review', { count: n })
  const at = facts.findIndex(f => typeof f !== 'string' && f.key === 'warn')
  if (at >= 0) {
    const w = facts[at] as Keyed
    const names = w.args.names as readonly (string | Keyed)[]
    return facts.map((f, i) => (i === at ? fact('warn', { count: Number(w.args.count) + n, names: [...names, review] }) : f))
  }
  const keyed = (f: Fact, test: (key: string) => boolean) => typeof f !== 'string' && test(f.key)
  const danger = facts.map(f => keyed(f, k => k.startsWith('danger_') || k === 'check_blocked')).lastIndexOf(true)
  const first = facts.findIndex(f => keyed(f, k => /^(check|scan|lookup)_/.test(k)))
  const i = danger >= 0 ? danger + 1 : first >= 0 ? first : facts.length
  return [...facts.slice(0, i), fact('warn', { count: n, names: [review] }), ...facts.slice(i)]
}

// The review's result for the model, in English, in every result after the dialog opens: every finding with its file,
// line and reason, and the reviewer's reason when it could not run, which the dialog left out; '' without a review.
export function reviewNote(r: Reviewed): string {
  switch (r.state) {
    case 'not needed': return ''
    case 'found': return `review: the model review's findings, ${LABEL} (the dialog showed the user only how many, on the warn line):\n` +
      r.findings.map(f => `  warn: ${f.file}:${f.line}: ${f.reason}`).join('\n')
    case 'nothing found': return `review: the dialog showed the user that the model review found nothing, ${LABEL}`
    case 'did not run': return 'why' in r
      ? `review: the dialog showed the user that the model review did not run (${say(r.why, 'en')})`
      : `review: the dialog showed the user that the model review did not run, without its reason, ${LABEL}: ${r.reviewer}`
  }
}
