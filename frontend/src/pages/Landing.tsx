import { Link } from 'react-router-dom'
import { api } from '../api'
import type { EvalVariant } from '../api'
import { useAsync } from '../hooks'
import { LlmBadge } from '../components/Layout'
import { Card, Label, pct } from '../components/ui'

const SLUG = 'grok-night-london'

const STEPS = [
  ['01', 'Apply', 'Applicants fill in the public form for a community: who they are, their GitHub, Devpost and chat handles, what they build, and which category they want.'],
  ['02', 'Score', 'Every application is checked against the community’s written rules plus public evidence from GitHub, Devpost and StopForumSpam. An LLM writes rule-by-rule reasoning (via Cursor, Gemini 3.7 Flash), and a history model trained on this lead’s past decisions adjusts the call.'],
  ['03', 'Route', 'Accept, ask (the lead’s review queue) or decline, always with reasons. Category quotas hold seats per group; once a category is full, applicants are waitlisted by score.'],
  ['04', 'Share', 'A scammer reported in one community is stopped in the next, via a hashed cross-community blocklist with appeals. Minor declines are re-checked after a cool-down; scams never are.'],
] as const

const DEMO = [
  ['Apply as a builder', 'The public application form.', `/apply/${SLUG}`],
  ['Clear the review queue', 'Borderline cases, one card at a time, keyboard shortcuts.', `/c/${SLUG}/queue`],
  ['See the scammer blocked from another community', 'Confirmed report from Shoreditch Builders Club, shared by hash.', `/c/${SLUG}/blocklist`],
  ['Evaluation', 'Rules only vs rules + history model, with the trade-offs.', `/c/${SLUG}/eval`],
] as const

export function LandingPage() {
  const health = useAsync(() => api.health(), [])
  const report = useAsync(() => api.evalReport(), [])
  const variants: EvalVariant[] = report.data?.variants ?? []
  const rules = variants[0]
  const hist = variants[variants.length - 1]
  return (
    <div className="min-h-screen bg-bg text-fg">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="grid h-7 w-7 place-items-center rounded-full border border-fg/80"><span className="h-2.5 w-2.5 rounded-full bg-fg" /></span>
          <span className="font-mono text-[12px] uppercase tracking-[0.2em]">Gatekeeper</span>
        </Link>
        <Link to={`/c/${SLUG}/queue`} className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-white/[.04]">Open lead view</Link>
      </header>

      <main className="mx-auto max-w-6xl px-5 pb-20">
        <section className="py-14 sm:py-20">
          <Label>Track 1 · Vetting &amp; moderation</Label>
          <h1 className="mt-4 max-w-3xl text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">
            Gatekeeper — vet applicants, keep scammers out, share a blocklist across communities.
          </h1>
          <p className="mt-5 max-w-2xl text-base text-muted sm:text-lg">
            Community leads hand-read every application, and a scammer kicked out of one group simply joins the next.
          </p>
        </section>

        <section>
          <Label>How it works</Label>
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
            {STEPS.map(([n, title, body]) => (
              <Card key={n}>
                <div className="font-mono text-[11px] text-muted">{n}</div>
                <div className="mt-2 text-base font-medium">{title}</div>
                <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
              </Card>
            ))}
          </div>
        </section>

        <section className="mt-14">
          <Label>Try the demo · Grok Night London</Label>
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
            {DEMO.map(([title, sub, to], i) => (
              <Link key={to} to={to} className="group flex items-start gap-4 rounded-xl border border-line bg-card p-5 transition-colors hover:bg-white/[.04]">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-line font-mono text-[12px]">{i + 1}</span>
                <span className="min-w-0">
                  <span className="block font-medium">{title} <span className="text-muted transition-colors group-hover:text-fg">→</span></span>
                  <span className="mt-1 block text-sm text-muted">{sub}</span>
                </span>
              </Link>
            ))}
          </div>
        </section>

        <section className="mt-14 flex flex-col gap-4 rounded-xl border border-line px-5 py-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">Synthetic test set{report.data ? ` · ${rules?.n ?? 150} applicants` : ''}</span>
            {rules && hist ? <>
              <span>Real people wrongly declined <span className="font-mono">{pct(rules.false_block_rate)} → {pct(hist.false_block_rate)}</span></span>
              <span>Accuracy on auto-decided <span className="font-mono">{pct(rules.accuracy_on_decided)} → {pct(hist.accuracy_on_decided)}</span></span>
              <span className="text-muted">Sent to lead <span className="font-mono">{pct(rules.ask_rate)} → {pct(hist.ask_rate)}</span></span>
            </> : <span className="text-muted">{report.error ? 'Evaluation report unavailable' : 'Loading evaluation…'}</span>}
          </div>
          <div className="shrink-0 whitespace-nowrap [&>span]:inline-flex"><LlmBadge health={health.data ?? null} /></div>
        </section>
      </main>
    </div>
  )
}
