export type Status = 'accepted' | 'ask' | 'declined' | 'waitlisted'
export type Verdict = 'accept' | 'ask' | 'decline'
export type ReasonCategory = 'skill_gap' | 'minor_issue' | 'capacity' | 'scam_abuse' | 'rules_mismatch'
export type EvidenceStatus = 'live' | 'simulated' | 'not_provided' | 'not_found' | 'unavailable'

export interface CategoryQuota { slug: string; name: string; quota: number; bypass_quota: boolean; used: number; remaining: number; waitlisted: number }
export interface Rule { id?: string; text: string }
export interface Community { id: string; slug: string; name: string; description?: string; rules: Rule[]; reconsider_cooldown_days: number; categories: CategoryQuota[] }
export interface CommunityRef { id: string; slug: string; name: string }

export interface ApplicantSummary {
  id: string; name: string; category: string; status: Status; final_score: number | null; confidence: number | null
  top_reason: string | null; decision_source: 'auto' | 'lead'; created_at: string; is_seed: boolean; reconsidered: boolean
  attended?: number; no_show?: number; liked?: boolean
}
export interface RuleCheck { rule_id: string; rule: string; score: number; verdict: 'pass' | 'unclear' | 'fail'; reason: string; quote: string | null; source: 'llm' | 'heuristic' }
export interface BlockMatch { entry_id: string; identifier_type: string; status: string; reporting_community: string; evidence: string; links: string[]; reported_at: string }
export interface Recommendation {
  verdict: Verdict; confidence: number; final_score: number; reasons: string[]; route_rule: string; disagreement: boolean
  llm: { status: 'live' | 'cached' | 'unavailable'; provider: string | null; model: string | null; error: string | null }
  rule_score: number; rule_checks: RuleCheck[]
  history: { available: boolean; p_accept: number | null; n_training: number; top_features: { feature: string; value: number; contribution: number }[] }
  evidence: {
    github: { status: EvidenceStatus; login?: string; account_age_days?: number; public_repos?: number; followers?: number; recent_push_days?: number | null; url?: string }
    devpost: { status: EvidenceStatus; projects?: number; wins?: number; sample?: { name: string; url: string }[] }
    stopforumspam: { status: EvidenceStatus; email_appears?: boolean; username_appears?: boolean; confidence?: number }
    blocklist: { hit: boolean; matches: BlockMatch[] }
  }
  quota: { category: string; quota: number; used: number; remaining: number; bypass_quota: boolean; outcome: 'seat' | 'waitlisted' | null; waitlist_rank: number | null }
}
export type NoteFlag = 'great_volunteer' | 'no_show' | 'disruptive' | 'watch' | 'vip'
export interface AttendeeNote { id: string; flag: NoteFlag | null; note: string; visibility: 'private' | 'shared'; author: string; community_name: string; created_at: string }
export interface Extras {
  attendance: { attended: number; no_show: number; events: { event_name: string; event_date: string; status: 'attended' | 'no_show' }[] }
  ban: { id: string; reason: string; created_at: string; label: string | null } | null
  liked?: boolean
  own_notes: AttendeeNote[]; shared_notes: AttendeeNote[]; shared_flags: { flag: NoteFlag; community_name: string }[]
}
export interface PastEvent { event_name: string; event_date: string; attended: number; no_show: number; attendees: { applicant_id: string; name: string; status: 'attended' | 'no_show'; liked: boolean }[] }
export interface CommunityBan { id: string; identifier_type: string; label: string | null; reason: string; created_by: string; created_at: string }
export interface StatusView {
  name: string; community_name: string; community_slug: string; category: string; decision: Status
  waitlist_position: number | null; lead_question: string | null; applicant_reply: string | null; applicant_reply_at: string | null
  message: string; invite_url: string | null; appeal_url: string | null
}
export interface ApplicantDetail extends ApplicantSummary {
  status_token?: string; lead_question?: string | null; applicant_reply?: string | null; applicant_reply_at?: string | null
  extras?: Extras
  community_slug: string; email: string; phone_masked: string | null; github: string | null; devpost: string | null; chat_handle: string | null
  what_build: string; decided_at: string | null; decline_reason: ReasonCategory | null
  recommendation: Recommendation
  reconsideration: { eligible: boolean; reconsider_after: string | null; previous: { declined_at: string; reason_category: ReasonCategory } | null; note: string | null }
  decisions: { verdict: string; reason_category: string | null; note: string | null; source: string; created_at: string }[]
}
export interface ModelInfo { available: boolean; n_decisions: number; n_accept: number; n_decline: number; trained_at: string | null; coefficients: { feature: string; weight: number }[] }
export interface Notification { id: string; applicant_id: string | null; applicant_name: string | null; kind: string; message: string; read: boolean; created_at: string }
export interface Appeal { id: string; contact: string; message: string; status: 'open' | 'upheld' | 'rejected'; created_at: string }
export interface BlockEntry {
  id: string; identifier_type: string; identifier_hash_prefix: string; evidence: string; links: string[]
  reporting_community: { slug: string; name: string }; is_own: boolean; status: 'pending' | 'confirmed' | 'appealed' | 'removed'; created_at: string; appeals: Appeal[]
}
export interface EvalVariant {
  name: string; accuracy: number; accept_precision: number; accept_recall: number; decline_precision: number; decline_recall: number
  false_block_rate: number; ask_rate: number; accuracy_on_decided: number; confusion: Record<string, number>; n: number
  confusion_matrix?: Record<'accept' | 'decline', Record<'accept' | 'ask' | 'decline', number>>
  by_kind?: Record<string, { n: number; accuracy: number; ask_rate: number }>
}
export interface EvalReport {
  generated_at: string; test_set: { n: number; n_accept: number; n_decline: number; n_scam: number; n_edge: number; source: string }
  train_set: { n: number; source: string }; variants: EvalVariant[]; notes: string[]
}
export interface Health { ok: boolean; db: string | boolean; llm: { available: boolean; provider: string | null; model: string | null; label: string; verified: boolean; error: string | null; calls_made: number; max_calls: number }; github_token: boolean }
export interface ApplyIn { name: string; email: string; phone?: string; github?: string; devpost?: string; chat_handle?: string; what_build: string; category: string }

