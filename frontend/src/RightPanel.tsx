import { useEffect, useRef, useState } from 'react'
import { api, type LedgerRow, type Outbox } from './api'
import type { State, Tab } from './store'
import { AGENT_COLOR, pct, riskColor } from './theme'

const TABS: { id: Tab; label: string }[] = [
  { id: 'premortem', label: 'Pre-mortem' },
  { id: 'approvals', label: 'Approvals' },
  { id: 'ledger', label: 'Ledger' },
  { id: 'feed', label: 'Agent feed' },
  { id: 'outbox', label: 'Outbox & Files' },
]

export function RightPanel({ s, setTab, onToast }: { s: State; setTab: (t: Tab) => void; onToast: (t: string) => void }) {
  const pending = s.nodes.filter((n) => n.status === 'awaiting_approval').length
  return (
    <aside className="flex w-[500px] shrink-0 flex-col border-l border-line bg-panel/80">
      <div className="flex flex-nowrap gap-0.5 overflow-x-auto border-b border-line p-2">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`relative whitespace-nowrap rounded-lg px-2.5 py-2 text-[15px] font-semibold transition ${s.tab === t.id ? 'bg-accent/25 text-white' : 'text-mute hover:text-ink'}`}>
            {t.label}
            {t.id === 'approvals' && pending > 0 && (
              <span className="ml-1.5 rounded-full bg-s-await px-1.5 py-0.5 text-xs font-bold text-black">{pending}</span>
            )}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {s.tab === 'premortem' && <Premortem s={s} />}
        {s.tab === 'approvals' && <Approvals s={s} onToast={onToast} />}
        {s.tab === 'ledger' && <Ledger s={s} onToast={onToast} />}
        {s.tab === 'feed' && <Feed s={s} />}
        {s.tab === 'outbox' && <OutboxTab s={s} />}
      </div>
    </aside>
  )
}

const Empty = ({ text }: { text: string }) => <div className="mt-10 text-center text-lg text-mute">{text}</div>

function Premortem({ s }: { s: State }) {
  const rated = s.nodes.filter((n) => n.fail_probability != null).sort((a, b) => (b.risk ?? 0) - (a.risk ?? 0))
  if (!rated.length) return <Empty text="The pre-mortem appears once the plan is drafted." />
  return (
    <div className="flex flex-col gap-3">
      {s.summary && <div className="rounded-xl border border-line bg-panel2 p-3 text-base leading-snug">{s.summary}</div>}
      {rated.map((n) => (
        <div key={n.id} className="slide-in rounded-xl border border-line bg-panel2 p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="font-semibold">{n.subtitle || n.title}</div>
            <span className="font-bold" style={{ color: riskColor(n.risk) }}>{pct(n.risk)}</span>
          </div>
          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-bg">
            <div className="h-full rounded-full transition-all" style={{ width: pct(n.risk), background: riskColor(n.risk) }} />
          </div>
          {n.failure_modes.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-sm text-mute">{n.failure_modes.map((f, i) => <li key={i}>{f}</li>)}</ul>
          )}
          {n.mitigation && <div className="mt-1.5 text-sm"><span className="font-semibold text-s-done">Mitigation: </span>{n.mitigation}</div>}
        </div>
      ))}
    </div>
  )
}

