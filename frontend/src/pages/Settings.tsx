import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import type { CategoryQuota, Rule } from '../api'
import { useAsync } from '../hooks'
import { Button, Card, ErrorState, Field, Label, Loading, PageHeader, inputCls } from '../components/ui'

type Cat = Omit<CategoryQuota, 'used' | 'remaining' | 'waitlisted'>

export default function SettingsPage() {
  const { slug = '' } = useParams()
  const c = useAsync(() => api.community(slug), [slug])
  const [rules, setRules] = useState<Rule[]>([])
  const [cats, setCats] = useState<Cat[]>([])
  const [cool, setCool] = useState(60)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  useEffect(() => {
    if (!c.data) return
    setRules(c.data.rules); setCool(c.data.reconsider_cooldown_days)
    setCats(c.data.categories.map(({ slug, name, quota, bypass_quota }) => ({ slug, name, quota, bypass_quota })))
  }, [c.data])

  const save = async () => {
    setBusy(true); setMsg(null)
    try {
      const r = await api.saveSettings(slug, { rules: rules.filter(r => r.text.trim()), categories: cats.filter(k => k.slug.trim() && k.name.trim()), reconsider_cooldown_days: cool })
      c.setData(r); setMsg({ ok: true, text: 'Saved. New applications are scored against these rules.' })
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }) } finally { setBusy(false) }
  }

  if (c.loading && !c.data) return <Loading />
  if (c.error || !c.data) return <ErrorState message={c.error ?? 'Not found'} onRetry={c.reload} />
  const usage = Object.fromEntries(c.data.categories.map(k => [k.slug, k]))

  return (
    <div>
      <PageHeader label="Lead · settings" title="Rules & quotas"
        sub="Write your community’s rules the way you’d explain them to a co-organiser. Each application is scored against every rule, with a quoted reason. Quotas cap the seats per guest category for the current event."
        right={<Button variant="primary" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save changes'}</Button>} />
      {msg && <div className={`mb-4 rounded-lg border px-4 py-2.5 text-sm ${msg.ok ? 'border-line bg-card text-muted' : 'border-decline/25 text-decline'}`}>{msg.text}</div>}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <Label>Written rules</Label>
          <div className="mt-4 space-y-2">
            {rules.map((r, i) => (
              <div key={i} className="flex gap-2">
                <span className="mt-2.5 w-6 shrink-0 font-mono text-xs text-muted">{String(i + 1).padStart(2, '0')}</span>
                <textarea rows={2} className={inputCls} value={r.text} onChange={e => setRules(rs => rs.map((x, j) => j === i ? { ...x, text: e.target.value } : x))} />
                <Button variant="ghost" aria-label="Remove rule" onClick={() => setRules(rs => rs.filter((_, j) => j !== i))}>✕</Button>
              </div>
            ))}
          </div>
          <Button className="mt-3" onClick={() => setRules(rs => [...rs, { text: '' }])}>Add rule</Button>
        </Card>
        <div className="space-y-4">
          <Card>
            <Label>Guest categories & quotas</Label>
            <div className="mt-4 space-y-3">
              <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_4.5rem_4.5rem_2rem] gap-2 font-mono text-[10px] uppercase tracking-wider text-faint">
                <span>slug</span><span>name</span><span>seats</span><span>bypass</span><span />
              </div>
              {cats.map((k, i) => (
                <div key={i}>
                  <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_4.5rem_4.5rem_2rem] items-center gap-2">
                    <input className={`${inputCls} font-mono text-xs`} value={k.slug} onChange={e => setCats(cs => cs.map((x, j) => j === i ? { ...x, slug: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') } : x))} />
                    <input className={inputCls} value={k.name} onChange={e => setCats(cs => cs.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
                    <input type="number" min={0} className={inputCls} value={k.quota} onChange={e => setCats(cs => cs.map((x, j) => j === i ? { ...x, quota: Number(e.target.value) } : x))} />
                    <label className="flex justify-center"><input type="checkbox" className="h-4 w-4 accent-white" checked={k.bypass_quota} onChange={e => setCats(cs => cs.map((x, j) => j === i ? { ...x, bypass_quota: e.target.checked } : x))} /></label>
                    <Button variant="ghost" className="px-0" aria-label="Remove category" onClick={() => setCats(cs => cs.filter((_, j) => j !== i))}>✕</Button>
                  </div>
                  {usage[k.slug] && <div className="mt-1 font-mono text-[11px] text-muted">{usage[k.slug].used} accepted · {usage[k.slug].waitlisted} waitlisted</div>}
                </div>
              ))}
            </div>
            <Button className="mt-3" onClick={() => setCats(cs => [...cs, { slug: '', name: '', quota: 10, bypass_quota: false }])}>Add category</Button>
          </Card>
          <Card>
            <Label>Reconsideration</Label>
            <div className="mt-3 max-w-xs">
              <Field label="Cool-down (days)" hint="Declines for a skill gap, a minor issue or capacity are re-checked after this, daily at 06:00 or with “Re-check now”. Scam / abuse declines never are.">
                <input type="number" min={0} className={inputCls} value={cool} onChange={e => setCool(Number(e.target.value))} />
              </Field>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
