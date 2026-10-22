import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import { Button, Card, Field, Label, inputCls } from '../components/ui'

export default function AppealPage() {
  const [f, setF] = useState({ identifier_type: 'phone', identifier: '', contact: '', message: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<{ matched: boolean } | null>(null)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try { setDone(await api.appeal(f)) } catch (e2) { setErr((e2 as Error).message) } finally { setBusy(false) }
  }
  if (done) return (
    <Card className="fade-in">
      <Label>Appeal received</Label>
      <p className="mt-2 text-sm">{done.matched ? 'We found a shared-blocklist entry for that identifier. The community that reported it will review your appeal, and until then the entry shows as “appealed”, so other communities send you to a human instead of auto-declining.' : 'No blocklist entry matched that identifier, so nothing was changed. If you were declined, it wasn’t because of the shared blocklist.'}</p>
    </Card>
  )
  return (
    <div className="fade-in">
      <Label>Shared blocklist · appeal</Label>
      <h1 className="mt-1.5 text-2xl font-semibold tracking-tight">Think you were blocked by mistake?</h1>
      <p className="mt-2 text-sm text-muted">Communities share hashed identifiers (phone, email, handle) of confirmed scammers. Enter the identifier you were blocked under; we hash it the same way and the reporting community reviews your appeal.</p>
      <form onSubmit={submit}>
        <Card className="mt-6 space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[10rem_1fr]">
            <Field label="Type">
              <select className={inputCls} value={f.identifier_type} onChange={e => setF({ ...f, identifier_type: e.target.value })}>
                <option value="phone">Phone</option><option value="email">Email</option><option value="github">GitHub</option><option value="handle">Chat handle</option>
              </select>
            </Field>
            <Field label="Identifier *"><input required className={inputCls} value={f.identifier} onChange={e => setF({ ...f, identifier: e.target.value })} /></Field>
          </div>
          <Field label="How to reach you *"><input required className={inputCls} value={f.contact} onChange={e => setF({ ...f, contact: e.target.value })} /></Field>
          <Field label="Why this is a mistake *"><textarea required rows={4} className={inputCls} value={f.message} onChange={e => setF({ ...f, message: e.target.value })} /></Field>
          {err && <div className="text-sm text-decline">Couldn’t submit: {err}</div>}
          <Button variant="primary" disabled={busy} type="submit">{busy ? 'Submitting…' : 'Submit appeal'}</Button>
        </Card>
      </form>
    </div>
  )
}
