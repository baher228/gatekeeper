import { useState } from 'react'
import { api } from '../api'
import { Button, Card, Label, PageHeader, StatusBadge, inputCls } from '../components/ui'

const SAMPLE = 'URGENT! You have won a guaranteed £1000 cash prize. To claim, text WIN to 87121 now. T&C apply.'

export default function MessageCheckPage() {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [res, setRes] = useState<Awaited<ReturnType<typeof api.checkMessage>> | null>(null)
  const [copied, setCopied] = useState(false)
  const run = async () => { setBusy(true); setErr(null); setCopied(false); try { setRes(await api.checkMessage(text)) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) } }
  return (
    <div>
      <PageHeader label="Moderation · message check" title="Is this chat message a scam?"
        sub="Paste a message from your WhatsApp or Discord group. A TF-IDF + logistic regression model trained on the UCI SMS Spam Collection scores it and drafts a removal message. You send it yourself." />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="space-y-3">
          <textarea rows={7} className={inputCls} value={text} onChange={e => setText(e.target.value)} placeholder="Paste a message…" />
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" disabled={busy || !text.trim()} onClick={run}>{busy ? 'Scoring…' : 'Check message'}</Button>
            <Button variant="ghost" onClick={() => setText(SAMPLE)}>Use sample</Button>
          </div>
          {err && <p className="text-sm text-decline">{err}</p>}
        </Card>
        <Card>
          {!res ? <p className="text-sm text-muted">The scam probability, the top terms behind it and a drafted removal message will appear here.</p> : (
            <div className="fade-in space-y-4">
              <div className="flex items-center gap-2"><Label>Result</Label><StatusBadge status={res.label === 'spam' ? 'decline' : 'accept'} /></div>
              <div><Label className="mb-1.5">Scam probability</Label><div className="font-mono text-2xl">{(res.scam_probability * 100).toFixed(0)}%</div></div>
              <div className="flex flex-wrap gap-1.5">{res.top_terms.map(t => <span key={t.term} className="rounded-md border border-line px-2 py-0.5 font-mono text-xs">{t.term} <span className={t.weight > 0 ? 'text-decline' : 'text-accept'}>{t.weight > 0 ? '+' : ''}{t.weight.toFixed(2)}</span></span>)}</div>
              {res.label === 'spam' && (
                <div>
                  <Label className="mb-1.5">Draft removal message</Label>
                  <p className="rounded-lg border border-line bg-bg p-3 text-sm">{res.draft_removal}</p>
                  <Button className="mt-2" onClick={() => { navigator.clipboard.writeText(res.draft_removal).then(() => setCopied(true)).catch(() => {}) }}>{copied ? 'Copied' : 'Copy to send'}</Button>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
