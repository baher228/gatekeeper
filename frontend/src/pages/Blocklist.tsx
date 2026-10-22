import { useState } from 'react'
import type { FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import type { BlockEntry } from '../api'
import { useAsync } from '../hooks'
import { Button, Card, Empty, ErrorState, Field, Label, Loading, PageHeader, StatusBadge, Tag, fmtDate, inputCls } from '../components/ui'

function EntryCard({ e, slug, onChange }: { e: BlockEntry; slug: string; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const run = async (fn: () => Promise<unknown>) => { setBusy(true); setErr(null); try { await fn(); onChange() } catch (x) { setErr((x as Error).message) } finally { setBusy(false) } }
  return (
    <Card className={e.status === 'removed' ? 'opacity-50' : ''}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={e.status} />
        <Tag>{e.identifier_type}</Tag>
        <span className="font-mono text-xs text-muted">hash {e.identifier_hash_prefix}…</span>
        <span className="ml-auto text-xs text-muted">{e.is_own ? 'reported by you' : `reported by ${e.reporting_community.name}`} · {fmtDate(e.created_at)}</span>
      </div>
      <p className="mt-3 text-sm">{e.evidence}</p>
      {e.links.map(l => <a key={l} href={l} target="_blank" rel="noreferrer" className="mt-1 block truncate font-mono text-xs text-link hover:underline">{l}</a>)}
      {e.appeals.length > 0 && (
        <div className="mt-4 space-y-2">
          <Label>Appeals</Label>
          {e.appeals.map(ap => (
            <div key={ap.id} className="rounded-lg border border-line bg-bg p-3">
              <div className="flex flex-wrap items-center gap-2"><StatusBadge status={ap.status} /><span className="font-mono text-xs text-muted">{ap.contact} · {fmtDate(ap.created_at)}</span></div>
              <p className="mt-1.5 text-sm">{ap.message}</p>
              {ap.status === 'open' && e.is_own && (
                <div className="mt-2 flex gap-2">
                  <Button variant="accept" disabled={busy} onClick={() => run(() => api.resolveAppeal(slug, ap.id, 'upheld'))}>Uphold · remove entry</Button>
                  <Button variant="decline" disabled={busy} onClick={() => run(() => api.resolveAppeal(slug, ap.id, 'rejected'))}>Reject appeal</Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {e.is_own && (e.status === 'pending' || e.status === 'confirmed') && (
        <div className="mt-4 flex gap-2">
          {e.status === 'pending' && <Button variant="decline" disabled={busy} onClick={() => run(() => api.confirmEntry(slug, e.id))}>Confirm · share with all communities</Button>}
          <Button variant="ghost" disabled={busy} onClick={() => run(() => api.removeEntry(slug, e.id))}>Remove</Button>
        </div>
      )}
      {err && <p className="mt-2 text-sm text-decline">{err}</p>}
    </Card>
  )
}

function EventBlacklist({ slug }: { slug: string }) {
  const bans = useAsync(() => api.bans(slug), [slug])
  const [f, setF] = useState({ identifier_type: 'email', identifier: '', reason: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null)
    try { await fn(); bans.reload() } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  const add = (e: FormEvent) => { e.preventDefault(); run(async () => { await api.addBan(slug, f); setF({ ...f, identifier: '', reason: '' }) }) }
  const items = bans.data ?? []
  return (
    <section className="mt-10">
      <Label>Event blacklist · private to this community</Label>
      <p className="mt-2 max-w-3xl text-sm text-muted">People you never want at your events. A match declines them here only; other communities never see these rows (row-level security on community).</p>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-2">
          {bans.loading && <Loading />}
          {bans.error && <ErrorState message={bans.error} onRetry={bans.reload} />}
          {!bans.loading && !bans.error && items.length === 0 && <Empty title="Nobody on your event blacklist." />}
          {items.map(b => (
            <Card key={b.id} className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-mono text-xs text-muted">{b.identifier_type} · {b.label ?? 'hashed'} · {fmtDate(b.created_at)}</div>
                <div className="mt-1 text-sm">{b.reason}</div>
              </div>
              <Button disabled={busy} onClick={() => run(() => api.removeBan(slug, b.id))}>Remove</Button>
            </Card>
          ))}
        </div>
        <form onSubmit={add}>
          <Card className="space-y-3">
            <Label>Ban from our events</Label>
            <Field label="Type">
              <select className={inputCls} value={f.identifier_type} onChange={e => setF({ ...f, identifier_type: e.target.value })}>
                <option value="email">Email</option><option value="phone">Phone</option><option value="github">GitHub</option><option value="handle">Chat handle</option>
              </select>
            </Field>
            <Field label="Identifier"><input required className={inputCls} value={f.identifier} onChange={e => setF({ ...f, identifier: e.target.value })} /></Field>
            <Field label="Reason"><input required className={inputCls} value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} placeholder="Harassed attendees at the March event" /></Field>
            {err && <p className="text-sm text-decline">{err}</p>}
            <Button variant="primary" type="submit" disabled={busy} className="w-full">Add to event blacklist</Button>
          </Card>
        </form>
      </div>
    </section>
  )
}

export default function BlocklistPage() {
  const { slug = '' } = useParams()
  const list = useAsync(() => api.blocklist(slug), [slug])
  const [f, setF] = useState({ identifier_type: 'phone', identifier: '', evidence: '', links: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      await api.report(slug, { ...f, links: f.links.split(/\s+/).filter(Boolean) })
      setF({ identifier_type: 'phone', identifier: '', evidence: '', links: '' }); list.reload()
    } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  const items = list.data ?? []
  return (
    <div>
      <PageHeader label="Shared · blocklist" title="Shared blocklist"
        sub={<>Identifiers are normalised (phone to E.164, handles lowercased) and HMAC-SHA256 hashed with a shared pepper, so communities can match without sharing raw numbers. Postgres row-level security means you see your own pending reports plus every confirmed one, and never other communities’ pending reports. Appeals come in through the public <a className="text-link hover:underline" href="/appeal" target="_blank" rel="noreferrer">appeal form</a>.</>} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-3">
          {list.loading && <Loading />}
          {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
          {!list.loading && !list.error && items.length === 0 && <Empty title="No reports visible to this community." />}
          {items.map(e => <EntryCard key={e.id} e={e} slug={slug} onChange={list.reload} />)}
        </div>
        <form onSubmit={submit} className="lg:sticky lg:top-32 lg:self-start">
          <Card className="space-y-3">
            <Label>Report someone</Label>
            <p className="text-xs text-muted">New reports start as pending and are only visible to your community until you confirm them.</p>
            <Field label="Type">
              <select className={inputCls} value={f.identifier_type} onChange={e => setF({ ...f, identifier_type: e.target.value })}>
                <option value="phone">Phone</option><option value="email">Email</option><option value="github">GitHub</option><option value="handle">Chat handle</option>
              </select>
            </Field>
            <Field label="Identifier"><input required className={inputCls} value={f.identifier} onChange={e => setF({ ...f, identifier: e.target.value })} placeholder="+44 7700 900000" /></Field>
            <Field label="Evidence"><textarea required rows={3} className={inputCls} value={f.evidence} onChange={e => setF({ ...f, evidence: e.target.value })} placeholder="What happened, quoted messages" /></Field>
            <Field label="Links" hint="Space-separated screenshot or message links"><input className={inputCls} value={f.links} onChange={e => setF({ ...f, links: e.target.value })} /></Field>
            {err && <p className="text-sm text-decline">{err}</p>}
            <Button variant="primary" type="submit" disabled={busy} className="w-full">{busy ? 'Reporting…' : 'Report (pending)'}</Button>
          </Card>
        </form>
      </div>
      <EventBlacklist slug={slug} />
    </div>
  )
}
