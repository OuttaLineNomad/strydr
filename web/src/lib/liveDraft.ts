import type { PlanOut } from '@/api/types'
import type { InputEvent } from './workoutEngine'

const KEY = 'strydr.liveDraft'
const MAX_AGE_MS = 4 * 3600 * 1000

/** A run in progress, kept so a reload, a back swipe or a discarded tab does not lose it. */
export interface LiveDraft {
  planId: number
  plan: PlanOut
  startAt: number
  inputs: InputEvent[]
  weight: number | null
}

export function saveDraft(d: LiveDraft): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(d))
  } catch {
    /* storage unavailable: the run still works, it just cannot resume */
  }
}
export function clearDraft(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* nothing to clear */
  }
}
/** The draft for this plan if it is under 4 h old; a stale or other-plan draft is ignored. */
export function readDraft(planId: number): LiveDraft | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const d = JSON.parse(raw) as LiveDraft
    if (!d || d.planId !== planId || !d.plan || !Array.isArray(d.inputs) || typeof d.startAt !== 'number') return null
    if (Date.now() - d.startAt >= MAX_AGE_MS) return null
    return d
  } catch {
    return null
  }
}
