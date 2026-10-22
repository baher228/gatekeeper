import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import type { ApplicantDetail, ApplyIn } from '../api'
import { useAsync } from '../hooks'
import { Button, Card, ErrorState, Field, Label, Loading, StatusBadge, inputCls } from '../components/ui'
import { VerdictSummary } from '../components/Evidence'

const EMPTY: ApplyIn = { name: '', email: '', phone: '', github: '', devpost: '', chat_handle: '', what_build: '', category: '' }

function TrackLink({ token }: { token: string }) {
  const url = `${window.location.origin}/status/${token}`
  const [copied, setCopied] = useState(false)
  return (
    <div className="mt-4">
      <div className="text-sm">Track your application:</div>
      <div className="mt-1.5 flex gap-2">
        <Link to={`/status/${token}`} className="min-w-0 flex-1 truncate rounded-lg border border-line bg-bg px-3 py-2 font-mono text-xs text-link hover:underline">{url}</Link>
        <Button onClick={() => { navigator.clipboard?.writeText(url); setCopied(true) }}>{copied ? 'Copied' : 'Copy'}</Button>
      </div>
    </div>
  )
}

export default function ApplyPage() {
  const { slug = '' } = useParams()
  const c = useAsync(() => api.community(slug), [slug])
  const [form, setForm] = useState<ApplyIn>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [result, setResult] = useState<ApplicantDetail | null>(null)
  const set = (k: keyof ApplyIn) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true); setErr(null)
    try {
      const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, typeof v === 'string' ? v.trim() : v]).filter(([, v]) => v !== '')) as unknown as ApplyIn
      setResult(await api.apply(slug, body))
    } catch (e2) { setErr((e2 as Error).message) } finally { setBusy(false) }
  }

  if (c.loading) return <Loading />
  if (c.error || !c.data) return <ErrorState message={c.error ?? 'Community not found'} onRetry={c.reload} />
  const com = c.data

  if (busy) return (
    <div className="fade-in grid min-h-[50vh] place-items-center text-center">
      <div>
        <div className="relative mx-auto h-16 w-16">
          <span className="absolute inset-0 animate-ping rounded-full bg-white/10" />
          <span className="absolute inset-0 rounded-full border border-line bg-card" />
          <svg className="absolute inset-0 m-auto animate-[float_1.2s_ease-in-out_infinite]" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></svg>
        </div>
        <h1 className="mt-6 text-xl font-semibold">Sending your application</h1>
        <p className="mt-1.5 text-sm text-muted">Hang tight, this only takes a moment.</p>
      </div>
    </div>
  )

  if (result) return (
    <div className="fade-in space-y-4">
      <Card>
        <div className="pop-in mb-4 grid h-12 w-12 place-items-center rounded-full border border-accept/40 bg-accept/10 text-accept">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path className="draw" d="M20 6 9 17l-5-5" /></svg>
        </div>
        <Label>Application received</Label>
        <h1 className="mt-1.5 text-xl font-semibold">Thanks, {result.name.split(' ')[0]}.</h1>
        <p className="mt-2 text-sm text-muted">{com.name} has your application. You’ll hear back from the lead. Gatekeeper doesn’t send email (that’s a hackathon cut).</p>
        {result.status_token && <TrackLink token={result.status_token} />}
      </Card>
      <Card className="border-dashed">
        <div className="mb-4 flex items-center justify-between gap-2">
          <Label>Lead preview · demo only</Label>
          <StatusBadge status={result.status} />
        </div>
        <VerdictSummary a={result} compact />
        <div className="mt-5 flex flex-wrap gap-2">
          <Link to={`/c/${slug}/applicants/${result.id}`}><Button variant="primary">Open in lead view →</Button></Link>
          <Button onClick={() => { setResult(null); setForm(EMPTY) }}>Submit another</Button>
        </div>
      </Card>
    </div>
  )

  return (
    <div className="fade-in">
      <Label>Apply · {com.slug}</Label>
      <h1 className="mt-1.5 text-2xl font-semibold tracking-tight">{com.name}</h1>
      {com.description && <p className="mt-2 text-sm text-muted">{com.description}</p>}
      <Card className="mt-6">
        <Label>What this community looks for</Label>
        <ol className="mt-3 space-y-1.5 text-sm">
          {com.rules.map((r, i) => <li key={r.id ?? i} className="flex gap-3"><span className="font-mono text-xs text-muted">{String(i + 1).padStart(2, '0')}</span><span>{r.text}</span></li>)}
        </ol>
      </Card>
      <form onSubmit={submit} className="mt-4">
        <Card className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Name *"><input required className={inputCls} value={form.name} onChange={set('name')} autoComplete="name" /></Field>
            <Field label="Email *"><input required type="email" className={inputCls} value={form.email} onChange={set('email')} autoComplete="email" /></Field>
            <Field label="Phone" hint="Hashed for the shared blocklist check"><input className={inputCls} value={form.phone} onChange={set('phone')} placeholder="+44 7700 900000" autoComplete="tel" /></Field>
            <Field label="Discord / WhatsApp handle"><input className={inputCls} value={form.chat_handle} onChange={set('chat_handle')} placeholder="@handle" /></Field>
            <Field label="GitHub username"><input className={inputCls} value={form.github} onChange={set('github')} placeholder="octocat" /></Field>
            <Field label="Devpost username"><input className={inputCls} value={form.devpost} onChange={set('devpost')} /></Field>
          </div>
          <Field label="Category *">
            <select required className={inputCls} value={form.category} onChange={set('category')}>
              <option value="" disabled>Choose one</option>
              {com.categories.map(k => <option key={k.slug} value={k.slug}>{k.name}{!k.bypass_quota && k.remaining === 0 ? ' (waitlist)' : ''}</option>)}
            </select>
          </Field>
          <Field label="What do you build? *" hint="Links to things you shipped help most.">
            <textarea required rows={5} className={inputCls} value={form.what_build} onChange={set('what_build')} />
          </Field>
          {err && <div className="rounded-lg border border-decline/25 bg-decline/5 px-3 py-2 text-sm text-decline">Couldn’t submit: {err}. Your answers are still here, so you can try again.</div>}
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" type="submit" disabled={busy} className="min-w-[11rem]">
              {busy ? <span className="inline-flex items-center gap-2"><span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />Sending</span> : 'Submit application'}
            </Button>
          </div>
        </Card>
      </form>
    </div>
  )
}