export class ApiError extends Error { status: number; constructor(status: number, msg: string) { super(msg); this.status = status } }

async function req<T>(method: string, path: string, body?: unknown, timeoutMs = 30000): Promise<T> {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), timeoutMs)
  try {
    const r = await fetch(`/api${path}`, {
      method, signal: ctl.signal,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    if (!r.ok) {
      let msg = `${r.status} ${r.statusText}`
      try {
        const j = await r.json()
        if (typeof j.detail === 'string') msg = j.detail
        else if (Array.isArray(j.detail)) msg = j.detail.map((d: { loc?: string[]; msg: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`).join('; ')
      } catch { /* non-JSON error */ }
      throw new ApiError(r.status, msg)
    }
    return (await r.json()) as T
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw new ApiError(0, `Request timed out after ${timeoutMs / 1000}s`)
    if (e instanceof ApiError) throw e
    throw new ApiError(0, 'Cannot reach the Gatekeeper API. Is the backend running on :8000?')
  } finally { clearTimeout(t) }
}

const q = (o: Record<string, string | undefined>) => {
  const s = new URLSearchParams(Object.entries(o).filter(([, v]) => v) as [string, string][]).toString()
  return s ? `?${s}` : ''
}

export const api = {
  health: () => req<Health>('GET', '/health'),
  resetDemo: () => req<{ ok: boolean; applicants: number; queue: number }>('POST', '/demo/reset', undefined, 180000),
  communities: () => req<CommunityRef[]>('GET', '/communities'),
  community: (slug: string) => req<Community>('GET', `/communities/${slug}`),
  saveSettings: (slug: string, body: { rules: Rule[]; categories: Omit<CategoryQuota, 'used' | 'remaining' | 'waitlisted'>[]; reconsider_cooldown_days: number }) =>
    req<Community>('PUT', `/communities/${slug}/settings`, body),
  apply: (slug: string, body: ApplyIn) => req<ApplicantDetail>('POST', `/communities/${slug}/apply`, body, 60000),
  applicants: (slug: string, f: { status?: string; category?: string; q?: string; liked?: string; returning?: string }) => req<ApplicantSummary[]>('GET', `/communities/${slug}/applicants${q(f)}`),
  queue: (slug: string) => req<ApplicantDetail[]>('GET', `/communities/${slug}/queue`),
  applicant: (id: string) => req<ApplicantDetail>('GET', `/applicants/${id}`),
  decide: (id: string, body: { verdict: 'accept' | 'ask_more' | 'decline'; reason_category?: ReasonCategory; note?: string }) =>
    req<{ applicant: ApplicantDetail; model: ModelInfo }>('POST', `/applicants/${id}/decision`, body),
  recheck: (id: string) => req<ApplicantDetail>('POST', `/applicants/${id}/recheck`, undefined, 60000),
  recheckDue: (slug: string) => req<{ checked: number; changed: ApplicantSummary[] }>('POST', `/communities/${slug}/recheck-due`, undefined, 120000),
  notifications: (slug: string) => req<Notification[]>('GET', `/communities/${slug}/notifications`),
  readNotification: (id: string) => req<{ ok: boolean }>('POST', `/notifications/${id}/read`),
  model: (slug: string) => req<ModelInfo>('GET', `/communities/${slug}/model`),
  retrain: (slug: string) => req<ModelInfo>('POST', `/communities/${slug}/model/retrain`),
  blocklist: (slug: string) => req<BlockEntry[]>('GET', `/communities/${slug}/blocklist`),
  report: (slug: string, body: { identifier_type: string; identifier: string; evidence: string; links: string[] }) => req<BlockEntry>('POST', `/communities/${slug}/blocklist`, body),
  confirmEntry: (slug: string, id: string) => req<BlockEntry>('POST', `/communities/${slug}/blocklist/${id}/confirm`),
  removeEntry: (slug: string, id: string) => req<BlockEntry>('POST', `/communities/${slug}/blocklist/${id}/remove`),
  appeal: (body: { identifier_type: string; identifier: string; contact: string; message: string }) => req<{ id: string | null; status: string; matched: boolean }>('POST', '/appeals', body),
  resolveAppeal: (slug: string, id: string, outcome: 'upheld' | 'rejected') => req<BlockEntry>('POST', `/communities/${slug}/appeals/${id}/resolve`, { outcome }),
  bans: (slug: string) => req<CommunityBan[]>('GET', `/communities/${slug}/bans`),
  addBan: (slug: string, body: { identifier_type: string; identifier: string; reason: string }) => req<unknown>('POST', `/communities/${slug}/bans`, body),
  removeBan: (slug: string, id: string) => req<unknown>('DELETE', `/communities/${slug}/bans/${id}`),
  banApplicant: (id: string, reason: string) => req<{ ok: boolean; count: number }>('POST', `/applicants/${id}/ban`, { reason }),
  addNote: (id: string, body: { flag: NoteFlag | null; note: string; visibility: 'private' | 'shared' }) => req<AttendeeNote>('POST', `/applicants/${id}/notes`, body),
  deleteNote: (id: string, noteId: string) => req<unknown>('DELETE', `/applicants/${id}/notes/${noteId}`),
  status: (token: string) => req<StatusView>('GET', `/status/${token}`),
  reply: (token: string, text: string) => req<StatusView>('POST', `/status/${token}/reply`, { text }),
  askApplicant: (id: string, question: string) => req<{ ok: boolean; lead_question: string }>('POST', `/applicants/${id}/question`, { question }),
  like: (id: string) => req<{ liked: boolean }>('POST', `/applicants/${id}/like`),
  unlike: (id: string) => req<{ liked: boolean }>('DELETE', `/applicants/${id}/like`),
  events: (slug: string) => req<PastEvent[]>('GET', `/communities/${slug}/events`),
  evalReport: () => req<EvalReport>('GET', '/eval'),
  runEval: () => req<EvalReport>('POST', '/eval/run', undefined, 180000),
  checkMessage: (text: string) => req<{ scam_probability: number; label: string; top_terms: { term: string; weight: number }[]; draft_removal: string }>('POST', '/messages/check', { text }),
}

export const REASON_LABELS: Record<ReasonCategory, string> = {
  skill_gap: 'Skill gap', minor_issue: 'Minor issue', capacity: 'Capacity', scam_abuse: 'Scam / abuse', rules_mismatch: 'Rules mismatch',
}
export const RECONSIDERABLE: ReasonCategory[] = ['skill_gap', 'minor_issue', 'capacity']
