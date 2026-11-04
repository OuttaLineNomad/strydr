import type { LastSession, PlanOut } from '@/api/types'
import { roundsText } from './workoutEngine'
import { kgToDisplay, weightUnit, type UnitSystem } from './units'

/** A weight in the runner's units, to one decimal with a trailing ".0" dropped (16 kg is 35.3 lb). */
export function planWeight(kg: number, system: UnitSystem): string {
  return String(Number(kgToDisplay(kg, system).toFixed(1)))
}

export function moveLine(m: PlanOut['moves'][number], system: UnitSystem): string {
  const amount = m.reps != null ? `${m.reps} reps` : `${m.seconds} sec`
  const bell = m.weight_kg == null ? 'bodyweight' : `${planWeight(m.weight_kg, system)} ${weightUnit(system)}`
  return `${m.name}, ${amount}, ${bell}`
}

/** "AMRAP · 20 min · 5 moves · 25 lb" */
export function planSummary(p: PlanOut, system: UnitSystem, withScore = false): string {
  const n = p.moves.length
  const moves = `${n} ${n === 1 ? 'move' : 'moves'}`
  const parts: string[] = []
  if (p.format === 'amrap') parts.push('AMRAP', `${p.cap_min} min`, moves)
  else if (p.format === 'emom') parts.push('EMOM', `${p.emom_min} min`, `${moves} rotating`)
  else parts.push('Complex', `${p.rounds} ${p.rounds === 1 ? 'round' : 'rounds'}`, moves)
  const w = p.moves.map((m) => m.weight_kg).filter((x): x is number => x != null)
  if (!w.length) parts.push('bodyweight')
  else {
    const lo = Math.min(...w)
    const hi = Math.max(...w)
    const u = weightUnit(system)
    parts.push(planWeight(lo, system) === planWeight(hi, system) ? `${planWeight(lo, system)} ${u}` : `${planWeight(lo, system)}–${planWeight(hi, system)} ${u}`)
  }
  if (withScore && p.strength_score != null) parts.push(`Strength ${p.strength_score}`)
  return parts.join(' · ')
}

/** "Last: 4 rounds · Tue" (a weekday inside the past week, a date after that). */
export function lastLine(l: LastSession, now: Date = new Date()): string {
  const d = new Date(l.date)
  const days = (now.getTime() - d.getTime()) / 86_400_000
  const when = days < 6 ? d.toLocaleDateString(undefined, { weekday: 'short' }) : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return `Last: ${roundsText(l.rounds, l.partial_moves)} · ${when}`
}
