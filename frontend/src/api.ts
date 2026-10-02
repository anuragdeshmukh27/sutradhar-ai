export const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const WS = API.replace(/^http/, 'ws')

export type Status = 'pending' | 'running' | 'done' | 'flagged' | 'awaiting_approval'
export type Lang = 'en' | 'hi' | 'mr'

export interface PNode {
  id: string
  title: string
  subtitle: string
  description: string
  depends_on: string[]
  tool: string
  tool_args: Record<string, unknown>
  success_criteria: string
  est_cost_inr: number
  reversible: boolean
  status: Status
  fail_probability: number | null
  failure_modes: string[]
  mitigation: string
  risk: number | null
  error: string | null
  result?: { summary?: string } | null
}
export interface Edge { source: string; target: string }
export interface Snapshot { nodes: PNode[]; edges: Edge[] }

export interface LedgerRow {
  id: number
  ts: string
  node_id: string
  agent: string
  tool: string
  args: Record<string, unknown>
  result: { summary?: string }
  reversible: boolean
  status: 'done' | 'undone' | 'failed'
}
export interface Outbox {
  emails: { id: number; to: string; subject: string; body: string; status: string }[]
  events: { id: number; title: string; date: string; details: string; status: string }[]
  files: string[]
}
export interface WsEvent { type: string; data: Record<string, any>; ts: number }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API + path, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new Error('Cannot reach the backend on port 8000. Is it running?')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `Request failed (${res.status})`)
  }
  return res.json()
}

const post = (path: string, body?: unknown) =>
  req<any>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  createRun: (b: { goal: string; budget_inr: number; deadline: string; language: Lang; scenario: string }) =>
    post('/runs', b) as Promise<{ run_id: string }>,
  approve: (run: string, node: string) => post(`/runs/${run}/approve/${node}`),
  reject: (run: string, node: string) => post(`/runs/${run}/reject/${node}`),
  injectFailure: (run: string, node_id: string, reason: string) =>
    post(`/runs/${run}/inject-failure`, { node_id, reason }),
  ledger: (run: string) => req<LedgerRow[]>(`/runs/${run}/ledger`),
  outbox: (run: string) => req<Outbox>(`/runs/${run}/outbox`),
  undo: (id: number) => post(`/ledger/${id}/undo`),
  fileUrl: (name: string) => `${API}/files/${encodeURIComponent(name)}`,
}

/** Opens the run's websocket; auto-reconnects (the server replays history on connect). */
export function openSocket(runId: string, onEvent: (e: WsEvent) => void, onState: (up: boolean) => void) {
  let ws: WebSocket | null = null
  let closed = false
  let seen = 0
  const connect = () => {
    ws = new WebSocket(`${WS}/ws/${runId}`)
    let n = 0
    ws.onopen = () => onState(true)
    ws.onmessage = (m) => {
      n++
      if (n <= seen) return // history replay after a reconnect: skip what we already processed
      seen = n
      onEvent(JSON.parse(m.data))
    }
    ws.onclose = () => {
      onState(false)
      if (!closed) setTimeout(connect, 1000)
    }
  }
  connect()
  return () => { closed = true; ws?.close() }
}
