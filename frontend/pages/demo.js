import { useState, useCallback } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import { ingestLog } from '@/lib/api'

// ---------------------------------------------------------------------------
// Sample events — cover all major source types
// ---------------------------------------------------------------------------

const SAMPLES = {
  aws_cloudtrail: {
    label: 'AWS CloudTrail',
    icon: '☁️',
    description: 'S3 GetObject',
    source: 'aws_cloudtrail',
    event: {
      eventVersion: '1.08',
      userIdentity: { type: 'IAMUser', userName: 'alice', principalId: 'AIDA1234', arn: 'arn:aws:iam::123:user/alice', accountId: '123456789012' },
      eventTime: '2024-03-15T10:23:45Z',
      eventSource: 's3.amazonaws.com',
      eventName: 'GetObject',
      awsRegion: 'ap-southeast-1',
      sourceIPAddress: '203.0.113.42',
      userAgent: 'aws-cli/2.13.0',
      requestParameters: { bucketName: 'prod-data-bucket', key: 'exports/salary_2024.csv' },
      responseElements: null, eventID: 'a1b2c3d4', errorCode: null, errorMessage: null,
    },
  },
  azure_ad: {
    label: 'Azure AD',
    icon: '🔷',
    description: 'Sign-in event',
    source: 'azure_ad',
    event: {
      id: 'b3d4e5f6', createdDateTime: '2024-03-15T02:11:22Z',
      userDisplayName: 'Bob Smith', userPrincipalName: 'bob@contoso.com',
      appDisplayName: 'Microsoft SharePoint', ipAddress: '198.51.100.17',
      clientAppUsed: 'Browser', conditionalAccessStatus: 'success',
      resourceDisplayName: 'Microsoft SharePoint',
      status: { errorCode: 0, failureReason: null },
      deviceDetail: { operatingSystem: 'Windows 10', browser: 'Chrome 122' },
      location: { city: 'Kuala Lumpur', countryOrRegion: 'MY' },
    },
  },
  cert_logon: {
    label: 'CERT Logon',
    icon: '🖥️',
    description: 'After-hours logon',
    source: 'cert_logon',
    event: { id: 'LOG-ACM2278-001', date: '2024-03-15 22:30:12', user: 'ACM2278', pc: 'PC-3482', activity: 'Logon' },
  },
  cert_email: {
    label: 'CERT Email',
    icon: '📧',
    description: 'External email + attachments',
    source: 'cert_email',
    event: {
      id: 'EML-ACM2278-042', date: '2024-03-15 22:45:00', user: 'ACM2278', pc: 'PC-3482',
      to: 'recruiter@external.com', cc: '', bcc: 'personal@gmail.com',
      from: 'ACM2278@company.com', activity: 'Send',
      size: 2048000, attachments: 3, content: 'resume and portfolio',
    },
  },
  cert_http: {
    label: 'CERT HTTP',
    icon: '🌐',
    description: 'Job-site visit',
    source: 'cert_http',
    event: {
      id: 'HTTP-ACM2278-123', date: '2024-03-15 09:15:00', user: 'ACM2278', pc: 'PC-3482',
      url: 'https://www.linkedin.com/jobs/search?keywords=security+engineer',
      activity: 'WWW Visit', content: '',
    },
  },
  cert_file: {
    label: 'CERT File',
    icon: '💾',
    description: 'USB archive transfer',
    source: 'cert_file',
    event: {
      id: 'FILE-ACM2278-077', date: '2024-03-15 22:55:00', user: 'ACM2278', pc: 'PC-3482',
      filename: '\\Device\\HarddiskVolume3\\backup_2024.zip',
      activity: 'write', to_removable_media: true, from_removable_media: false,
    },
  },
  cert_device: {
    label: 'CERT Device',
    icon: '🔌',
    description: 'USB device connected',
    source: 'cert_device',
    event: {
      id: 'DEV-ACM2278-009', date: '2024-03-15 22:53:00', user: 'ACM2278', pc: 'PC-3482',
      activity: 'Connect',
    },
  },
  cloudflare_access: {
    label: 'Cloudflare Access',
    icon: '🔶',
    description: 'Login from new country',
    source: 'cloudflare_access',
    event: {
      action: 'login',
      allowed: true,
      app_domain: 'internal-dashboard.company.com',
      app_uid: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      created_at: '2024-03-15T02:34:00Z',
      user_email: 'alice@company.com',
      user_id: 'cf-user-uuid-1234',
      ip_address: '203.0.113.45',
      country: 'CN',
      ray_id: 'cf-ray-7a8b9c0d1e2f',
    },
  },
  github_events: {
    label: 'GitHub Events',
    icon: '🐙',
    description: 'Bulk code push — off hours',
    source: 'github_events',
    event: {
      id: '34823485756',
      type: 'PushEvent',
      actor: {
        id: 9182736,
        login: 'alice',
        display_login: 'alice',
      },
      repo: {
        id: 556677,
        name: 'company/internal-secrets-api',
        url: 'https://api.github.com/repos/company/internal-secrets-api',
      },
      payload: {
        push_id: 18273645,
        size: 47,
        ref: 'refs/heads/main',
        head: 'a1b2c3d4e5f6a1b2c3d4',
      },
      public: false,
      created_at: '2024-03-15T02:47:00Z',
    },
  },
}

