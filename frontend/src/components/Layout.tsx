import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import type { CommunityRef, Health, Notification } from '../api'
import { cx, timeAgo } from './ui'

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span className="grid h-7 w-7 place-items-center rounded-full border border-fg/80"><span className="h-2.5 w-2.5 rounded-full bg-fg" /></span>
      <span className="font-mono text-[12px] uppercase tracking-[0.2em]">Gatekeeper</span>
    </Link>
  )
}

export function LlmBadge({ health }: { health: Health | null }) {
  if (!health) return null
  return health.llm.available
    ? <span title={`Rule checks written by ${health.llm.provider} · ${health.llm.model}`} className="hidden items-center gap-1.5 rounded-md border border-line px-2 py-1 font-mono text-[11px] text-muted md:inline-flex"><span className="h-1.5 w-1.5 rounded-full bg-accept/80" />{health.llm.provider} live · {health.llm.model}</span>
    : <span title={health.llm.error ?? undefined} className="hidden items-center gap-1.5 rounded-md border border-ask/25 bg-ask/5 px-2 py-1 font-mono text-[11px] text-ask md:inline-flex"><span className="h-1.5 w-1.5 rounded-full bg-ask/80" />LLM unavailable – rule-only reasoning</span>
}

function Notifications({ slug }: { slug: string }) {
  const [items, setItems] = useState<Notification[]>([])
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const nav = useNavigate()
  const loc = useLocation()
  useEffect(() => {
    let alive = true
    const load = () => api.notifications(slug).then(n => alive && setItems(n)).catch(() => {})
    load()
    const t = setInterval(load, 10000)
    return () => { alive = false; clearInterval(t) }
  }, [slug, loc.pathname])
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const unread = items.filter(i => !i.read).length
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(o => !o)} aria-label="Notifications" className="relative grid h-9 w-9 place-items-center rounded-lg border border-line hover:bg-white/[.04]">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" /></svg>
        {unread > 0 && <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-ask px-1 font-mono text-[10px] font-semibold text-bg">{unread}</span>}
      </button>
      {open && (
        <div className="fade-in absolute right-0 z-30 mt-2 w-[min(360px,calc(100vw-2rem))] overflow-hidden rounded-xl border border-line bg-card shadow-2xl shadow-black/60">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">Lead notifications</span>
            <span className="font-mono text-[11px] text-muted">{unread} unread</span>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 && <div className="px-4 py-6 text-sm text-muted">Nothing needs you right now.</div>}
            {items.slice(0, 30).map(n => (
              <button key={n.id} onClick={() => {
                if (!n.read) api.readNotification(n.id).then(() => setItems(xs => xs.map(x => x.id === n.id ? { ...x, read: true } : x))).catch(() => {})
                if (n.applicant_id) { setOpen(false); nav(`/c/${slug}/applicants/${n.applicant_id}`) }
              }} className={cx('block w-full border-b border-line/60 px-4 py-3 text-left last:border-0 hover:bg-white/[.04]', n.read && 'opacity-50')}>
                <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-muted">
                  <span className={cx('h-1.5 w-1.5 rounded-full', n.kind === 'blocklist_hit' ? 'bg-decline' : n.kind === 'reconsidered' ? 'bg-accept' : 'bg-ask')} />
                  {n.kind.replace('_', ' ')} · {timeAgo(n.created_at)}
                </div>
                <div className="mt-1 text-sm leading-snug">{n.message}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const NAV = [
  ['queue', 'Review queue'], ['applicants', 'Applicants'], ['blocklist', 'Blocklist'], ['settings', 'Rules & quotas'], ['eval', 'Evaluation'], ['moderation', 'Message check'],
] as const

export function LeadLayout() {
  const { slug = '' } = useParams()
  const nav = useNavigate()
  const loc = useLocation()
  const [communities, setCommunities] = useState<CommunityRef[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  useEffect(() => { localStorage.setItem('gk.community', slug) }, [slug])
  useEffect(() => {
    api.communities().then(setCommunities).catch(() => {})
    api.health().then(setHealth).catch(() => {})
  }, [])
  useEffect(() => { window.scrollTo(0, 0) }, [loc.pathname])
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <Logo />
          <span className="hidden h-5 w-px bg-line sm:block" />
          <select value={slug} onChange={e => { const rest = loc.pathname.split('/').slice(3, 4).join('/') || 'queue'; nav(`/c/${e.target.value}/${rest}`) }}
            aria-label="Community (lead login)" className="h-9 min-w-0 max-w-[46vw] truncate rounded-lg border border-line bg-card px-2.5 text-sm outline-none hover:bg-white/[.04] sm:max-w-none">
            {communities.length === 0 && <option value={slug}>{slug}</option>}
            {communities.map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}
          </select>
          <div className="ml-auto flex items-center gap-2">
            <LlmBadge health={health} />
            <a href={`/apply/${slug}`} target="_blank" rel="noreferrer" className="hidden h-9 items-center rounded-lg border border-line px-3 text-sm text-muted hover:bg-white/[.04] hover:text-fg sm:inline-flex">Public form ↗</a>
            <Notifications slug={slug} />
          </div>
        </div>
        <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-3 pb-2 sm:px-5 [scrollbar-width:none]">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={`/c/${slug}/${to}`} className={({ isActive }) => cx('shrink-0 rounded-md px-2.5 py-1.5 text-sm transition-colors', isActive ? 'bg-white/[.07] text-fg' : 'text-muted hover:bg-white/[.04] hover:text-fg')}>{label}</NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6"><Outlet context={{ health }} /></main>
    </div>
  )
}

export function PublicLayout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line">
        <div className="mx-auto flex h-14 max-w-2xl items-center justify-between px-4 sm:px-6">
          <Logo />
          <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">Public</span>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-4 py-10 sm:px-6"><Outlet /></main>
    </div>
  )
}
