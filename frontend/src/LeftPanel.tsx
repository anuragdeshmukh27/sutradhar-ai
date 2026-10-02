import { useEffect, useRef, useState } from 'react'
import { api, type Lang } from './api'

const SPEECH: Record<Lang, string> = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' }
const LABEL: Record<Lang, string> = { en: 'English', hi: 'हिन्दी', mr: 'मराठी' }

export interface FormValues { goal: string; budget: number; deadline: string; lang: Lang; demo: boolean }

const SR: any = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition

export function LeftPanel({ busy, onRun, onToast }: {
  busy: boolean
  onRun: (v: FormValues) => void
  onToast: (text: string) => void
}) {
  const [lang, setLang] = useState<Lang>('en')
  const [goals, setGoals] = useState<Record<Lang, string> | null>(null) // sample goals come from the backend scenario file
  const [goal, setGoal] = useState('')
  const [budget, setBudget] = useState(150000)
  const [deadline, setDeadline] = useState('3 weeks')
  const [demo, setDemo] = useState(true)
  const [listening, setListening] = useState(false)
  const rec = useRef<any>(null)

  useEffect(() => {
    api.scenario('techfest').then((sc) => {
      setGoals(sc.goals); setGoal(sc.goals.en); setBudget(sc.budget_inr); setDeadline(sc.deadline)
    }).catch(() => onToast('Could not load the sample goal. Is the backend running?'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const pickLang = (l: Lang) => {
    // swap the sample goal only if the user hasn't typed their own
    if (goals && (Object.values(goals).includes(goal) || !goal.trim())) setGoal(goals[l])
    setLang(l)
  }

  const toggleMic = () => {
    if (listening) { rec.current?.stop(); return }
    const r = new SR()
    r.lang = SPEECH[lang]
    r.interimResults = false
    r.onresult = (e: any) => setGoal(Array.from(e.results).map((x: any) => x[0].transcript).join(' '))
    r.onerror = (e: any) => onToast(e.error === 'network' || e.error === 'service-not-allowed'
      ? 'Mic needs internet. Type your goal instead.'
      : e.error === 'not-allowed' ? 'Mic permission is blocked. Type your goal instead.'
      : e.error === 'no-speech' || e.error === 'aborted' ? 'Did not hear anything. Try again or type your goal.'
      : 'Mic is not available. Type your goal instead.')
    r.onend = () => setListening(false)
    rec.current = r
    setListening(true)
    r.start()
  }

  const label = 'mb-1.5 block text-sm font-semibold uppercase tracking-wide text-mute'
  const input = 'w-full rounded-xl border border-line bg-bg/70 px-3 py-2.5 text-lg text-ink outline-none focus:border-accent'

  return (
    <aside className="flex w-[340px] shrink-0 flex-col gap-4 overflow-y-auto border-r border-line bg-panel/80 p-5">
      <div>
        <label className={label}>Goal</label>
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={6} className={input + ' resize-none leading-snug'} />
      </div>

      <div>
        <label className={label}>Language</label>
        <div className="flex gap-2">
          {(Object.keys(LABEL) as Lang[]).map((l) => (
            <button key={l} onClick={() => pickLang(l)}
              className={`flex-1 rounded-xl border py-2 text-lg font-semibold transition ${lang === l ? 'border-accent bg-accent/20 text-white' : 'border-line text-mute hover:border-accent/60'}`}>
              {LABEL[l]}
            </button>
          ))}
        </div>
        {SR && (
          <button onClick={toggleMic}
            className={`mt-2 w-full rounded-xl border py-2 text-base font-semibold ${listening ? 'animate-pulse border-s-flagged bg-s-flagged/20 text-s-flagged' : 'border-line text-mute hover:border-accent/60'}`}>
            🎤 {listening ? 'Listening… tap to stop' : 'Speak your goal'}
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={label}>Budget ₹</label>
          <input type="number" value={budget} onChange={(e) => setBudget(+e.target.value)} className={input} />
        </div>
        <div>
          <label className={label}>Deadline</label>
          <input value={deadline} onChange={(e) => setDeadline(e.target.value)} className={input} />
        </div>
      </div>

      <label className="flex cursor-pointer items-center justify-between rounded-xl border border-line bg-bg/50 px-4 py-3">
        <span>
          <span className="block text-base font-semibold">Demo mode</span>
          <span className="text-sm text-mute">Replay recorded AI responses (offline)</span>
        </span>
        <span onClick={() => setDemo(!demo)} className={`relative h-7 w-12 rounded-full transition ${demo ? 'bg-accent' : 'bg-line'}`}>
          <span className={`absolute top-0.5 h-6 w-6 rounded-full bg-white transition-all ${demo ? 'left-[22px]' : 'left-0.5'}`} />
        </span>
      </label>

      <button disabled={busy || !goal.trim()} onClick={() => onRun({ goal, budget, deadline, lang, demo })}
        className="mt-auto rounded-2xl bg-gradient-to-r from-accent to-fuchsia-500 py-4 text-xl font-bold text-white shadow-lg transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
        {busy ? 'Working…' : '▶  Run'}
      </button>
    </aside>
  )
}
