import { useMemo } from 'react'
import { Background, Controls, Handle, Position, ReactFlow, type Edge as RFEdge, type Node as RFNode, type NodeProps } from '@xyflow/react'
import dagre from 'dagre'
import type { PNode } from './api'
import type { State } from './store'
import { STATUS, pct, riskColor } from './theme'

const W = 380
const H = 190

interface Data extends Record<string, unknown> {
  n: PNode
  fx?: 'added' | 'changed' | 'removed'
  onSimulate?: (id: string) => void
}

function TaskNode({ data }: NodeProps<RFNode<Data>>) {
  const { n, fx, onSimulate } = data
  const st = STATUS[n.status]
  const fxClass = fx === 'added' || fx === 'changed' ? 'flash-green' : fx === 'removed' ? 'flash-red' : ''
  return (
    <div
      className={`rounded-2xl border-2 bg-panel px-5 py-4 text-ink shadow-xl ${n.status === 'running' ? 'pulse-ring' : ''} ${fxClass}`}
      style={{ width: W, minHeight: H - 30, borderColor: fx === 'removed' ? '#fb7185' : st.color, transition: 'border-color .3s' }}
    >
      <Handle type="target" position={Position.Left} className="!bg-line !border-0" />
      <div className="flex items-center justify-between gap-2">
        <span className="rounded-full px-3 py-1 text-base font-semibold" style={{ background: st.color + '26', color: st.color }}>
          {st.icon} {st.label}
        </span>
        <span className="rounded-full px-3 py-1 text-base font-bold" style={{ background: riskColor(n.risk) + '26', color: riskColor(n.risk) }}
          title="Pre-mortem risk">
          risk {pct(n.risk)}
        </span>
      </div>
      <div className={`mt-3 text-[26px] font-bold leading-tight ${fx === 'removed' ? 'line-through opacity-70' : ''}`}>{n.title}</div>
      {n.subtitle && n.subtitle !== n.title && <div className="mt-1 text-lg leading-snug text-mute">{n.subtitle}</div>}
      <div className="mt-3 flex items-center justify-between text-base text-mute">
        <span className="rounded bg-panel2 px-2 py-0.5 font-mono">{n.tool}</span>
        <span>{n.est_cost_inr ? `₹${n.est_cost_inr.toLocaleString('en-IN')}` : ''}{!n.reversible && ' · irreversible'}</span>
      </div>
      {n.error && <div className="mt-2 truncate rounded bg-s-flagged/15 px-2 py-1 text-base text-s-flagged" title={n.error}>{n.error}</div>}
      {n.tool === 'book_venue' && onSimulate && !fx && (
        <button
          onClick={() => onSimulate(n.id)}
          className="nodrag mt-2 w-full rounded-lg border border-s-flagged/60 bg-s-flagged/10 py-2 text-base font-semibold text-s-flagged hover:bg-s-flagged/25"
        >
          ⚡ Simulate failure
        </button>
      )}
      <Handle type="source" position={Position.Right} className="!bg-line !border-0" />
    </div>
  )
}

const nodeTypes = { task: TaskNode }

