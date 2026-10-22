import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Button, Card, ErrorState, Label, Loading, StatusBadge, cx, inputCls, timeAgo } from '../components/ui'

export default function StatusPage() {
  const { token = '' } = useParams()
  const s = useAsync(() => api.status(token), [token])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  if (s.loading) return <Loading />
  if (s.error || !s.data) return <ErrorState message={s.error ?? 'Application not found'} onRetry={s.reload} />
  const d = s.data
  const send = async () => {
    setBusy(true); setErr(null)
    try { s.setData(await api.reply(token, text.trim())); setText('') } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="fade-in space-y-4">
      <div>
        <Label>Application status · {d.community_name}</Label>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight">Hi {d.name.split(' ')[0]}.</h1>
      </div>
      <Card>
        <div className="flex items-center justify-between gap-3">
          <p className="text-lg">{d.message}</p>
          {d.decision !== 'declined' && <StatusBadge status={d.decision} />}
        </div>
        {d.decision === 'waitlisted' && d.waitlist_position != null && <p className="mt-2 text-sm text-muted">You're #{d.waitlist_position} on the {d.category.replace('_', ' ')} waitlist. If a seat opens, you move up.</p>}
        {d.decision === 'declined' && d.appeal_url && <p className="mt-2 text-sm text-muted">Think this is a mistake? <Link className="text-link hover:underline" to={d.appeal_url}>Appeal it</Link>.</p>}
        {d.decision === 'accepted' && d.invite_url && (
          <div className="mt-4 rounded-lg border border-line p-4">
            <p className="text-sm text-muted">{d.community_name} runs a member network for people who've been accepted. Your name, GitHub and what you build carry over; you choose what to share there.</p>
            <a href={d.invite_url} target="_blank" rel="noreferrer"><Button variant="primary" className="mt-3">Join the member network →</Button></a>
          </div>
        )}
      </Card>
      {(d.lead_question || d.applicant_reply) && (
        <Card className="space-y-3">
          <Label>Question from the lead</Label>
          {d.lead_question && <p className="text-sm">{d.lead_question}</p>}
          {d.applicant_reply ? (
            <div className="rounded-lg border border-line px-3 py-2">
              <div className="font-mono text-[11px] text-muted">your reply{d.applicant_reply_at && ` · ${timeAgo(d.applicant_reply_at)}`}</div>
              <p className="mt-1 whitespace-pre-line text-sm">{d.applicant_reply}</p>
            </div>
          ) : (
            <>
              <textarea rows={4} maxLength={1000} className={cx(inputCls)} value={text} onChange={e => setText(e.target.value)} placeholder="Your answer goes straight to the lead." />
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[11px] text-muted">{text.length}/1000</span>
                <Button variant="primary" disabled={busy || !text.trim()} onClick={send}>{busy ? 'Sending…' : 'Send reply'}</Button>
              </div>
              {err && <p className="text-sm text-decline">{err}</p>}
            </>
          )}
        </Card>
      )}
      <p className="text-xs text-muted">Bookmark this page. It's private to you: anyone with the link can see your status.</p>
    </div>
  )
}
