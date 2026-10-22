import type { ApplicantDetail, EvidenceStatus, Recommendation } from '../api'
import { REASON_LABELS } from '../api'
import { Card, Label, ScoreBar, StatusBadge, Tag, cx, fmtDate, pct } from './ui'

const ROUTE_LABELS: Record<string, string> = {
  blocklist_confirmed: 'Confirmed shared-blocklist match', blocklist_unconfirmed: 'Unconfirmed blocklist match – lead decides',
  spam_signal: 'StopForumSpam signal – lead decides', incomplete: 'Incomplete application', disagreement: 'Rules and history model disagree – lead decides',
  score_accept: 'Score above accept threshold', score_decline: 'Score below decline threshold', low_confidence: 'Borderline score – lead decides',
}

export function SourceTag({ status }: { status: EvidenceStatus }) {
  const tone = status === 'live' ? 'accept' : status === 'simulated' ? 'ask' : 'muted'
  return <Tag tone={tone} className="h-5 px-1.5 text-[10px] uppercase">{status.replace('_', ' ')}</Tag>
}

export function VerdictSummary({ a, compact = false }: { a: ApplicantDetail; compact?: boolean }) {
  const r = a.recommendation
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <Label>Recommendation</Label>
        <StatusBadge status={r.verdict} />
        {a.status !== (r.verdict === 'accept' ? 'accepted' : r.verdict === 'decline' ? 'declined' : 'ask') && <><span className="text-faint">→</span><StatusBadge status={a.status} /></>}
        {r.disagreement && <Tag tone="ask">model disagrees</Tag>}
        {r.llm.status === 'live' ? <Tag tone="accept">{r.llm.provider} · {r.llm.model}</Tag> : <Tag title={r.llm.error ?? undefined} tone="ask" className="max-w-full truncate">LLM unavailable – rule-only reasoning</Tag>}
      </div>
      <div className="mt-2 text-sm text-muted">{ROUTE_LABELS[r.route_rule] ?? r.route_rule}{a.decline_reason && ` · ${REASON_LABELS[a.decline_reason]}`}</div>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div><Label className="mb-1.5">Final score</Label><ScoreBar value={r.final_score} /></div>
        <div><Label className="mb-1.5">Rules</Label><ScoreBar value={r.rule_score} /></div>
        <div><Label className="mb-1.5">History P(accept)</Label>{r.history.available ? <ScoreBar value={r.history.p_accept} /> : <span className="font-mono text-xs text-muted">no model yet</span>}</div>
      </div>
      <div className="mt-1 font-mono text-[11px] text-muted">confidence {pct(r.confidence)}</div>
      <ul className="mt-4 space-y-1.5">
        {r.reasons.slice(0, compact ? 4 : 20).map((x, i) => (
          <li key={i} className="flex gap-2.5 text-sm leading-snug"><span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-muted" /><span>{x}</span></li>
        ))}
      </ul>
    </div>
  )
}