function layout(nodes: PNode[], edges: { source: string; target: string }[]) {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 24, ranksep: 70 })
  g.setDefaultEdgeLabel(() => ({}))
  nodes.forEach((n) => g.setNode(n.id, { width: W, height: H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return (id: string) => {
    const p = g.node(id)
    const x = p?.x - W / 2, y = p?.y - H / 2
    return { x: Number.isFinite(x) ? x : 0, y: Number.isFinite(y) ? y : 0 }
  }
}

export function Graph({ s, onSimulate }: { s: State; onSimulate: (id: string) => void }) {
  const { rfNodes, rfEdges, key } = useMemo(() => {
    const all = [...s.nodes, ...s.ghosts.filter((g) => !s.nodes.some((n) => n.id === g.id))]
    const ids = new Set(all.map((n) => n.id))
    const edges = [...s.edges, ...s.ghostEdges].filter((e) => ids.has(e.source) && ids.has(e.target))
    const pos = layout(all, edges)
    const ghostIds = new Set(s.ghosts.map((g) => g.id))
    const rfNodes: RFNode<Data>[] = all.map((n) => ({
      id: n.id, type: 'task', position: pos(n.id), draggable: false, initialWidth: W, initialHeight: H,
      data: { n, fx: ghostIds.has(n.id) ? 'removed' : s.flash[n.id], onSimulate },
    }))
    const rfEdges: RFEdge[] = edges.map((e) => ({
      id: `${e.source}->${e.target}`, source: e.source, target: e.target, type: 'smoothstep',
      animated: all.find((n) => n.id === e.target)?.status === 'running',
      style: ghostIds.has(e.source) || ghostIds.has(e.target) ? { stroke: '#fb7185', strokeDasharray: '6 4' } : undefined,
    }))
    // remounting on a new node-id set re-runs fitView, so the graph is always framed
    return { rfNodes, rfEdges, key: all.map((n) => n.id).sort().join('|') }
  }, [s.nodes, s.edges, s.ghosts, s.ghostEdges, s.flash, onSimulate])

  return (
    <div className="relative h-full">
      {rfNodes.length === 0 ? <Empty phase={s.phase} /> : (
        <ReactFlow key={key} nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.04 }}
          minZoom={0.15} nodesConnectable={false} proOptions={{ hideAttribution: true }}>
          <Background color="#26325244" gap={28} />
          <Controls showInteractive={false} />
        </ReactFlow>
      )}
      <Legend />
      {s.diff && <DiffBanner s={s} />}
    </div>
  )
}

function Empty({ phase }: { phase: State['phase'] }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-mute">
      <div className="text-6xl">{phase === 'planning' ? '🧠' : '🪔'}</div>
      <div className="text-2xl font-semibold text-ink">{phase === 'planning' ? 'Planning your goal…' : 'Goals in, done out.'}</div>
      <div className="max-w-md text-lg">
        {phase === 'planning' ? 'The Planner agent is drafting a task graph.' : 'Type a goal on the left (English, हिन्दी or मराठी) and press Run. The live task graph appears here.'}
      </div>
    </div>
  )
}

function Legend() {
  return (
    <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-x-4 gap-y-1 rounded-xl border border-line bg-panel/90 px-4 py-2 text-sm backdrop-blur">
      {Object.entries(STATUS).map(([k, v]) => (
        <span key={k} className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-full" style={{ background: v.color }} />
          {v.label}
        </span>
      ))}
    </div>
  )
}

function DiffBanner({ s }: { s: State }) {
  const d = s.diff!
  const name = (id: string) => s.nodes.find((n) => n.id === id)?.subtitle || s.ghosts.find((n) => n.id === id)?.subtitle || id
  return (
    <div className="slide-in absolute right-3 top-3 max-w-md rounded-xl border border-pink-400/60 bg-panel/95 p-4 shadow-2xl backdrop-blur">
      <div className="text-sm font-bold uppercase tracking-wide text-pink-300">↻ Self-healing re-plan</div>
      <div className="mt-1 text-base">{d.summary || `Replaced "${name(d.failed_node)}" and its downstream steps.`}</div>
      <div className="mt-2 flex flex-wrap gap-2 text-sm font-semibold">
        <span className="rounded bg-s-done/20 px-2 py-0.5 text-s-done">+{d.added.length} added</span>
        <span className="rounded bg-s-flagged/20 px-2 py-0.5 text-s-flagged">−{d.removed.length} removed</span>
        <span className="rounded bg-s-await/20 px-2 py-0.5 text-s-await">~{d.changed.length} changed</span>
      </div>
      <div className="mt-1 text-xs text-mute">Completed steps were left untouched.</div>
    </div>
  )
}