function Approvals({ s, onToast }: { s: State; onToast: (t: string) => void }) {
  const waiting = s.nodes.filter((n) => n.status === 'awaiting_approval')
  const act = async (fn: typeof api.approve, id: string) => {
    try { await fn(s.runId!, id) } catch (e) { onToast((e as Error).message) }
  }
  if (!waiting.length) return <Empty text="Nothing needs your approval right now." />
  return (
    <div className="flex flex-col gap-3">
      {waiting.map((n) => {
        const info = s.approvals.find((a) => a.node_id === n.id)
        return (
          <div key={n.id} className="slide-in rounded-xl border-2 border-s-await/70 bg-panel2 p-4">
            <div className="text-xs font-bold uppercase tracking-wide text-s-await">✋ Approval needed · {info?.reason ?? 'high risk'}</div>
            <div className="mt-1 text-lg font-semibold">{n.title}</div>
            {n.subtitle && <div className="text-sm text-mute">{n.subtitle}</div>}
            <div className="mt-2 text-sm text-mute">{n.description}</div>
            <div className="mt-2 flex gap-4 text-sm">
              <span>Risk <b style={{ color: riskColor(n.risk) }}>{pct(n.risk)}</b></span>
              <span>Cost <b>₹{n.est_cost_inr.toLocaleString('en-IN')}</b></span>
              <span>{n.reversible ? 'Reversible' : <b className="text-s-flagged">Irreversible</b>}</span>
            </div>
            {n.failure_modes.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-mute">{n.failure_modes.map((f, i) => <li key={i}>{f}</li>)}</ul>}
            <div className="mt-3 flex gap-2">
              <button onClick={() => act(api.approve, n.id)} className="flex-1 rounded-lg bg-s-done py-2.5 text-lg font-bold text-black hover:brightness-110">Approve</button>
              <button onClick={() => act(api.reject, n.id)} className="flex-1 rounded-lg border border-s-flagged py-2.5 text-lg font-bold text-s-flagged hover:bg-s-flagged/20">Reject</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function useFetched<T>(s: State, load: (run: string) => Promise<T>, init: T) {
  const [data, setData] = useState<T>(init)
  const [stamp, setStamp] = useState(0)
  useEffect(() => {
    if (!s.runId) { setData(init); return }
    let live = true
    load(s.runId).then((d) => live && setData(d)).catch(() => {})
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.runId, s.tick, stamp])
  return [data, () => setStamp((x) => x + 1)] as const
}

function Ledger({ s, onToast }: { s: State; onToast: (t: string) => void }) {
  const [rows, refresh] = useFetched<LedgerRow[]>(s, api.ledger, [])
  const undo = async (id: number) => {
    try { await api.undo(id); refresh() } catch (e) { onToast((e as Error).message) }
  }
  if (!rows.length) return <Empty text="Every tool action is logged here, with an undo." />
  return (
    <div className="flex flex-col gap-2">
      {[...rows].reverse().map((r) => (
        <div key={r.id} className="rounded-xl border border-line bg-panel2 p-3">
          <div className="flex items-center justify-between">
            <span className="rounded bg-bg px-1.5 py-0.5 font-mono text-sm">{r.tool}</span>
            <span className={`text-xs font-bold uppercase ${r.status === 'done' ? 'text-s-done' : r.status === 'undone' ? 'text-s-await' : 'text-s-flagged'}`}>{r.status}</span>
          </div>
          <div className="mt-1.5 text-sm">{r.result?.summary}</div>
          <div className="mt-2 flex items-center justify-between text-xs text-mute">
            <span>#{r.id} · {r.node_id}</span>
            {r.status === 'done' && r.reversible
              ? <button onClick={() => undo(r.id)} className="rounded-md border border-s-await/70 px-3 py-1 text-sm font-semibold text-s-await hover:bg-s-await/20">↶ Undo</button>
              : r.status === 'done' && <span>irreversible</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function Feed({ s }: { s: State }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [s.thoughts.length])
  if (!s.thoughts.length) return <Empty text="Agent thoughts stream here live." />
  return (
    <div className="flex flex-col gap-2">
      {s.thoughts.map((t, i) => (
        <div key={i} className="slide-in rounded-xl border-l-4 bg-panel2 px-3 py-2" style={{ borderColor: AGENT_COLOR[t.agent] ?? '#9aa8c7' }}>
          <div className="text-xs font-bold uppercase tracking-wide" style={{ color: AGENT_COLOR[t.agent] ?? '#9aa8c7' }}>{t.agent}</div>
          <div className="text-[15px] leading-snug">{t.text}</div>
        </div>
      ))}
      <div ref={end} />
    </div>
  )
}

function OutboxTab({ s }: { s: State }) {
  const [box] = useFetched<Outbox>(s, api.outbox, { emails: [], events: [], files: [] })
  if (!box.emails.length && !box.events.length && !box.files.length) return <Empty text="Emails, calendar events and files appear here." />
  return (
    <div className="flex flex-col gap-3">
      {box.files.length > 0 && <Section title="Files">
        {box.files.map((f) => (
          <a key={f} href={api.fileUrl(f)} download className="flex items-center justify-between rounded-lg border border-line bg-panel2 px-3 py-2.5 hover:border-accent">
            <span className="truncate font-mono text-sm">{f}</span><span className="font-semibold text-accent">⬇ Download</span>
          </a>
        ))}
      </Section>}
      {box.emails.length > 0 && <Section title="Outbox">
        {box.emails.map((e) => (
          <div key={e.id} className={`rounded-lg border border-line bg-panel2 p-3 ${e.status === 'recalled' ? 'opacity-50' : ''}`}>
            <div className="flex justify-between gap-2"><b className="truncate">{e.subject}</b>
              {e.status === 'recalled' && <span className="text-xs font-bold uppercase text-s-await">recalled</span>}</div>
            <div className="text-xs text-mute">to {e.to}</div>
            <div className="mt-1 line-clamp-3 whitespace-pre-line text-sm text-mute">{e.body}</div>
          </div>
        ))}
      </Section>}
      {box.events.length > 0 && <Section title="Calendar">
        {box.events.map((e) => (
          <div key={e.id} className={`rounded-lg border border-line bg-panel2 p-3 ${e.status === 'deleted' ? 'line-through opacity-50' : ''}`}>
            <b>{e.title}</b><div className="text-sm text-mute">{e.date}</div>
          </div>
        ))}
      </Section>}
    </div>
  )
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div><div className="mb-1.5 text-sm font-bold uppercase tracking-wide text-mute">{title}</div><div className="flex flex-col gap-2">{children}</div></div>
)
