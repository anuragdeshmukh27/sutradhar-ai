import type { Status } from './api'

export const STATUS: Record<Status, { label: string; color: string; icon: string }> = {
  pending: { label: 'Pending', color: '#7c8aa8', icon: '○' },
  running: { label: 'Running', color: '#38bdf8', icon: '◔' },
  done: { label: 'Done', color: '#34d399', icon: '✓' },
  flagged: { label: 'Flagged', color: '#fb7185', icon: '⚑' },
  awaiting_approval: { label: 'Awaiting approval', color: '#fbbf24', icon: '✋' },
}

export const riskColor = (r: number | null | undefined) =>
  r == null ? '#7c8aa8' : r >= 0.5 ? '#fb7185' : r >= 0.3 ? '#fbbf24' : '#34d399'

export const pct = (r: number | null | undefined) => (r == null ? '–' : `${Math.round(r * 100)}%`)

export const AGENT_COLOR: Record<string, string> = {
  planner: '#7c8cff', critic: '#f59e0b', executor: '#38bdf8', verifier: '#34d399', replanner: '#f472b6', system: '#9aa8c7',
}
