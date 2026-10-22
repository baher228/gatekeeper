import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, REASON_LABELS } from '../api'
import type { ApplicantDetail, ModelInfo, ReasonCategory } from '../api'
import { useAsync } from '../hooks'
import { Button, Card, Empty, ErrorState, Kbd, Label, Loading, PageHeader, Tag, cx, inputCls, timeAgo } from '../components/ui'
import { ExtrasChips } from '../components/Extras'
import { EvidencePanel, HistoryPanel, RuleChecks, VerdictSummary } from '../components/Evidence'

const REASON_KEYS: ReasonCategory[] = ['skill_gap', 'minor_issue', 'capacity', 'rules_mismatch', 'scam_abuse']

export default function QueuePage() {
  const { slug = '' } = useParams()
  const q = useAsync(() => api.queue(slug), [slug])
  const m = useAsync(() => api.model(slug), [slug])
  const [idx, setIdx] = useState(0)
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState<ReasonCategory>('skill_gap')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [cleared, setCleared] = useState(0)
  const [flash, setFlash] = useState<string | null>(null)
  const [model, setModel] = useState<ModelInfo | null>(null)
  const [tab, setTab] = useState<'rules' | 'evidence' | 'history'>('rules')

  const items = q.data ?? []
  const cur: ApplicantDetail | undefined = items[Math.min(idx, items.length - 1)]
  const mi = model ?? m.data

  const decide = useCallback(async (verdict: 'accept' | 'ask_more' | 'decline', rc?: ReasonCategory) => {
    if (!cur || busy) return
    setBusy(true); setErr(null)
    try {
      const res = await api.decide(cur.id, { verdict, reason_category: rc, note: note || undefined })
      setModel(res.model)
      setCleared(c => c + 1)
      setFlash(`${cur.name}: ${verdict === 'ask_more' ? 'asked for more info' : verdict === 'accept' ? `accepted (${res.applicant.status})` : `declined · ${REASON_LABELS[rc!]}`} · model retrained on ${res.model.n_decisions} decisions`)
      setDeclining(false); setNote('')
      if (verdict === 'ask_more') setIdx(i => i + 1)
      else q.setData(xs => (xs ?? []).filter(x => x.id !== cur.id))
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }, [cur, busy, note, q])

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || e.metaKey || e.ctrlKey) return
      if (declining) {
        const n = Number(e.key)
        if (n >= 1 && n <= REASON_KEYS.length) { e.preventDefault(); decide('decline', REASON_KEYS[n - 1]) }
        if (e.key === 'Escape') setDeclining(false)
        return
      }
      if (e.key === 'a') decide('accept')
      else if (e.key === 's') decide('ask_more')
      else if (e.key === 'd') setDeclining(true)
      else if (e.key === 'j' || e.key === 'ArrowRight') setIdx(i => Math.min(i + 1, Math.max(items.length - 1, 0)))
      else if (e.key === 'k' || e.key === 'ArrowLeft') setIdx(i => Math.max(i - 1, 0))
      else if (e.key === '1') setTab('rules'); else if (e.key === '2') setTab('evidence'); else if (e.key === '3') setTab('history')
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [decide, declining, items.length])

  return (
    <div>
      <PageHeader label="Lead · review queue" title="Borderline cases"
        sub="Gatekeeper decided the clear cases itself. These are the ones it routed to you, one card at a time. Every decision you make here is stored and retrains the history model."
        right={<>
          {mi && <Tag>{mi.available ? `model retrained on ${mi.n_decisions} decisions` : `model: ${mi.n_decisions} decisions, needs 10`}</Tag>}
          {cleared > 0 && <Tag tone="accept">{cleared} cleared this session</Tag>}
        </>} />
      {flash && <div className="fade-in mb-4 rounded-lg border border-line bg-card px-4 py-2.5 font-mono text-xs text-muted">{flash}</div>}
      {q.loading && <Loading label="Loading queue" />}
      {q.error && <ErrorState message={q.error} onRetry={q.reload} />}
      {!q.loading && !q.error && items.length === 0 && <Empty title="Queue is clear." sub="New borderline applications will show up here and in the notifications bell." />}
      {cur && (
        <div className="fade-in" key={cur.id}>
          <div className="mb-3 flex items-center justify-between gap-2 font-mono text-xs text-muted">
            <span>{Math.min(idx, items.length - 1) + 1} / {items.length} waiting</span>
            <span className="hidden sm:inline"><Kbd>A</Kbd> accept · <Kbd>S</Kbd> ask more · <Kbd>D</Kbd> decline · <Kbd>J</Kbd>/<Kbd>K</Kbd> next/prev · <Kbd>1</Kbd><Kbd>2</Kbd><Kbd>3</Kbd> tabs</span>
          </div>
          <Card pad={false}>
            <div className="border-b border-line p-5">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold">{cur.name}</h2>
                    <Tag>{cur.category}</Tag>
                    {cur.is_seed && <Tag>seed</Tag>}
                    {cur.reconsidered && <Tag tone="accept">reconsidered</Tag>}
                    <ExtrasChips a={cur} />
                  </div>
                  <div className="mt-1 truncate font-mono text-xs text-muted">{[cur.email, cur.github && `gh:${cur.github}`, cur.devpost && `dp:${cur.devpost}`, cur.chat_handle].filter(Boolean).join(' · ')} · {timeAgo(cur.created_at)}</div>
                </div>
                <Link to={`/c/${slug}/applicants/${cur.id}`} className="shrink-0 text-sm text-link hover:underline">Full detail →</Link>
              </div>
              <p className="mt-4 whitespace-pre-line text-sm leading-relaxed">{cur.what_build}</p>
              {cur.reconsideration.note && <p className="mt-3 rounded-lg border border-accept/20 bg-accept/[.04] px-3 py-2 text-sm">{cur.reconsideration.note}</p>}
            </div>
            <div className="border-b border-line p-5"><VerdictSummary a={cur} compact /></div>
            <div className="p-5">
              <div className="mb-4 flex gap-1">
                {(['rules', 'evidence', 'history'] as const).map((t, i) => (
                  <button key={t} onClick={() => setTab(t)} className={cx('rounded-md px-2.5 py-1 text-sm', tab === t ? 'bg-white/[.07]' : 'text-muted hover:text-fg')}>{i + 1}. {t === 'rules' ? 'Rule checks' : t === 'evidence' ? 'Evidence' : 'History model'}</button>
                ))}
              </div>
              {tab === 'rules' && <RuleChecks r={cur.recommendation} />}
              {tab === 'evidence' && <EvidencePanel r={cur.recommendation} />}
              {tab === 'history' && <HistoryPanel r={cur.recommendation} />}
            </div>
            <div className="sticky bottom-0 rounded-b-xl border-t border-line bg-card/95 p-4 backdrop-blur">
              {err && <div className="mb-3 text-sm text-decline">{err}</div>}
              {!declining ? (
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <input className={cx(inputCls, 'sm:max-w-xs')} placeholder="Note (optional)" value={note} onChange={e => setNote(e.target.value)} />
                  <div className="grid grid-cols-3 gap-2 sm:ml-auto sm:flex">
                    <Button variant="accept" disabled={busy} onClick={() => decide('accept')}>Accept <Kbd>A</Kbd></Button>
                    <Button variant="ask" disabled={busy} onClick={() => decide('ask_more')}>Ask more <Kbd>S</Kbd></Button>
                    <Button variant="decline" disabled={busy} onClick={() => setDeclining(true)}>Decline <Kbd>D</Kbd></Button>
                  </div>
                </div>
              ) : (
                <div className="fade-in">
                  <Label className="mb-2">Decline reason · stored for reconsideration</Label>
                  <div className="flex flex-wrap gap-2">
                    {REASON_KEYS.map((k, i) => (
                      <Button key={k} variant={reason === k ? 'decline' : 'default'} disabled={busy} onMouseEnter={() => setReason(k)} onClick={() => decide('decline', k)}>
                        <Kbd>{i + 1}</Kbd> {REASON_LABELS[k]}
                      </Button>
                    ))}
                    <Button variant="ghost" onClick={() => setDeclining(false)}>Cancel <Kbd>Esc</Kbd></Button>
                  </div>
                  <p className="mt-2 text-xs text-muted">Skill gap, minor issue and capacity are re-checked automatically after the cool-down. Scam / abuse is never re-checked.</p>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
