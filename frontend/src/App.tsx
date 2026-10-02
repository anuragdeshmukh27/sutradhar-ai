import { Component, useCallback, useEffect, useReducer, useState, type ReactNode } from 'react'
import { api, friendly, openSocket } from './api'
import { Graph } from './Graph'
import { LeftPanel, type FormValues } from './LeftPanel'
import { RightPanel } from './RightPanel'
import { initial, reducer } from './store'

class Boundary extends Component<{ children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null }
  static getDerivedStateFromError(e: Error) { return { err: e.message } }
  render() {
    if (!this.state.err) return this.props.children
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
        <div className="text-2xl font-bold">Something glitched.</div>
        <button onClick={() => location.reload()} className="rounded-xl bg-accent px-6 py-3 text-lg font-bold">Reload</button>
      </div>
    )
  }
}

function Dashboard() {
  const [s, dispatch] = useReducer(reducer, initial)
  const [online, setOnline] = useState(true)
  const [starting, setStarting] = useState(false)

  const toast = useCallback((text: string, kind: 'error' | 'info' | 'success' = 'error') =>
    dispatch({ kind: 'toast', toast: { kind, text: kind === 'error' ? friendly(text) : text } }), [])

  // live socket for the current run
  useEffect(() => {
    if (!s.runId) return
    return openSocket(s.runId, (ev) => dispatch({ kind: 'event', ev }), setOnline)
  }, [s.runId])

  // clear re-plan highlight effects after a few seconds
  useEffect(() => {
    if (!s.diff) return
    const t = setTimeout(() => dispatch({ kind: 'clearFx' }), 5000)
    return () => clearTimeout(t)
  }, [s.diff])

  // auto-dismiss toasts
  useEffect(() => {
    if (!s.toasts.length) return
    const id = s.toasts[0].id
    const t = setTimeout(() => dispatch({ kind: 'dismiss', id }), 6000)
    return () => clearTimeout(t)
  }, [s.toasts])

  const run = async (v: FormValues) => {
    setStarting(true)
    try {
      const { run_id } = await api.createRun({
        goal: v.goal, budget_inr: v.budget, deadline: v.deadline, language: v.lang,
        scenario: v.demo ? 'techfest' : 'default',
      })
      dispatch({ kind: 'start', runId: run_id })
    } catch (e) {
      toast((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  const simulate = useCallback(async (nodeId: string) => {
    if (!s.runId) return
    try {
      const r = await api.injectFailure(s.runId, nodeId, 'Venue declined')
      toast(r.mode === 'armed'
        ? 'Failure armed: the venue step will be declined when it runs.'
        : 'Failure triggered: "Venue declined". Re-planning this branch…', 'info')
    } catch (e) { toast((e as Error).message) }
  }, [s.runId, toast])

  const busy = starting || s.phase === 'planning' || s.phase === 'running'
  const done = s.nodes.filter((n) => n.status === 'done').length
  const pct = s.nodes.length ? (done / s.nodes.length) * 100 : 0
  const chip = {
    idle: ['Ready', '#7c8aa8'], planning: ['Planning', '#7c8cff'], running: ['Running', '#38bdf8'],
    complete: ['Complete', '#34d399'], failed: ['Stopped', '#fb7185'],
  }[s.phase]

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-line bg-panel/90 px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="text-3xl">🪔</span>
          <div>
            <div className="text-2xl font-extrabold tracking-tight">Sutradhar <span className="text-accent">AI</span></div>
            <div className="-mt-0.5 text-sm text-mute">Goals in, done out.</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {s.nodes.length > 0 && (
            <div className="flex items-center gap-3 text-base">
              <div className="h-2.5 w-48 overflow-hidden rounded-full bg-bg">
                <div className="h-full rounded-full bg-gradient-to-r from-accent to-s-done transition-all duration-500" style={{ width: `${pct}%` }} />
              </div>
              <span className="font-semibold">{done}/{s.nodes.length} steps</span>
              {s.replans > 0 && <span className="rounded-full bg-pink-400/20 px-2.5 py-0.5 text-sm font-semibold text-pink-300">↻ {s.replans} re-plan</span>}
            </div>
          )}
          {!online && <span className="rounded-full bg-s-await/20 px-3 py-1 text-sm font-semibold text-s-await">reconnecting…</span>}
          <span className="rounded-full px-4 py-1 text-base font-bold" style={{ background: chip[1] + '26', color: chip[1] }}>● {chip[0]}</span>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <LeftPanel busy={busy} onRun={run} onToast={toast} />
        <main className="min-w-0 flex-1"><Graph s={s} onSimulate={simulate} /></main>
        <RightPanel s={s} setTab={(tab) => dispatch({ kind: 'tab', tab })} onToast={toast} />
      </div>

      <div className="pointer-events-none fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 flex-col gap-2">
        {s.toasts.map((t) => (
          <div key={t.id} onClick={() => dispatch({ kind: 'dismiss', id: t.id })}
            className={`slide-in pointer-events-auto cursor-pointer rounded-xl border px-5 py-3 text-lg font-semibold shadow-2xl ${
              t.kind === 'error' ? 'border-s-flagged bg-[#3a1620] text-rose-200'
              : t.kind === 'success' ? 'border-s-done bg-[#0f3226] text-emerald-200' : 'border-accent bg-panel2'}`}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  return <Boundary><Dashboard /></Boundary>
}
