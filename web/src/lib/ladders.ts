import type { MoveIn } from '@/api/types'

export type LadderId = 'push-up' | 'pull-up'

/** Rungs, easiest first. Mirrors LADDERS in backend/strydr/progress.py; a backend test keeps the two equal. */
export const LADDERS: Record<LadderId, string[]> = {
  'push-up': ['Wall', 'Incline', 'Knee', 'Full', 'Decline'],
  'pull-up': ['Negative', 'Band-assisted', 'Full'],
}

export const LADDER_IDS = Object.keys(LADDERS) as LadderId[]

/** "Incline push-up". */
export function rungName(ladder: LadderId, rung: number): string {
  return `${LADDERS[ladder][rung]} ${ladder}`
}

/** The rung alone, "Incline". */
export function rungLabel(ladder: LadderId, rung: number): string {
  return LADDERS[ladder][rung] ?? ''
}

/** A move with the ladder fields set. */
export function isLadderMove(m: Pick<MoveIn, 'ladder' | 'rung'>): m is { ladder: LadderId; rung: number } {
  return m.ladder != null && m.rung != null
}
