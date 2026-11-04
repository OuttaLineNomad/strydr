import type { PlanProgress, ProgressSession } from '@/api/types'
import { formatClock, weightUnit, type UnitSystem } from './units'
import { planWeight } from './plans'

type Row = ProgressSession
type Plan = PlanProgress['plan']

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "3 Sep", or "3 Sep 2025" when not this year, in the runner's own time zone. */
export function shortDate(iso: string, now: Date = new Date()): string {
  const d = new Date(iso)
  const base = `${d.getDate()} ${MONTHS[d.getMonth()]}`
  return d.getFullYear() === now.getFullYear() ? base : `${base} ${d.getFullYear()}`
}

const finished = (r: Row) => r.target_rounds != null && r.rounds_done >= r.target_rounds

/** Whether the format's measure (rounds at the cap, time for the same rounds) can be compared. EMOM is judged on missed reps. */
export function measureComparable(plan: Pick<Plan, 'format'>, then: Row, now: Row): boolean {
  if (plan.format === 'amrap') return then.cap_min === now.cap_min
  if (plan.format === 'complex') return finished(then) && finished(now) && then.target_rounds === now.target_rounds
  return true
}

/** The bell in the runner's units; a session without one is bodyweight. */
export function bellText(kg: number | null, system: UnitSystem): string {
  return kg == null ? 'Bodyweight' : `${planWeight(kg, system)} ${weightUnit(system)}`
}

/** "6/10", or "—/10" when there is no effort. */
export function effortText(e: number | null): string {
  return `${e == null ? '—' : Number(e.toFixed(1))}/10`
}

/** "35 lb felt 6/10. On 3 Sep, 25 lb felt 8/10." */
export function headline(then: Row, now: Row, system: UnitSystem): string {
  return `${bellText(now.weight_kg, system)} felt ${effortText(now.effort)}. On ${shortDate(then.date)}, ${bellText(then.weight_kg, system)} felt ${effortText(then.effort)}.`
}

/** Rounds with the partial round as a fraction of the moves: 4 + 2/5 is 4.4. */
export function roundsValue(r: Row): number {
  return r.rounds_done + (r.move_count > 0 ? r.partial_moves / r.move_count : 0)
}
const one = (n: number) => String(Number(n.toFixed(1)))

/** "4.4 rounds" or "6 rounds" (one decimal only when it isn't whole). */
export function roundsFigure(r: Row): string {
  const v = Number(roundsValue(r).toFixed(1))
  return `${one(v)} ${v === 1 ? 'round' : 'rounds'}`
}

/** The one line naming the gain, by the format's own measure. */
export function gainLine(plan: Pick<Plan, 'format'>, then: Row, now: Row): string {
  if (plan.format === 'amrap') {
    if (!measureComparable(plan, then, now)) return "The time cap changed, so rounds aren't compared."
    const cap = now.cap_min
    const d = Number((roundsValue(now) - roundsValue(then)).toFixed(1))
    if (d === 0) return `Same rounds in ${cap} minutes`
    const n = one(Math.abs(d))
    return `${n} ${d > 0 ? 'more' : 'fewer'} ${Math.abs(d) === 1 ? 'round' : 'rounds'} in the same ${cap} minutes`
  }
  if (plan.format === 'complex') {
    if (!measureComparable(plan, then, now)) return "Rounds differ, so time isn't compared."
    const d = then.active_s - now.active_s
    if (d === 0) return `Same time for the same ${now.target_rounds} rounds`
    return `${formatClock(Math.abs(d))} ${d > 0 ? 'faster' : 'slower'} for the same ${now.target_rounds} rounds`
  }
  if (then.missed_reps == null || now.missed_reps == null) return 'Answer the fell-short minutes to compare.'
  const d = then.missed_reps - now.missed_reps
  if (d === 0) return 'No change in missed reps'
  return `${Math.abs(d)} ${d > 0 ? 'fewer' : 'more'} missed ${Math.abs(d) === 1 ? 'rep' : 'reps'}`
}

export type Field = 'rounds' | 'time' | 'missed' | 'effort' | 'bell'

/** Which of two sessions is better on a field: 'a', 'b' or null (equal, or not comparable). */
export function better(field: Field, a: Row, b: Row): 'a' | 'b' | null {
  const pick = (x: number | null, y: number | null, higher: boolean): 'a' | 'b' | null => {
    if (x == null || y == null || x === y) return null
    return (x > y) === higher ? 'a' : 'b'
  }
  switch (field) {
    case 'rounds': return pick(Number(roundsValue(a).toFixed(1)), Number(roundsValue(b).toFixed(1)), true)
    case 'time': return pick(a.active_s, b.active_s, false)
    case 'missed': return pick(a.missed_reps, b.missed_reps, false)
    case 'effort': return pick(a.effort, b.effort, false)
    case 'bell': return a.weight_kg == null && b.weight_kg == null ? null : pick(a.weight_kg ?? 0, b.weight_kg ?? 0, true)
  }
}

/** Line 2 of a session row: "25 lb · 4 rounds + 2 · effort 7". */
export function sessionLine(r: Row, plan: Pick<Plan, 'format'>, system: UnitSystem): string {
  const measure = plan.format === 'amrap' ? `${r.rounds_done} ${r.rounds_done === 1 ? 'round' : 'rounds'}${r.partial_moves > 0 ? ` + ${r.partial_moves}` : ''}` : plan.format === 'complex' ? formatClock(r.active_s) : r.missed_reps == null ? 'missed reps unknown' : `${r.missed_reps} missed`
  return [bellText(r.weight_kg, system), measure, r.effort == null ? 'effort —' : `effort ${Number(r.effort.toFixed(1))}`].join(' · ')
}
