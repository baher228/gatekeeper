import type { ReactNode, ButtonHTMLAttributes } from 'react'
import type { Status, Verdict } from '../api'

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

export function Card({ children, className, pad = true }: { children: ReactNode; className?: string; pad?: boolean }) {
  return <div className={cx('rounded-xl border border-line bg-card', pad && 'p-5', className)}>{children}</div>
}

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('font-mono text-[11px] uppercase tracking-[0.12em] text-muted', className)}>{children}</div>
}

export function PageHeader({ label, title, sub, right }: { label: string; title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <Label>{label}</Label>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-1.5 max-w-2xl text-sm text-muted">{sub}</p>}
      </div>
      {right && <div className="flex shrink-0 flex-wrap items-center gap-2">{right}</div>}
    </div>
  )
}

type BtnVariant = 'default' | 'primary' | 'accept' | 'ask' | 'decline' | 'ghost'
const btnStyles: Record<BtnVariant, string> = {
  default: 'border-line bg-raised hover:bg-white/[.06] text-fg',
  primary: 'border-fg bg-fg text-bg hover:bg-white',
  accept: 'border-accept/30 bg-accept/10 text-accept hover:bg-accept/15',
  ask: 'border-ask/30 bg-ask/10 text-ask hover:bg-ask/15',
  decline: 'border-decline/30 bg-decline/10 text-decline hover:bg-decline/15',
  ghost: 'border-transparent bg-transparent text-muted hover:text-fg hover:bg-white/[.04]',
}
export function Button({ variant = 'default', className, children, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant }) {
  return (
    <button {...p} className={cx('inline-flex h-9 items-center justify-center gap-2 rounded-lg border px-3.5 text-sm font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40', btnStyles[variant], className)}>
      {children}
    </button>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-current/30 px-1 font-mono text-[10px] leading-4 opacity-70">{children}</kbd>
}

const statusTone: Record<string, string> = {
  accepted: 'accept', accept: 'accept', ask: 'ask', ask_more: 'ask', waitlisted: 'ask', declined: 'decline', decline: 'decline',
  confirmed: 'decline', pending: 'ask', appealed: 'ask', removed: 'muted', open: 'ask', upheld: 'accept', rejected: 'decline',
}
const toneCls: Record<string, string> = {
  accept: 'text-accept bg-accept/10 border-accept/25', ask: 'text-ask bg-ask/10 border-ask/25',
  decline: 'text-decline bg-decline/10 border-decline/25', muted: 'text-muted bg-white/[.03] border-line',
}
export function StatusBadge({ status, className }: { status: Status | Verdict | string; className?: string }) {
  const tone = statusTone[status] ?? 'muted'
  return <span className={cx('inline-flex h-6 items-center rounded-md border px-2 font-mono text-[11px] uppercase tracking-wider', toneCls[tone], className)}>{status.replace('_', ' ')}</span>
}
export function Tag({ children, tone = 'muted', className, title }: { children: ReactNode; tone?: 'muted' | 'accept' | 'ask' | 'decline'; className?: string; title?: string }) {
  return <span title={title} className={cx('inline-flex h-6 items-center gap-1 rounded-md border px-2 font-mono text-[11px] tracking-wide', toneCls[tone], className)}>{children}</span>
}

export function ScoreBar({ value, className }: { value: number | null | undefined; className?: string }) {
  const v = value ?? 0
  const tone = v >= 0.62 ? 'bg-accept/70' : v <= 0.38 ? 'bg-decline/70' : 'bg-ask/70'
  return (
    <div className={cx('flex items-center gap-2', className)}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[.06]"><div className={cx('h-full rounded-full', tone)} style={{ width: `${Math.round(v * 100)}%` }} /></div>
      <span className="w-9 shrink-0 text-right font-mono text-xs text-muted">{value == null ? '—' : v.toFixed(2)}</span>
    </div>
  )
}

export function QuotaBar({ name, used, quota, bypass, waitlisted }: { name: string; used: number; quota: number; bypass: boolean; waitlisted: number }) {
  const pct = quota > 0 ? Math.min(100, (used / quota) * 100) : 100
  const full = used >= quota
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm">{name}</span>
        <span className={cx('shrink-0 font-mono text-xs', full && !bypass ? 'text-decline' : 'text-muted')}>{used}/{quota}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[.06]"><div className={cx('h-full rounded-full', full && !bypass ? 'bg-decline/60' : 'bg-fg/60')} style={{ width: `${pct}%` }} /></div>
      <div className="mt-1.5 font-mono text-[11px] text-muted">
        {bypass ? 'bypasses quota' : full ? 'full' : `${quota - used} left`}{waitlisted > 0 && ` · ${waitlisted} waitlisted`}
      </div>
    </div>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return <div className="flex items-center gap-3 py-10 text-sm text-muted"><span className="h-3.5 w-3.5 animate-spin rounded-full border border-line border-t-fg" />{label}…</div>
}
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Card className="border-decline/25">
      <Label className="text-decline">Error</Label>
      <p className="mt-2 text-sm">{message}</p>
      {onRetry && <Button className="mt-4" onClick={onRetry}>Retry</Button>}
    </Card>
  )
}
export function Empty({ title, sub }: { title: string; sub?: string }) {
  return (
    <Card className="py-12 text-center">
      <div className="text-sm">{title}</div>
      {sub && <div className="mt-1 text-sm text-muted">{sub}</div>}
    </Card>
  )
}

export const inputCls = 'w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none transition-colors placeholder:text-faint focus:border-white/30'
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-faint">{hint}</span>}
    </label>
  )
}

export const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`)
export const fmtDate = (s: string | null | undefined) => (s ? new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—')
export const timeAgo = (s: string) => {
  const d = (Date.now() - new Date(s).getTime()) / 1000
  if (d < 60) return 'just now'
  if (d < 3600) return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  return `${Math.floor(d / 86400)}d ago`
}
