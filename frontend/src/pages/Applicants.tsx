import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../hooks'
import { LikeButton } from '../components/Extras'
import { Button, Card, Empty, ErrorState, Loading, PageHeader, QuotaBar, ScoreBar, StatusBadge, Tag, cx, inputCls, timeAgo } from '../components/ui'

const STATUSES = ['', 'accepted', 'ask', 'waitlisted', 'declined']

export default function ApplicantsPage() {
  const { slug = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const status = sp.get('status') ?? ''
  const category = sp.get('category') ?? ''
  const liked = sp.get('liked') ?? ''
  const returning = sp.get('returning') ?? ''
  const [text, setText] = useState(sp.get('q') ?? '')
  const c = useAsync(() => api.community(slug), [slug])
  const list = useAsync(() => api.applicants(slug, { status, category, q: sp.get('q') ?? '', liked, returning }), [slug, status, category, sp.get('q'), liked, returning])
  const [rc, setRc] = useState<{ busy: boolean; msg: string | null }>({ busy: false, msg: null })
  const setParam = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }

  const recheckDue = async () => {
    setRc({ busy: true, msg: null })
    try {
      const r = await api.recheckDue(slug)
      setRc({ busy: false, msg: `Re-checked ${r.checked} eligible past declines · ${r.changed.length} changed${r.changed.length ? ': ' + r.changed.map(x => `${x.name} → ${x.status}`).join(', ') : ''}` })
      list.reload(); c.reload()
    } catch (e) { setRc({ busy: false, msg: `Re-check failed: ${(e as Error).message}` }) }
  }

  return (
    <div>
      <PageHeader label="Lead · applicants" title="Everyone who applied"
        sub="Filter by verdict or category. Seats per category are enforced when someone is accepted; past declines for a skill gap, a minor issue or capacity are re-checked after the cool-down."
        right={<Button disabled={rc.busy} onClick={recheckDue}>{rc.busy ? 'Re-checking…' : 'Re-check due declines'}</Button>} />
      {rc.msg && <div className="fade-in mb-4 rounded-lg border border-line bg-card px-4 py-2.5 font-mono text-xs text-muted">{rc.msg}</div>}
      {c.data && (
        <Card className="mb-4 grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-5">
          {c.data.categories.map(k => (
            <button key={k.slug} onClick={() => setParam('category', category === k.slug ? '' : k.slug)} className={cx('-m-2 rounded-lg p-2 text-left transition-colors hover:bg-white/[.04]', category === k.slug && 'bg-white/[.05]')}>
              <QuotaBar name={k.name} used={k.used} quota={k.quota} bypass={k.bypass_quota} waitlisted={k.waitlisted} />
            </button>
          ))}
        </Card>
      )}
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <div className="flex gap-1 overflow-x-auto rounded-lg border border-line bg-card p-1">
          {STATUSES.map(s => (
            <button key={s || 'all'} onClick={() => setParam('status', s)} className={cx('shrink-0 rounded-md px-2.5 py-1 text-sm', status === s ? 'bg-white/[.08]' : 'text-muted hover:text-fg')}>{s || 'all'}</button>
          ))}
        </div>
        <div className="flex gap-1 rounded-lg border border-line bg-card p-1">
          <button onClick={() => setParam('liked', liked ? '' : 'true')} className={cx('shrink-0 rounded-md px-2.5 py-1 text-sm', liked ? 'bg-rose-400/10 text-rose-300' : 'text-muted hover:text-fg')}>♥ Liked</button>
          <button onClick={() => setParam('returning', returning ? '' : 'true')} className={cx('shrink-0 rounded-md px-2.5 py-1 text-sm', returning ? 'bg-accept/10 text-accept' : 'text-muted hover:text-fg')}>Returning</button>
        </div>
        <form className="flex-1" onSubmit={e => { e.preventDefault(); setParam('q', text) }}>
          <input className={inputCls} placeholder="Search name or email, then press Enter" value={text} onChange={e => setText(e.target.value)} />
        </form>
      </div>
      {list.loading && <Loading />}
      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      {list.data && list.data.length === 0 && <Empty title="No applicants match these filters." />}
      {list.data && list.data.length > 0 && (
        <Card pad={false} className="overflow-hidden">
          <div className="hidden grid-cols-[2rem_minmax(0,1.3fr)_7rem_8rem_8rem_9rem_minmax(0,2fr)_5rem] gap-4 border-b border-line px-4 py-2.5 font-mono text-[11px] uppercase tracking-[0.12em] text-muted md:grid">
            <span /><span>Name</span><span>Past events</span><span>Category</span><span>Status</span><span>Score</span><span>Top reason</span><span className="text-right">When</span>
          </div>
          {list.data.map(a => (
            <Link key={a.id} to={`/c/${slug}/applicants/${a.id}`} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] gap-x-4 gap-y-1.5 border-b border-line/70 px-4 py-3 last:border-0 hover:bg-white/[.03] md:grid-cols-[2rem_minmax(0,1.3fr)_7rem_8rem_8rem_9rem_minmax(0,2fr)_5rem] md:items-center">
              <span><LikeButton small id={a.id} liked={!!a.liked} onChange={v => list.setData(xs => (xs ?? []).map(y => y.id === a.id ? { ...y, liked: v } : y))} /></span>
              <span className="flex min-w-0 items-center gap-2 truncate text-sm">{a.name}{a.decision_source === 'lead' && <Tag className="h-5 px-1.5 text-[10px]">lead</Tag>}{a.reconsidered && <Tag tone="accept" className="h-5 px-1.5 text-[10px]">re-checked</Tag>}</span>
              <span className="flex flex-wrap gap-1 max-md:col-span-3 max-md:col-start-2">{a.attended ? <Tag tone="accept" className="h-5 px-1.5 text-[10px]">{a.attended} attended</Tag> : null}{a.no_show ? <Tag tone="ask" className="h-5 px-1.5 text-[10px]">{a.no_show} no-show</Tag> : null}{!a.attended && !a.no_show && <span className="font-mono text-xs text-faint max-md:hidden">new</span>}</span>
              <span className="truncate font-mono text-xs text-muted md:order-none">{a.category}</span>
              <span className="md:order-none"><StatusBadge status={a.status} /></span>
              <ScoreBar value={a.final_score} className="max-md:hidden" />
              <span className="col-span-2 col-start-2 truncate text-sm text-muted md:col-span-1 md:col-start-auto">{a.top_reason}</span>
              <span className="hidden text-right font-mono text-xs text-muted md:block">{timeAgo(a.created_at)}</span>
            </Link>
          ))}
        </Card>
      )}
    </div>
  )
}
