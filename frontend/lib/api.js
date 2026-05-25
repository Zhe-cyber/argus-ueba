/**
 * api.js — typed fetch wrappers for the UEBA FastAPI backend.
 *
 * All functions throw on non-OK HTTP responses so callers can
 * catch errors uniformly.  Import individual functions as needed:
 *
 *   import { fetchUsers, fetchStats } from '@/lib/api'
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ---------------------------------------------------------------------------
// Internal helper
// ---------------------------------------------------------------------------

/**
 * Thin fetch wrapper that throws a descriptive Error on non-2xx responses.
 *
 * @param {string} path      — path relative to API_URL, must start with /
 * @param {RequestInit} [options] — passed straight to fetch()
 * @returns {Promise<any>}   — parsed JSON body
 */
async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })

  if (!res.ok) {
    let message = `API error ${res.status}`
    try {
      const body = await res.json()
      message = body?.detail ?? JSON.stringify(body) ?? message
    } catch {
      // ignore JSON parse failures — keep the status-code message
    }
    throw new Error(message)
  }

  return res.json()
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/**
 * Fetch a paginated list of users, optionally filtered by risk level.
 *
 * @param {string|null}  risk   — 'High' | 'Medium' | 'Low' | null (all)
 * @param {number}       limit  — max results (default 100)
 * @param {number}       offset — records to skip for pagination (default 0)
 * @returns {Promise<UserSummary[]>}
 */
export async function fetchUsers(risk = null, limit = 100, offset = 0) {
  const params = new URLSearchParams()
  if (risk) params.set('risk', risk)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return apiFetch(`/users?${params}`)
}

/**
 * Fetch full detail for a single user (includes score breakdown + top-5 SHAP).
 *
 * @param {string} id — user identifier, e.g. 'ACM2278'
 * @returns {Promise<UserDetail>}
 */
export async function fetchUser(id) {
  return apiFetch(`/users/${encodeURIComponent(id)}`)
}

/**
 * Fetch SHAP feature breakdown for a user (top 10 features + reason string).
 *
 * @param {string} id — user identifier
 * @returns {Promise<UserShap>}
 */
export async function fetchUserShap(id) {
  return apiFetch(`/users/${encodeURIComponent(id)}/shap`)
}

/**
 * Fetch dataset-level summary statistics for the dashboard header.
 *
 * @returns {Promise<Stats>}
 */
export async function fetchStats() {
  return apiFetch('/stats')
}

/**
 * Submit a raw log event for normalisation and return the unified 8-field schema.
 * This is the live demo endpoint.
 *
 * @param {Object} event   — raw log event dict (CloudTrail record, Azure AD entry, etc.)
 * @param {string} source  — log source identifier:
 *                           'aws_cloudtrail' | 'azure_ad' | 'cert_logon' |
 *                           'cert_file' | 'cert_device' | 'cert_email' | 'cert_http'
 * @returns {Promise<NormalizedEvent>}
 */
export async function ingestLog(event, source) {
  return apiFetch('/ingest', {
    method: 'POST',
    body: JSON.stringify({ event, source }),
  })
}

// ---------------------------------------------------------------------------
// Investigation endpoints
// ---------------------------------------------------------------------------

/**
 * Fetch the investigation record for a user (null-safe — returns null on 404).
 * @param {string} id
 * @returns {Promise<InvestigationRecord|null>}
 */
export async function fetchInvestigation(id) {
  try {
    return await apiFetch(`/users/${encodeURIComponent(id)}/investigation`)
  } catch (err) {
    if (err.message?.includes('404') || err.message?.toLowerCase().includes('no investigation')) {
      return null
    }
    throw err
  }
}

/**
 * Create or update an investigation record.
 * @param {string} id
 * @param {{ status: string, analyst: string, notes: string }} body
 * @returns {Promise<InvestigationRecord>}
 */
export async function saveInvestigation(id, body) {
  return apiFetch(`/users/${encodeURIComponent(id)}/investigation`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

/**
 * Delete an investigation record.
 * @param {string} id
 * @returns {Promise<void>}
 */
export async function deleteInvestigation(id) {
  return apiFetch(`/users/${encodeURIComponent(id)}/investigation`, {
    method: 'DELETE',
  })
}

/**
 * List all investigations, optionally filtered by status.
 * @param {string|null} status
 * @returns {Promise<InvestigationRecord[]>}
 */
export async function fetchInvestigations(status = null) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  return apiFetch(`/investigations?${params}`)
}

/**
 * Bulk-import all High-risk users into the queue as Pending.
 * @returns {Promise<{ created: number, skipped: number, total_high_risk: number }>}
 */
export async function bulkImportHighRisk() {
  return apiFetch('/investigations/bulk', { method: 'POST' })
}

/**
 * Generate (or regenerate) an AI investigation suggestion for a user.
 * @param {string} id
 * @returns {Promise<{ user_id: string, suggestion: string }>}
 */
export async function getAiSuggestion(id) {
  return apiFetch(`/users/${encodeURIComponent(id)}/investigation/suggest`, {
    method: 'POST',
  })
}

/**
 * Fetch the live event feed for a user (events ingested via /ingest).
 * @param {string} id
 * @param {number} [limit=20]
 * @returns {Promise<LiveEvent[]>}
 */
export async function fetchUserEvents(id, limit = 20) {
  return apiFetch(`/users/${encodeURIComponent(id)}/events?limit=${limit}`)
}
