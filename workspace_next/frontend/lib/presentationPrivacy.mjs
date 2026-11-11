// Visual masking only. Stored evidence, API payloads and identity keys stay intact.
export function maskText(value) {
  if (typeof value !== 'string') return value
  return value.replace(/acct_[0-9a-f]{64}/g, match => 'Account ' + match.slice(5, 13))
    .replace(/\b(?:AROA|AIDA)[A-Z0-9]{12,}(?::[^\s,;"'<>]+)?/g, '[AWS principal hidden]')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[email hidden]')
    .replace(/\b[0-9]{12}\b/g, '<account>')
    .replace(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g, '[IP hidden]')
}