export function RuleChecks({ r }: { r: Recommendation }) {
  return (
    <div className="divide-y divide-line/70">
      {r.rule_checks.map(c => (
        <div key={c.rule_id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
          <span className={cx('mt-1 h-2 w-2 shrink-0 rounded-full', c.verdict === 'pass' ? 'bg-accept/80' : c.verdict === 'fail' ? 'bg-decline/80' : 'bg-ask/80')} />
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <div className="text-sm">{c.rule}</div>
              <span className="shrink-0 font-mono text-xs text-muted">{c.score.toFixed(2)}</span>
            </div>
            <div className="mt-0.5 text-sm text-muted">{c.reason}</div>
            {c.quote && <div className="mt-1.5 border-l border-line pl-2.5 text-xs italic text-muted">“{c.quote}”</div>}
            <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-faint">{c.source === 'llm' ? 'LLM' : 'heuristic'}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex justify-between gap-3 py-1 text-sm"><span className="text-muted">{k}</span><span className="text-right font-mono text-[13px]">{v}</span></div>
}

export function EvidencePanel({ r }: { r: Recommendation }) {
  const { github: g, devpost: d, stopforumspam: s, blocklist: b } = r.evidence
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <Card className={cx(b.hit && 'border-decline/30')}>
        <div className="flex items-center justify-between"><Label>Shared blocklist</Label>{b.hit ? <Tag tone="decline">match</Tag> : <Tag>no match</Tag>}</div>
        {b.matches.length === 0 && <p className="mt-2 text-sm text-muted">No identifier matched any report this community can see.</p>}
        {b.matches.map(m => (
          <div key={m.entry_id + m.identifier_type} className="mt-3 rounded-lg border border-decline/20 bg-decline/[.04] p-3">
            <div className="flex flex-wrap items-center gap-2 text-sm"><StatusBadge status={m.status} /><span className="font-mono text-xs">{m.identifier_type}</span><span className="text-muted">reported by {m.reporting_community} · {fmtDate(m.reported_at)}</span></div>
            <p className="mt-2 text-sm">{m.evidence}</p>
            {m.links.map(l => <a key={l} href={l} target="_blank" rel="noreferrer" className="mt-1 block truncate font-mono text-xs text-link hover:underline">{l}</a>)}
          </div>
        ))}
      </Card>
      <Card>
        <div className="flex items-center justify-between"><Label>GitHub</Label><SourceTag status={g.status} /></div>
        {g.account_age_days != null ? (
          <div className="mt-2">
            <Row k="Login" v={g.url ? <a className="text-link hover:underline" href={g.url} target="_blank" rel="noreferrer">{g.login}</a> : g.login} />
            <Row k="Account age" v={`${(g.account_age_days / 365).toFixed(1)}y`} />
            <Row k="Public repos" v={g.public_repos} />
            <Row k="Followers" v={g.followers} />
            <Row k="Last push" v={g.recent_push_days == null ? '—' : `${g.recent_push_days}d ago`} />
          </div>
        ) : <p className="mt-2 text-sm text-muted">{g.status === 'not_provided' ? 'No handle given.' : g.status === 'not_found' ? 'Handle not found.' : 'Lookup failed.'}</p>}
      </Card>
      <Card>
        <div className="flex items-center justify-between"><Label>Devpost</Label><SourceTag status={d.status} /></div>
        {d.projects != null ? (
          <div className="mt-2">
            <Row k="Projects" v={d.projects} />
            <Row k="Wins" v={d.wins ?? 0} />
            {d.sample?.map(p => <a key={p.url} href={p.url} target="_blank" rel="noreferrer" className="block truncate py-0.5 text-sm text-link hover:underline">{p.name}</a>)}
          </div>
        ) : <p className="mt-2 text-sm text-muted">{d.status === 'not_provided' ? 'No handle given.' : d.status === 'not_found' ? 'No projects found.' : 'Lookup failed.'}</p>}
      </Card>
      <Card>
        <div className="flex items-center justify-between"><Label>StopForumSpam</Label><SourceTag status={s.status} /></div>
        {s.confidence != null || s.email_appears != null ? (
          <div className="mt-2">
            <Row k="Email reported" v={s.email_appears ? 'yes' : 'no'} />
            <Row k="Username reported" v={s.username_appears ? 'yes' : 'no'} />
            <Row k="Confidence" v={s.confidence != null ? `${s.confidence.toFixed(0)}%` : '—'} />
          </div>
        ) : <p className="mt-2 text-sm text-muted">{s.status === 'unavailable' ? 'Lookup failed.' : 'Not checked.'}</p>}
      </Card>
    </div>
  )
}

export function HistoryPanel({ r }: { r: Recommendation }) {
  const h = r.history
  if (!h.available) return <p className="text-sm text-muted">Fewer than 10 past decisions with both outcomes – the history model isn't trained yet.</p>
  const max = Math.max(...h.top_features.map(f => Math.abs(f.contribution)), 0.01)
  return (
    <div>
      <p className="text-sm text-muted">Scored at submission by a model trained on {h.n_training} decisions. P(accept) = <span className="font-mono text-fg">{h.p_accept?.toFixed(2)}</span>. Top contributing features:</p>
      <div className="mt-3 space-y-2">
        {h.top_features.map(f => (
          <div key={f.feature} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_3.5rem] items-center gap-3">
            <span className="truncate font-mono text-xs">{f.feature} <span className="text-faint">= {Number.isInteger(f.value) ? f.value : f.value.toFixed(2)}</span></span>
            <div className="relative h-1.5 rounded-full bg-white/[.06]">
              <div className={cx('absolute top-0 h-full rounded-full', f.contribution >= 0 ? 'left-1/2 bg-accept/60' : 'right-1/2 bg-decline/60')} style={{ width: `${(Math.abs(f.contribution) / max) * 50}%` }} />
              <div className="absolute left-1/2 top-[-3px] h-[12px] w-px bg-line" />
            </div>
            <span className={cx('text-right font-mono text-xs', f.contribution >= 0 ? 'text-accept' : 'text-decline')}>{f.contribution >= 0 ? '+' : ''}{f.contribution.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
