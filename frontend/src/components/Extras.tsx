import { useState } from 'react'
import { api } from '../api'
import type { ApplicantDetail, AttendeeNote, NoteFlag } from '../api'
import { Button, Label, Tag, cx, fmtDate, inputCls, timeAgo } from './ui'

export const FLAG_LABELS: Record<NoteFlag, string> = {
  great_volunteer: 'great volunteer', no_show: 'no-show', disruptive: 'disruptive', watch: 'watch', vip: 'VIP',
}
const FLAG_TONE: Record<NoteFlag, 'muted' | 'accept' | 'ask' | 'decline'> = {
  great_volunteer: 'accept', vip: 'accept', no_show: 'ask', watch: 'ask', disruptive: 'decline',
}

export function attendanceLine(a: ApplicantDetail) {
  const at = a.extras?.attendance
  if (!at || (!at.attended && !at.no_show)) return null
  return [at.attended ? `Attended ${at.attended} of your past events` : null, at.no_show ? `No-show at ${at.no_show} of your past events` : null].filter(Boolean).join(' · ')
}

export function ExtrasChips({ a }: { a: ApplicantDetail }) {
  const e = a.extras
  if (!e) return null
  const line = attendanceLine(a)
  return <>
    {e.ban && <Tag tone="decline">on your event blacklist</Tag>}
    {line && <Tag tone={e.attendance.no_show ? 'ask' : 'accept'}>{line}</Tag>}
    {e.shared_flags.map(f => <Tag key={f.flag + f.community_name} tone={FLAG_TONE[f.flag]} title={`Shared by ${f.community_name}`}>{FLAG_LABELS[f.flag]} · {f.community_name}</Tag>)}
  </>
}

function NoteRow({ n, onDelete }: { n: AttendeeNote; onDelete?: () => void }) {
  return (
    <div className="rounded-lg border border-line px-3 py-2">
      <div className="flex flex-wrap items-center gap-1.5 font-mono text-[11px] text-muted">
        {n.flag && <Tag tone={FLAG_TONE[n.flag]}>{FLAG_LABELS[n.flag]}</Tag>}
        <span>{n.visibility}</span><span>·</span><span>{n.community_name}</span><span>·</span><span>{timeAgo(n.created_at)}</span>
        {onDelete && <button onClick={onDelete} className="ml-auto text-muted hover:text-decline">remove</button>}
      </div>
      {n.note && <p className="mt-1 text-sm">{n.note}</p>}
    </div>
  )
}

export function ExtrasPanel({ a, onChange }: { a: ApplicantDetail; onChange: () => void }) {
  const e = a.extras
  const [flag, setFlag] = useState<NoteFlag | null>(null)
  const [note, setNote] = useState('')
  const [shared, setShared] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  if (!e) return null
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null)
    try { await fn(); onChange() } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  const save = () => run(async () => { await api.addNote(a.id, { flag, note: note.trim(), visibility: shared ? 'shared' : 'private' }); setFlag(null); setNote('') })
  const at = e.attendance
  return <>
    <div>
      <Label>Attendance at your events</Label>
      {at.events.length === 0 ? <p className="mt-2 text-sm text-muted">No past events on record.</p> : <>
        <p className="mt-2 text-sm">{attendanceLine(a)}</p>
        <div className="mt-2 space-y-1">
          {at.events.map((ev, i) => (
            <div key={i} className="flex items-center justify-between gap-2 font-mono text-xs">
              <span className="truncate text-muted">{ev.event_name} · {fmtDate(ev.event_date)}</span>
              <span className={ev.status === 'attended' ? 'text-accept' : 'text-ask'}>{ev.status === 'attended' ? 'attended' : 'no-show'}</span>
            </div>
          ))}
        </div>
      </>}
    </div>
    <div className="border-t border-line pt-4">
      <Label>Event blacklist</Label>
      {e.ban
        ? <><p className="mt-2 text-sm text-decline">Banned from your events: {e.ban.reason}</p><p className="mt-1 text-xs text-muted">Private to your community. Remove it in the Blocklist tab.</p></>
        : <Button className="mt-2 w-full" variant="decline" disabled={busy} onClick={() => { const r = window.prompt('Reason for banning from your events (private to your community)'); if (r && r.trim()) run(() => api.banApplicant(a.id, r.trim())) }}>Ban from our events</Button>}
    </div>
    <div className="border-t border-line pt-4">
      <Label>Add a note</Label>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {(Object.keys(FLAG_LABELS) as NoteFlag[]).map(f => (
          <button key={f} type="button" onClick={() => setFlag(flag === f ? null : f)}
            className={cx('rounded-md border px-2 py-0.5 font-mono text-[11px]', flag === f ? 'border-fg/60 bg-white/[.07] text-fg' : 'border-line text-muted hover:text-fg')}>{FLAG_LABELS[f]}</button>
        ))}
      </div>
      <textarea rows={2} maxLength={500} className={cx(inputCls, 'mt-2')} value={note} onChange={ev => setNote(ev.target.value)} placeholder="What should other organisers know?" />
      <div className="mt-2 flex items-center justify-between gap-2">
        <div className="flex rounded-lg border border-line p-0.5 text-xs">
          {(['private', 'shared'] as const).map(v => (
            <button key={v} type="button" onClick={() => setShared(v === 'shared')} className={cx('rounded-md px-2 py-1', (v === 'shared') === shared ? 'bg-white/[.07]' : 'text-muted')}>{v}</button>
          ))}
        </div>
        <Button variant="primary" disabled={busy || (!flag && !note.trim())} onClick={save}>Save note</Button>
      </div>
      <p className="mt-1.5 text-xs text-muted">{shared ? 'Shared: every community on Gatekeeper sees this.' : 'Private: only your community sees this.'}</p>
      {err && <p className="mt-2 text-sm text-decline">{err}</p>}
    </div>
    <div className="border-t border-line pt-4">
      <Label>Your notes</Label>
      <div className="mt-2 space-y-2">
        {e.own_notes.length === 0 && <p className="text-sm text-muted">None yet.</p>}
        {e.own_notes.map(n => <NoteRow key={n.id} n={n} onDelete={() => run(() => api.deleteNote(a.id, n.id))} />)}
      </div>
    </div>
    <div className="border-t border-line pt-4">
      <Label>Shared by other organisers</Label>
      <div className="mt-2 space-y-2">
        {e.shared_notes.length === 0 && <p className="text-sm text-muted">Nothing shared about this person.</p>}
        {e.shared_notes.map(n => <NoteRow key={n.id} n={n} />)}
      </div>
    </div>
  </>
}
