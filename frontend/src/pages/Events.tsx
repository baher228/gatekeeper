import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Card, Empty, ErrorState, Loading, PageHeader, Tag, fmtDate } from '../components/ui'
import { LikeButton } from '../components/Extras'

export default function EventsPage() {
  const { slug = '' } = useParams()
  const ev = useAsync(() => api.events(slug), [slug])
  const setLiked = (id: string, v: boolean) => ev.setData(es => (es ?? []).map(e => ({ ...e, attendees: e.attendees.map(x => x.applicant_id === id ? { ...x, liked: v } : x) })))
  const total = (ev.data ?? []).reduce((n, e) => n + e.attended, 0)
  return (
    <div>
      <PageHeader label="Lead · past events" title="Who came to your events"
        sub="Attendance feeds scoring: returning attendees get +0.05, each no-show −0.05 (capped at −0.15). Like the people you want back." />
      {ev.loading && <Loading />}
      {ev.error && <ErrorState message={ev.error} onRetry={ev.reload} />}
      {ev.data && ev.data.length === 0 && <Empty title="No past events on record yet." />}
      {ev.data && ev.data.length > 0 && <p className="mb-4 font-mono text-xs text-muted">{ev.data.length} events · {total} check-ins</p>}
      <div className="space-y-4">
        {(ev.data ?? []).map(e => (
          <Card key={e.event_name + e.event_date}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div><h2 className="text-lg font-semibold">{e.event_name}</h2><div className="font-mono text-xs text-muted">{fmtDate(e.event_date)}</div></div>
              <div className="flex gap-2"><Tag tone="accept">{e.attended} attended</Tag>{e.no_show > 0 && <Tag tone="ask">{e.no_show} no-show</Tag>}</div>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {e.attendees.map(x => (
                <div key={x.applicant_id} className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5">
                  <LikeButton small id={x.applicant_id} liked={x.liked} onChange={v => setLiked(x.applicant_id, v)} />
                  <Link to={`/c/${slug}/applicants/${x.applicant_id}`} className="min-w-0 flex-1 truncate text-sm hover:underline">{x.name}</Link>
                  <span className={x.status === 'attended' ? 'font-mono text-[11px] text-accept' : 'font-mono text-[11px] text-ask'}>{x.status === 'attended' ? 'attended' : 'no-show'}</span>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
