// Display-only: retain exact identity/provenance in the evidence snapshot.
export function redactDiagnostic(value) {
  if (Array.isArray(value)) return value.map(redactDiagnostic)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key, ['scope', 'source_account_id', 'account_id'].includes(key) ? '[provider account hidden]' : redactDiagnostic(item)
  ]))
  if (typeof value === 'number' && /^\d{12}$/.test(String(value))) return '[account ID hidden]'
  return typeof value === 'string' ? value.replace(/\b\d{12}\b/g, '[account ID hidden]') : value
}
