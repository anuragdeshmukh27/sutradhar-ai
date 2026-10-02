import { friendly, type Edge, type PNode, type WsEvent } from './api'

export interface Thought { agent: string; text: string; ts: number }
export interface Approval { node_id: string; title: string; subtitle: string; risk: number; reason: string; failure_modes: string[]; open: boolean }
export interface Diff { failed_node: string; reason: string; added: string[]; removed: string[]; changed: string[]; summary: string }
export interface Toast { id: number; kind: 'error' | 'info' | 'success'; text: string }

export interface State {
  runId: string | null
  phase: 'idle' | 'planning' | 'running' | 'complete' | 'failed'
  nodes: PNode[]
  edges: Edge[]
  ghosts: PNode[] // nodes removed by a re-plan, shown red for a few seconds
  ghostEdges: Edge[]
  flash: Record<string, 'added' | 'changed'>
  summary: string
  approvals: Approval[]
  thoughts: Thought[]
  diff: Diff | null
  tick: number // bumps when ledger / outbox should be refetched
  toasts: Toast[]
  replans: number
  tab: Tab
}
export type Tab = 'premortem' | 'approvals' | 'ledger' | 'feed' | 'outbox'

export const initial: State = {
  runId: null, phase: 'idle', nodes: [], edges: [], ghosts: [], ghostEdges: [], flash: {}, summary: '',
  approvals: [], thoughts: [], diff: null, tick: 0, toasts: [], replans: 0, tab: 'feed',
}

export type Action =
  | { kind: 'start'; runId: string }
  | { kind: 'event'; ev: WsEvent }
  | { kind: 'clearFx' }
  | { kind: 'tab'; tab: Tab }
  | { kind: 'toast'; toast: Omit<Toast, 'id'> }
  | { kind: 'dismiss'; id: number }
  | { kind: 'refreshed' }

let toastId = 1
const mk = (t: Omit<Toast, 'id'>): Toast => ({ ...t, id: toastId++ })

export function reducer(s: State, a: Action): State {
  switch (a.kind) {
    case 'start':
      return { ...initial, runId: a.runId, phase: 'planning', tab: 'feed', toasts: s.toasts }
    case 'tab':
      return { ...s, tab: a.tab }
    case 'toast':
      return { ...s, toasts: [...s.toasts, mk(a.toast)] }
    case 'dismiss':
      return { ...s, toasts: s.toasts.filter((t) => t.id !== a.id) }
    case 'clearFx':
      return { ...s, ghosts: [], ghostEdges: [], flash: {} }
    case 'refreshed':
      return s
    case 'event':
      return onEvent(s, a.ev)
  }
}

function patch(nodes: PNode[], id: string, f: (n: PNode) => Partial<PNode>): PNode[] {
  return nodes.map((n) => (n.id === id ? { ...n, ...f(n) } : n))
}

function onEvent(s: State, { type, data: d, ts }: WsEvent): State {
  switch (type) {
    case 'plan_created':
      return { ...s, nodes: d.nodes, edges: d.edges, phase: 'running' }
    case 'premortem_done': {
      let nodes = s.nodes
      for (const r of d.risks)
        nodes = patch(nodes, r.node_id, () => ({
          risk: r.risk, fail_probability: r.fail_probability, failure_modes: r.failure_modes, mitigation: r.mitigation,
        }))
      return { ...s, nodes, summary: d.summary, tab: 'premortem' }
    }
    case 'node_status':
      return {
        ...s,
        nodes: patch(s.nodes, d.node_id, (n) => ({ status: d.status, error: d.error, risk: d.risk ?? n.risk })),
        tick: s.tick + (d.status === 'done' || d.status === 'flagged' ? 1 : 0),
      }
    case 'tool_call':
      return {
        ...s, tick: s.tick + 1,
        nodes: patch(s.nodes, d.node_id, () => ({ result: { summary: d.summary } })),
      }
    case 'verify_result':
      return s
    case 'approval_needed':
      return {
        ...s, tab: 'approvals',
        approvals: [...s.approvals.filter((x) => x.node_id !== d.node_id), { ...(d as Approval), open: true }],
      }
    case 'replan_diff': {
      const removed = new Set<string>(d.removed)
      const ghosts = s.nodes.filter((n) => removed.has(n.id)).map((n) => ({ ...n, status: 'flagged' as const }))
      const flash: State['flash'] = {}
      for (const i of d.added) flash[i] = 'added'
      for (const i of d.changed) flash[i] = 'changed'
      const ids = new Set<string>([...d.nodes.map((n: PNode) => n.id), ...ghosts.map((g) => g.id)])
      return {
        ...s, nodes: d.nodes, edges: d.edges, ghosts, flash, replans: s.replans + 1, tab: 'feed',
        ghostEdges: s.edges.filter((e) => ids.has(e.source) && ids.has(e.target) && (removed.has(e.source) || removed.has(e.target))),
        diff: { failed_node: d.failed_node, reason: d.reason, added: d.added, removed: d.removed, changed: d.changed, summary: d.summary },
        approvals: s.approvals.map((x) => ({ ...x, open: false })), phase: 'running', tick: s.tick + 1,
      }
    }
    case 'run_complete':
      return { ...s, phase: d.status === 'complete' ? 'complete' : 'failed', tick: s.tick + 1,
        toasts: d.status === 'complete' ? [...s.toasts, mk({ kind: 'success', text: `Run complete: ${d.done}/${d.total} steps done` })] : s.toasts }
    case 'agent_thought':
      return { ...s, thoughts: [...s.thoughts, { agent: d.agent, text: d.text, ts }] }
    case 'error':
      return { ...s, phase: 'failed', toasts: [...s.toasts, mk({ kind: 'error', text: friendly(String(d.message)) })] }
    default:
      return s
  }
}