const SOURCE_OPTIONS = [
  { value: 'aws_cloudtrail',    label: 'AWS CloudTrail'      },
  { value: 'azure_ad',          label: 'Azure AD'            },
  { value: 'cloudflare_access', label: 'Cloudflare Access'   },
  { value: 'github_events',     label: 'GitHub Events'       },
  { value: 'cert_logon',        label: 'CERT Logon'          },
  { value: 'cert_file',         label: 'CERT File'           },
  { value: 'cert_device',       label: 'CERT Device'         },
  { value: 'cert_email',        label: 'CERT Email'          },
  { value: 'cert_http',         label: 'CERT HTTP'           },
]

const SCHEMA_FIELDS = [
  { key: 'timestamp',  desc: 'ISO 8601 event time'      },
  { key: 'user',       desc: 'User identifier'           },
  { key: 'source',     desc: 'Normalised log source'     },
  { key: 'action',     desc: 'Human-readable action'     },
  { key: 'resource',   desc: 'Accessed resource'         },
  { key: 'ip_address', desc: 'Source IP or empty string' },
  { key: 'metadata',   desc: 'Source-specific extras'    },
  { key: 'raw',        desc: 'Original unmodified event' },
]

const FEAT_LABELS = {
  login_count:         'Login count',
  after_hours_count:   'After-hours sessions',
  files_accessed:      'Files accessed',
  n_archive_files:     'Archive files (.zip …)',
  n_exe_files:         'Executable files (.exe)',
  n_afterhours_file:   'After-hours file ops',
  usb_events:          'USB events',
  has_usb:             'USB device seen',
  n_afterhours_usb:    'After-hours USB',
  usb_and_file:        'USB + file combined',
  email_count:         'Emails sent',
  external_emails:     'External emails',
  n_bcc_email:         'BCC emails',
  total_attachments:   'Attachments',
  n_afterhours_email:  'After-hours emails',
  http_count:          'HTTP requests',
  n_job_site:          'Job-site visits',
  n_cloud_storage:     'Cloud storage visits',
  suspicious_http:     'Suspicious URLs',
  n_afterhours_http:   'After-hours HTTP',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function prettyJson(obj) { return JSON.stringify(obj, null, 2) }

function tryParseJson(str) {
  try { return { ok: true, value: JSON.parse(str) } }
  catch (e) { return { ok: false, error: e.message } }
}

function scoreColor(s) {
  if (s >= 0.5) return 'text-red-600'
  if (s >= 0.2) return 'text-amber-600'
  return 'text-green-600'
}

function scoreBg(s) {
  if (s >= 0.5) return 'border-red-200 bg-red-50'
  if (s >= 0.2) return 'border-amber-200 bg-amber-50'
  return 'border-green-200 bg-green-50'
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SampleButton({ sample, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={[
        'flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-all',
        active
          ? 'border-indigo-300 bg-indigo-50 text-indigo-700 ring-1 ring-indigo-300'
          : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-200 hover:bg-indigo-50/50',
      ].join(' ')}
    >
      <span>{sample.icon}</span>
      <span className="flex flex-col items-start leading-none">
        <span>{sample.label}</span>
        <span className="text-xs font-normal text-slate-400 mt-0.5">{sample.description}</span>
      </span>
    </button>
  )
}

function FieldRow({ fieldKey, value, desc }) {
  const isObject = typeof value === 'object' && value !== null
  return (
    <div className="grid grid-cols-[140px_1fr] gap-2 py-2.5 border-b border-slate-50 last:border-0
                    hover:bg-slate-50/60 px-3 rounded -mx-3 transition-colors group">
      <div>
        <span className="font-mono text-xs font-semibold text-indigo-600">{fieldKey}</span>
        <p className="text-[10px] text-slate-400 mt-0.5 leading-tight hidden group-hover:block">{desc}</p>
      </div>
      <div className="overflow-hidden">
        {isObject ? (
          <pre className="text-xs text-slate-600 bg-slate-50 rounded p-2 overflow-x-auto
                          max-h-32 font-mono leading-relaxed whitespace-pre-wrap break-words">
            {prettyJson(value)}
          </pre>
        ) : (
          <span className={`font-mono text-xs break-all ${value === '' ? 'text-slate-300 italic' : 'text-slate-700'}`}>
            {value === '' ? '(empty)' : String(value)}
          </span>
        )}
      </div>
    </div>
  )
}

function StepBadge({ n, label, done }) {
  return (
    <div className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold
                     border transition-all ${done
                       ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
                       : 'border-slate-200 bg-slate-50 text-slate-400'}`}>
      <span className={`h-5 w-5 rounded-full flex items-center justify-center text-[10px] font-bold
                        ${done ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>
        {done ? '✓' : n}
      </span>
      {label}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DemoPage() {
  const router = useRouter()

  const [activeSample, setActiveSample] = useState('aws_cloudtrail')
  const [source,       setSource]       = useState('aws_cloudtrail')
  const [jsonInput,    setJsonInput]    = useState(prettyJson(SAMPLES.aws_cloudtrail.event))
  const [parseError,   setParseError]   = useState(null)

  const [result,   setResult]   = useState(null)   // PipelineResult
  const [apiError, setApiError] = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [elapsed,  setElapsed]  = useState(null)

  const loadSample = useCallback((key) => {
    const s = SAMPLES[key]
    setActiveSample(key); setSource(s.source)
    setJsonInput(prettyJson(s.event)); setParseError(null)
    setResult(null); setApiError(null); setElapsed(null)
  }, [])

  const handleJsonChange = (e) => {
    setJsonInput(e.target.value); setParseError(null); setActiveSample(null)
  }

  const handleNormalize = async () => {
    const parsed = tryParseJson(jsonInput)
    if (!parsed.ok) { setParseError(`Invalid JSON: ${parsed.error}`); return }
    setLoading(true); setResult(null); setApiError(null); setElapsed(null)
    const t0 = performance.now()
    try {
      const data = await ingestLog(parsed.value, source)
      setResult(data)
      setElapsed(Math.round(performance.now() - t0))
    } catch (err) {
      setApiError(err.message ?? 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const hasFeatures = result && Object.keys(result.extracted_features ?? {}).length > 0

  return (
    <>
      <Head>
        <title>Demo Lab — Argus</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

        <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-5">

          {/* Intro + pipeline steps */}
          <div>
            <h2 className="text-lg font-bold text-slate-800">Multi-Cloud Log Ingestion Pipeline</h2>
            <p className="mt-1 text-sm text-slate-500 max-w-2xl">
              Paste any raw log, choose the source, and click <strong className="text-slate-700">Run Pipeline</strong>.
              Each event is normalized, features are extracted, the event is persisted, and the
              user&apos;s live risk score is updated — all in one API call.
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              <StepBadge n="1" label="Normalize"         done={!!result} />
              <StepBadge n="2" label="Extract Features"  done={!!result} />
              <StepBadge n="3" label="Store Event"       done={!!result} />
              <StepBadge n="4" label="Live Score Update" done={!!result} />
              <StepBadge n="5" label="Rarity Signals"    done={!!result && !!result.rarity_flags} />
            </div>
          </div>

          {/* Sample buttons */}
          <div className="flex flex-wrap gap-2">
            <span className="self-center text-xs font-semibold uppercase tracking-wider text-slate-400 mr-1">
              Load sample:
            </span>
            {Object.entries(SAMPLES).map(([key, s]) => (
              <SampleButton key={key} sample={s} active={activeSample === key} onClick={() => loadSample(key)} />
            ))}
          </div>

          {/* Two-panel: input + output */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">

            {/* LEFT: Input */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
              <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-700">Raw Log Event</h3>
                <span className="text-xs text-slate-400 font-mono">Stage 1 input</span>
              </div>
              <div className="px-5 py-4 space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5">Log Source</label>
                  <select value={source} onChange={e => { setSource(e.target.value); setActiveSample(null) }}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2
                               text-sm text-slate-700 font-medium focus:outline-none
                               focus:ring-2 focus:ring-indigo-400 focus:border-transparent">
                    {SOURCE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5">Event Payload</label>
                  <textarea value={jsonInput} onChange={handleJsonChange} spellCheck={false} rows={18}
                    className={`w-full rounded-lg border px-3 py-2.5 font-mono text-xs text-slate-700
                                leading-relaxed resize-none focus:outline-none focus:ring-2
                                focus:ring-indigo-400 focus:border-transparent bg-slate-50
                                ${parseError ? 'border-red-300' : 'border-slate-200'}`}
                    placeholder="Paste raw log event JSON here…" />
                  {parseError && (
                    <p className="mt-1 text-xs text-red-600">{parseError}</p>
                  )}
                </div>
                <button onClick={handleNormalize} disabled={loading}
                  className={`w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white
                              transition-all duration-150 flex items-center justify-center gap-2
                              ${loading ? 'bg-indigo-400 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 active:scale-[0.98]'}`}>
                  {loading ? (
                    <><svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                    </svg>Running pipeline…</>
                  ) : (
                    <><svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" clipRule="evenodd"
                        d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75
                           0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5
                           0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75
                           0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0
                           002.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75
                           0 000 1.5h4.243a.75.75 0 00.53-.219z" />
                    </svg>Run Pipeline</>
                  )}
                </button>
              </div>
            </div>

            {/* RIGHT: Output stages */}
            <div className="space-y-4">

              {/* Idle */}
              {!result && !apiError && !loading && (
                <div className="rounded-xl border border-dashed border-slate-200 bg-white
                                flex flex-col items-center justify-center py-20 gap-3 text-center text-slate-300">
                  <svg className="h-12 w-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                    <path strokeLinecap="round" strokeLinejoin="round"
                      d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0
                         002-2v-4M9 21H5a2 2 0 01-2-2v-4m0 0h18" />
                  </svg>
                  <p className="text-sm font-medium">Select a sample and click <strong>Run Pipeline</strong></p>
                  <p className="text-xs">All 4 pipeline stages will run and appear here</p>
                </div>
              )}

              {loading && (
                <div className="rounded-xl border border-slate-200 bg-white
                                flex flex-col items-center justify-center py-20 gap-3 text-slate-400">
                  <svg className="animate-spin h-7 w-7" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                  </svg>
                  <span className="text-sm font-medium">Running all 4 stages…</span>
                </div>
              )}

              {apiError && (
                <div className="rounded-xl border border-red-200 bg-red-50 p-5">
                  <p className="text-sm font-semibold text-red-700">Pipeline failed</p>
                  <p className="text-sm text-red-600 mt-1">{apiError}</p>
                </div>
              )}

              {result && !apiError && (
                <>
                  {/* Stage 1: Normalize */}
                  <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                    <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="h-5 w-5 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center">1</span>
                        <h4 className="text-sm font-semibold text-slate-700">Normalized Schema</h4>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="inline-flex items-center gap-1 rounded-full bg-green-100 text-green-700 ring-1 ring-green-300 px-2 py-0.5 text-xs font-semibold">
                          <span className="h-1.5 w-1.5 rounded-full bg-green-500"/>Normalized
                        </span>
                        {elapsed !== null && <span className="text-xs text-slate-400 font-mono">{elapsed} ms</span>}
                      </div>
                    </div>
                    <div className="px-5 py-4">
                      {SCHEMA_FIELDS.map(({ key, desc }) => (
                        <FieldRow key={key} fieldKey={key} value={result[key]} desc={desc} />
                      ))}
                    </div>
                  </div>

                  {/* Stage 2: Extracted Features */}
                  <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                    <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-2">
                      <span className="h-5 w-5 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center">2</span>
                      <div>
                        <h4 className="text-sm font-semibold text-slate-700">Extracted Features</h4>
                        <p className="text-xs text-slate-400">Behavioral feature increments this event contributes</p>
                      </div>
                    </div>
                    <div className="px-5 py-4">
                      {hasFeatures ? (
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(result.extracted_features).map(([feat, val]) => (
                            <div key={feat}
                              className="flex items-center gap-1.5 rounded-lg border border-indigo-100
                                         bg-indigo-50 px-3 py-1.5 text-xs">
                              <span className="font-medium text-indigo-700">
                                {FEAT_LABELS[feat] ?? feat}
                              </span>
                              <span className="rounded-full bg-indigo-600 text-white text-[10px] font-bold px-1.5 py-0.5">
                                +{val}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-slate-400 text-center py-4">
                          No behavioral features extracted for this source type.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Stage 3 + 4: Store + Live Score */}
                  <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                    <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-2">
                      <span className="h-5 w-5 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center">3</span>
                      <span className="h-5 w-5 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center ml-0.5">4</span>
                      <div className="ml-1">
                        <h4 className="text-sm font-semibold text-slate-700">Stored &amp; Live Score Updated</h4>
                        <p className="text-xs text-slate-400">Event persisted · rolling 24-hour risk score recomputed</p>
                      </div>
                    </div>
                    <div className="px-5 py-4 space-y-4">

                      {/* Score + counts row */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className={`rounded-lg border px-4 py-3 text-center ${scoreBg(result.live_score)}`}>
                          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Rule Score</p>
                          <p className={`text-2xl font-bold tabular-nums ${scoreColor(result.live_score)}`}>
                            {result.live_score.toFixed(3)}
                          </p>
                          <p className="text-[10px] text-slate-400 mt-0.5">24 h window</p>
                        </div>
                        {result.ae_live_score != null ? (
                          <div className={`rounded-lg border px-4 py-3 text-center ${scoreBg(result.ae_live_score)}`}>
                            <p className="text-xs font-semibold text-indigo-500 uppercase tracking-wider mb-1">AE Score ★</p>
                            <p className={`text-2xl font-bold tabular-nums ${scoreColor(result.ae_live_score)}`}>
                              {result.ae_live_score.toFixed(3)}
                            </p>
                            <p className="text-[10px] text-slate-400 mt-0.5">trained model</p>
                          </div>
                        ) : (
                          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-center">
                            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">AE Score ★</p>
                            <p className="text-sm text-slate-400 mt-1">model not loaded</p>
                            <p className="text-[10px] text-slate-300 mt-0.5">add autoencoder_v4.pt</p>
                          </div>
                        )}
                        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-center">
                          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Events (24 h)</p>
                          <p className="text-2xl font-bold text-slate-700 tabular-nums">{result.event_count_24h}</p>
                          <p className="text-[10px] text-slate-400 mt-0.5">recent window</p>
                        </div>
                        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-center">
                          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Total Stored</p>
                          <p className="text-2xl font-bold text-slate-700 tabular-nums">{result.total_events}</p>
                          <p className="text-[10px] text-slate-400 mt-0.5">all-time</p>
                        </div>
                      </div>

                      {/* Cumulative features */}
                      {Object.keys(result.cumulative_features ?? {}).length > 0 && (
                        <div>
                          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                            Accumulated (24 h window)
                          </p>
                          <div className="flex flex-wrap gap-1.5">
                            {Object.entries(result.cumulative_features).map(([feat, val]) => (
                              <span key={feat}
                                className="inline-flex items-center gap-1 rounded-md bg-slate-100
                                           text-slate-600 text-xs px-2 py-1 font-mono">
                                {FEAT_LABELS[feat] ?? feat}
                                <span className="font-bold text-slate-800">{val}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Link to user profile */}
                      {result.user && (
                        <div className="flex items-center justify-between pt-1 border-t border-slate-100">
                          <p className="text-xs text-slate-500">
                            Event attributed to user&nbsp;
                            <span className="font-mono font-semibold text-slate-700">{result.user}</span>
                          </p>
                          <button
                            onClick={() => router.push(`/users/${encodeURIComponent(result.user)}`)}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600
                                       px-3 py-1.5 text-xs font-semibold text-white
                                       hover:bg-indigo-700 transition-colors">
                            View profile
                            <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" clipRule="evenodd"
                                d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75
                                   0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5
                                   5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75
                                   0 013 10z" />
                            </svg>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Stage 5: Rarity Signals */}
                  {result.rarity_flags && (
                    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                      <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-2">
                        <span className="h-5 w-5 rounded-full bg-indigo-600 text-white text-[10px] font-bold flex items-center justify-center">5</span>
                        <div className="flex-1">
                          <h4 className="text-sm font-semibold text-slate-700">Rarity Signals</h4>
                          <p className="text-xs text-slate-400">Source-agnostic anomaly flags — fire on unusual patterns regardless of log type</p>
                        </div>
                        {/* Rarity score badge */}
                        <div className={`rounded-lg border px-3 py-1.5 text-center min-w-[72px] ${
                          result.rarity_score >= 0.6 ? 'border-red-200 bg-red-50' :
                          result.rarity_score >= 0.4 ? 'border-amber-200 bg-amber-50' :
                          'border-green-200 bg-green-50'
                        }`}>
                          <p className={`text-lg font-bold tabular-nums ${
                            result.rarity_score >= 0.6 ? 'text-red-600' :
                            result.rarity_score >= 0.4 ? 'text-amber-600' :
                            'text-green-600'
                          }`}>
                            {Math.round(result.rarity_score * 100)}%
                          </p>
                          <p className="text-[10px] text-slate-400 leading-tight">rarity</p>
                        </div>
                      </div>
                      <div className="px-5 py-4 space-y-3">
                        {/* Flag pills */}
                        <div className="flex flex-wrap gap-2">
                          {[
                            { key: 'first_time_action',  label: 'First-Time Action',  desc: 'Action never seen for this user before' },
                            { key: 'new_ip',             label: 'New IP',             desc: 'Source IP never seen for this user' },
                            { key: 'off_hours',          label: 'Off Hours',          desc: 'Outside Mon–Fri 07:00–19:00 UTC' },
                            { key: 'high_volume',        label: 'High Volume',        desc: `More than 50 events in last hour` },
                            { key: 'sensitive_resource', label: 'Sensitive Resource', desc: 'Resource matches high-risk pattern (IAM, secrets, admin…)' },
                            { key: 'geo_rarity',         label: 'New Country',        desc: 'Country code never seen for this user (Cloudflare Access)' },
                          ].map(({ key, label, desc }) => {
                            const fired = result.rarity_flags[key] === true
                            return (
                              <div key={key} title={desc}
                                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold cursor-default select-none transition-all ${
                                  fired
                                    ? 'border-red-300 bg-red-50 text-red-700 ring-1 ring-red-300'
                                    : 'border-slate-200 bg-slate-50 text-slate-400'
                                }`}>
                                <span className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${fired ? 'bg-red-500' : 'bg-slate-300'}`} />
                                {label}
                                {fired && <span className="ml-0.5 text-[10px] font-bold text-red-600">!</span>}
                              </div>
                            )
                          })}
                        </div>

                        {/* Score bar */}
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs text-slate-500 font-medium">
                              {Object.values(result.rarity_flags).filter(Boolean).length} of {Object.keys(result.rarity_flags).length} signals fired
                            </span>
                            <span className={`text-xs font-semibold ${
                              result.rarity_score >= 0.6 ? 'text-red-600' :
                              result.rarity_score >= 0.4 ? 'text-amber-600' :
                              'text-green-600'
                            }`}>
                              {result.rarity_score >= 0.6 ? 'High rarity' :
                               result.rarity_score >= 0.4 ? 'Medium rarity' : 'Low rarity'}
                            </span>
                          </div>
                          <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${
                                result.rarity_score >= 0.6 ? 'bg-red-500' :
                                result.rarity_score >= 0.4 ? 'bg-amber-500' :
                                'bg-green-500'
                              }`}
                              style={{ width: `${Math.round(result.rarity_score * 100)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                </>
              )}
            </div>
          </div>

          {/* Schema reference */}
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate-100">
              <h3 className="text-sm font-semibold text-slate-700">Unified Schema Reference</h3>
              <p className="text-xs text-slate-400 mt-0.5">Every log source maps to these 8 fields regardless of origin</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    <th className="px-5 py-2.5 text-left font-semibold text-slate-500 uppercase tracking-wider">Field</th>
                    <th className="px-5 py-2.5 text-left font-semibold text-slate-500 uppercase tracking-wider">Type</th>
                    <th className="px-5 py-2.5 text-left font-semibold text-slate-500 uppercase tracking-wider">Description</th>
                    <th className="px-5 py-2.5 text-left font-semibold text-slate-500 uppercase tracking-wider hidden sm:table-cell">AWS CloudTrail</th>
                    <th className="px-5 py-2.5 text-left font-semibold text-slate-500 uppercase tracking-wider hidden sm:table-cell">Azure AD</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['timestamp',  'str',  'ISO 8601 event time',           'eventTime',           'createdDateTime'],
                    ['user',       'str',  'User identifier',                'userIdentity.userName','userPrincipalName'],
                    ['source',     'str',  'Normalised log source constant', 'aws_cloudtrail',      'azure_ad'],
                    ['action',     'str',  'Human-readable action',         'eventName',           'appDisplayName'],
                    ['resource',   'str',  'Accessed resource',             'requestParameters.*', 'resourceDisplayName'],
                    ['ip_address', 'str',  'Source IP or ""',                'sourceIPAddress',     'ipAddress'],
                    ['metadata',   'dict', 'Source-specific extras',        'eventID, region, …',  'correlationId, …'],
                    ['raw',        'dict', 'Original event, untouched',     '{ … }',               '{ … }'],
                  ].map(([field, type, desc, aws, azure], i) => (
                    <tr key={field} className={`border-b border-slate-50 ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'}`}>
                      <td className="px-5 py-2.5 font-mono font-semibold text-indigo-600">{field}</td>
                      <td className="px-5 py-2.5 font-mono text-slate-400">{type}</td>
                      <td className="px-5 py-2.5 text-slate-600">{desc}</td>
                      <td className="px-5 py-2.5 font-mono text-slate-400 hidden sm:table-cell">{aws}</td>
                      <td className="px-5 py-2.5 font-mono text-slate-400 hidden sm:table-cell">{azure}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

        </main>
    </>
  )
}
