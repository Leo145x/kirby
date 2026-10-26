// The install call's rows in the transcript, one short line each. The call's input repeats the
// dialog's wording and the result is written for the model; ctrl+o still shows both in full.

type Input = Record<string, unknown>

const str = (v: unknown) => (typeof v === 'string' ? v : '')

export function callLine(input: unknown): string {
  const i = (input && typeof input === 'object' ? input : {}) as Input
  const kind = str(i.kind)
  const args = Array.isArray(i.mcp_args) ? i.mcp_args : []
  const name = kind === 'skill' ? str(i.folder).split('/').pop() : kind === 'plugin' ? str(i.plugin) : str(args[0])
  const what = [kind, name].filter(Boolean).join(' ')
  return `kirby install ${str(i.repo)}${what ? ` (${what})` : ''}`
}

// The text the tool returned, however the engine stored it.
export function textOf(output: unknown): string {
  if (typeof output === 'string') return output
  if (Array.isArray(output)) return output.map(textOf).join('\n')
  if (output && typeof output === 'object') {
    const o = output as Input
    if (typeof o.text === 'string') return o.text
    if ('content' in o) return textOf(o.content)
    if ('result' in o) return textOf(o.result)
  }
  return ''
}

export function resultLine(output: unknown): string {
  const lines = textOf(output).split('\n')
  const first = lines[0] ?? ''
  const installed = first.match(/^installed \(scope \w+\)/)
  if (installed) {
    // A skill's second line ends with where it went: "… -> <path> (<n> files)".
    const to = lines.find(l => /^installed \S+ -> /.test(l))?.replace(/^installed \S+ /, ' ')
    return installed[0] + (to ?? '')
  }
  const failed = first.match(/^install failed \(scope \w+\)/)
  if (failed) return failed[0]
  // "not installed: <what the user chose>. <what the model does next>": keep the first sentence.
  if (first.startsWith('not installed: ')) return first.replace(/^(.*?\.)\s.*$/, '$1')
  return first
}
