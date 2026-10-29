// The read-only tools beside install, for the model review (docs/adr/0002): `check` runs install's
// pre-install check without a dialog and says whether a review is needed and what it reads; `file` reads
// one file where the check read it, a repo at a commit or an MCP server's package. Pure: no `$`, so the
// tests can run it directly; the rules match codex/server.py's check() and file().

import type { Review } from './dialog'

// What the scripts' `review` gives: for a commit the repo, for an MCP server's package the package, whose
// archive the sha (its sha256) names.
export type Package = { ecosystem: 'npm' | 'PyPI'; name: string; version: string }
export type ReviewOf = Review & { repo?: string; package?: Package }

const REPO_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/
const SHA_RE = /^[0-9a-f]{40}$/
const PACKAGE_SHA_RE = /^[0-9a-f]{64}$/
const FILES_SHOWN = 200
const FILE_MAX = 20_000
const NO_FILES = 'not possible: kirby has no files of it to read; call install without review'

// The check tool's answer, as JSON for the model: whether a review is needed, what the file tool reads it
// from and which files, and the dialog's facts.
export function checkResult(lines: readonly string[], review: ReviewOf, blocked: boolean): string {
  const state = !review.needed ? 'not needed' : review.files.length ? 'needed' : NO_FILES
  const out: Record<string, unknown> = { review: state }
  if (state === 'needed') {
    out.read = review.package ? { package: review.package, ref: review.sha } : { repo: review.repo, ref: review.sha }
    out.files = review.files.slice(0, FILES_SHOWN)
    if (review.files.length > FILES_SHOWN) out.more_files = review.files.length - FILES_SHOWN
  }
  return JSON.stringify({ ...out, findings: lines, blocked })
}

function insidePath(path: unknown): path is string {
  return typeof path === 'string' && path !== '' && !path.startsWith('/') && !path.split('/').includes('..')
}

// The command that reads one file for the file tool, or why the input is refused.
export function fileRequest(input: Record<string, unknown>, scripts: string): { argv: string[] } | { problem: string } {
  const { repo, path, ref, package: pkg } = input
  if (!insidePath(path)) return { problem: `not a path inside the ${pkg !== undefined ? 'package' : 'repo'}: ${JSON.stringify(path)}` }
  if (pkg !== undefined) {
    // An MCP server's package, read from the archive the check unpacked, which ref names by its sha256.
    if (repo !== undefined) return { problem: 'give repo or package, not both' }
    const p = (pkg && typeof pkg === 'object' && !Array.isArray(pkg) ? pkg : {}) as Record<string, unknown>
    if (Object.keys(p).sort().join() !== 'ecosystem,name,version' || !['npm', 'PyPI'].includes(String(p.ecosystem))
      || typeof p.name !== 'string' || !p.name || typeof p.version !== 'string' || !p.version) {
      return { problem: 'package must be {"ecosystem": "npm" or "PyPI", "name", "version"}, as the check tool gives it' }
    }
    if (typeof ref !== 'string' || !PACKAGE_SHA_RE.test(ref)) return { problem: 'ref must be the sha256 the check tool gave for the package' }
    const want = { ecosystem: p.ecosystem, name: p.name, version: p.version, sha: ref, path }
    return { argv: ['python3', '-I', `${scripts}/check_mcp.py`, '--read', JSON.stringify(want)] }
  }
  if (typeof repo !== 'string' || !REPO_RE.test(repo)) return { problem: `not an owner/repo: ${JSON.stringify(repo)}` }
  if (typeof ref !== 'string' || !SHA_RE.test(ref)) return { problem: 'ref must be the full 40-character commit sha' }
  const at = path.split('/').map(encodeURIComponent).join('/')
  return { argv: ['gh', 'api', `repos/${repo}/contents/${at}?ref=${ref}`, '-H', 'Accept: application/vnd.github.raw'] }
}

export function fileText(out: string): string {
  return out.length > FILE_MAX ? `${out.slice(0, FILE_MAX)}\n\n[truncated at ${FILE_MAX} characters]` : out
}
