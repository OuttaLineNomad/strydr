/**
 * The live-workout engine: a pure replay of a plan plus the runner's timestamped inputs (taps, pauses, an end) into
 * the current state. No timers live here; the view feeds it `now`. Times are wall milliseconds since the workout
 * started (`t_ms`); every timer runs on *active* time, which is wall time minus the paused spans.
 *
 * Auto transitions (a seconds move ending, an EMOM minute turning over, the AMRAP cap ending a rest) are derived
 * from the clock, not stored as inputs. `replay` returns them in the log with kind 'auto' so the saved record has
 * every event. Positions in the log are 0-based and name where the runner was just before the event.
 */
import type { PlanOut } from '@/api/types'

export type PlanShape = Pick<PlanOut, 'format' | 'cap_min' | 'emom_min' | 'rounds' | 'moves'> & { tap_per?: 'move' | 'round' }
export type EventKind = 'next' | 'auto' | 'flag' | 'pause' | 'resume' | 'end'
/** What the runner did. `next` and `flag` are the same tap; the format decides what it means (and is logged as). */
export interface InputEvent {
  t_ms: number
  kind: 'next' | 'flag' | 'pause' | 'resume' | 'end'
  /** Tap per round only: on an `end` during work, how many moves of the round were finished. */
  partial?: number
}
export interface LoggedEvent {
  t_ms: number
  kind: EventKind
  move: number
  round: number
}
export type Phase = 'ready' | 'work' | 'rest' | 'overtime' | 'paused' | 'done'

export interface WorkoutState {
  phase: Phase
  /** The phase underneath a pause (or the phase at the end). */
  base: Exclude<Phase, 'paused' | 'ready'>
  /** 0-based index into plan.moves of the move on screen. */
  move: number
  /** 0-based round (EMOM: which rotation of the moves list). */
  round: number
  /** EMOM: 0-based minute. */
  minute: number
  /** The big clock, in ms: AMRAP countdown then overtime count-up, EMOM time left in the minute, complex elapsed. */
  clockMs: number
  /** Time left on a seconds move, or null for a reps move. */
  moveLeftMs: number | null
  /** Ready: ms until the start. */
  readyMs: number
  fellShort: number[] // 1-based EMOM minutes
  roundsDone: number
  partialMoves: number
  activeMs: number
  /** Rest only: ms of active time since the rest began (round mode counts this up); else 0. */
  restMs: number
  overtimeMs: number
  /** Wall t_ms at which the workout finished (done only). */
  endedMs: number | null
  /** What a tap does now. */
  tap: 'next' | 'flag' | 'start-round' | 'none'
}

export interface Replay {
  state: WorkoutState
  log: LoggedEvent[]
}

export const READY_MS = 5000
const MIN = 60_000

interface Sim {
  a: number // active ms at the last processed point
  wallOffset: number // paused ms before `a`
  pausedAt: number | null // wall t of the open pause
  move: number
  round: number
  moveStartA: number
  rest: boolean
  restA: number // active ms at which the current rest began
  done: boolean
  doneA: number
  doneWall: number
  roundsDone: number
  partial: number
  minute: number
  flags: Set<number>
  log: LoggedEvent[]
}

/** One tap per round (AMRAP and complex only; EMOM advances by itself and ignores it). */
export const roundMode = (p: PlanShape) => p.tap_per === 'round' && p.format !== 'emom'
const capMs = (p: PlanShape) => (p.format === 'amrap' ? (p.cap_min ?? 0) * MIN : Infinity)
const emomMs = (p: PlanShape) => (p.emom_min ?? 0) * MIN
const wallOf = (s: Sim, a: number) => Math.round(a + s.wallOffset)

function log(s: Sim, a: number, kind: EventKind, move = s.move, round = s.round) {
  s.log.push({ t_ms: wallOf(s, a), kind, move, round })
}

function finish(s: Sim, a: number) {
  s.done = true
  s.doneA = a
  s.doneWall = wallOf(s, a)
}

/** Completes the move on screen at active time `a`. */
function completeMove(p: PlanShape, s: Sim, a: number, kind: 'next' | 'auto') {
  log(s, a, kind)
  if (s.move + 1 < p.moves.length) {
    s.move++
    s.moveStartA = a
    return
  }
  s.roundsDone++
  const last = p.format === 'complex' ? s.roundsDone >= (p.rounds ?? 1) : a >= capMs(p)
  if (last) {
    s.partial = 0
    finish(s, a)
  } else {
    s.rest = true
    s.restA = a
  }
}

/** The next time-driven change after the sim's position, or null. */
function nextAuto(p: PlanShape, s: Sim): { a: number; kind: 'move' | 'minute' | 'cap' } | null {
  if (p.format === 'emom') return { a: (s.minute + 1) * MIN, kind: 'minute' }
  if (s.rest) return p.format === 'amrap' ? { a: capMs(p), kind: 'cap' } : null
  if (roundMode(p)) return null // a hold or carry is listed with its seconds; nothing runs on its own
  const m = p.moves[s.move]
  return m?.seconds != null ? { a: s.moveStartA + m.seconds * 1000, kind: 'move' } : null
}

/** Applies every automatic change up to and including active time `until`. */
function runAuto(p: PlanShape, s: Sim, until: number) {
  while (!s.done) {
    const n = nextAuto(p, s)
    if (!n || n.a > until) break
    if (n.kind === 'move') completeMove(p, s, n.a, 'auto')
    else if (n.kind === 'cap') {
      log(s, n.a, 'auto')
      finish(s, n.a)
    } else {
      log(s, n.a, 'auto', s.minute % p.moves.length, Math.floor(s.minute / p.moves.length))
      s.minute++
      if (n.a >= emomMs(p)) {
        s.partial = 0
        finish(s, n.a)
      }
    }
    s.a = Math.max(s.a, n.a)
  }
}

function emomPosition(p: PlanShape, s: Sim) {
  s.move = s.minute % p.moves.length
  s.round = Math.floor(s.minute / p.moves.length)
}

export function replay(plan: PlanShape, inputs: InputEvent[], nowMs: number): Replay {
  const empty: Sim = {
    a: 0, wallOffset: 0, pausedAt: null, move: 0, round: 0, moveStartA: 0, rest: false, restA: 0, done: false, doneA: 0,
    doneWall: 0, roundsDone: 0, partial: 0, minute: 0, flags: new Set(), log: [],
  }
  const s = empty
  const n = plan.moves.length
  const events = inputs.map((e, i) => ({ e, i })).sort((x, y) => x.e.t_ms - y.e.t_ms || x.i - y.i).map((x) => x.e)

  if (nowMs < 0) return { state: snapshot(plan, s, nowMs, 0), log: [] }

  for (const e of events) {
    if (s.done || e.t_ms > nowMs) break
    const a = s.pausedAt != null ? s.a : e.t_ms - s.wallOffset // active time at the event
    if (s.pausedAt == null) runAuto(plan, s, a)
    if (s.done) break
    if (plan.format === 'emom') emomPosition(plan, s)
    if (e.kind === 'pause') {
      if (s.pausedAt != null) continue
      s.a = a
      s.pausedAt = e.t_ms
      log(s, a, 'pause')
    } else if (e.kind === 'resume') {
      if (s.pausedAt == null) continue
      s.wallOffset += e.t_ms - s.pausedAt
      s.pausedAt = null
      log(s, s.a, 'resume')
    } else if (e.kind === 'end') {
      const at = s.pausedAt != null ? s.a : a
      if (s.pausedAt != null) s.wallOffset += e.t_ms - s.pausedAt
      s.pausedAt = null
      log(s, at, 'end')
      if (plan.format === 'emom') {
        s.roundsDone = Math.floor(s.minute / n)
        s.partial = s.minute % n
      } else if (roundMode(plan)) s.partial = s.rest ? 0 : Math.max(0, Math.min(n - 1, Math.floor(e.partial ?? 0)))
      else s.partial = s.rest ? 0 : s.move
      finish(s, at)
    } else if (s.pausedAt != null) {
      // taps while paused do nothing: the view sends a resume
    } else if (plan.format === 'emom') {
      const minute = s.minute + 1
      if (s.flags.has(minute)) s.flags.delete(minute)
      else s.flags.add(minute)
      log(s, a, 'flag')
    } else if (s.rest) {
      log(s, a, 'next')
      s.rest = false
      s.round++
      s.move = 0
      s.moveStartA = a
    } else if (roundMode(plan)) {
      s.move = n - 1 // the tap says the whole round is done
      completeMove(plan, s, a, 'next')
    } else {
      completeMove(plan, s, a, 'next')
    }
    s.a = Math.max(s.a, a)
  }

  if (!s.done && s.pausedAt == null) {
    const a = nowMs - s.wallOffset
    runAuto(plan, s, a)
    if (!s.done) s.a = a
  }
  if (plan.format === 'emom') emomPosition(plan, s)
  return { state: snapshot(plan, s, nowMs, s.a), log: s.log }
}

function snapshot(plan: PlanShape, s: Sim, nowMs: number, a: number): WorkoutState {
  const n = plan.moves.length
  const cap = capMs(plan)
  if (plan.format === 'emom' && s.done) {
    s.roundsDone = Math.floor(s.minute / n)
    s.partial = s.minute % n
    if (s.minute >= (plan.emom_min ?? 0)) s.minute = Math.max(0, (plan.emom_min ?? 1) - 1)
  }
  const activeMs = s.done ? s.doneA : a
  const paused = s.pausedAt != null && !s.done
  const overtime = plan.format === 'amrap' && !s.rest && !s.done && activeMs >= cap
  let base: WorkoutState['base'] = s.done ? 'done' : s.rest ? 'rest' : overtime ? 'overtime' : 'work'
  let phase: Phase = paused ? 'paused' : base
  if (nowMs < 0) {
    phase = 'ready'
    base = 'work'
  }
  let clockMs = activeMs
  if (plan.format === 'amrap') clockMs = Math.abs(cap - activeMs)
  else if (plan.format === 'emom') clockMs = (s.done ? 0 : (s.minute + 1) * MIN - activeMs)
  const restMs = s.rest && !s.done ? Math.max(0, activeMs - s.restA) : 0
  if (roundMode(plan) && s.rest && !s.done) clockMs = restMs
  const m = plan.moves[Math.min(s.move, n - 1)]
  const moveLeftMs = !roundMode(plan) && !s.rest && !s.done && m?.seconds != null && plan.format !== 'emom' ? Math.max(0, s.moveStartA + m.seconds * 1000 - activeMs) : null
  const doneRounds = plan.format === 'emom' && !s.done ? Math.floor(s.minute / n) : s.roundsDone
  const doneMoves = plan.format === 'emom' && !s.done ? s.minute % n : s.done ? s.partial : s.rest ? 0 : s.move
  const tap: WorkoutState['tap'] = phase === 'ready' || phase === 'done' || phase === 'paused' ? 'none' : plan.format === 'emom' ? 'flag' : s.rest ? 'start-round' : 'next'
  return {
    phase, base, move: Math.min(s.move, n - 1), round: s.round, minute: s.minute, clockMs: Math.max(0, clockMs), moveLeftMs,
    readyMs: nowMs < 0 ? -nowMs : 0, fellShort: [...s.flags].sort((x, y) => x - y), roundsDone: doneRounds, partialMoves: doneMoves,
    activeMs, restMs, overtimeMs: plan.format === 'amrap' ? Math.max(0, activeMs - cap) : 0, endedMs: s.done ? s.doneWall : null, tap,
  }
}

/** The next move after the one on screen, for the "Next:" line. Null when the session would end. */
export function nextMoveIndex(plan: PlanShape, st: WorkoutState): number | null {
  const n = plan.moves.length
  if (plan.format === 'emom') return (st.minute + 1) * MIN >= emomMs(plan) ? null : (st.minute + 1) % n
  if (st.phase === 'rest') return 0
  if (st.move + 1 < n) return st.move + 1
  if (plan.format === 'complex' && st.roundsDone + 1 >= (plan.rounds ?? 1)) return null
  if (plan.format === 'amrap' && st.phase === 'overtime') return null
  return 0
}

/** "3 rounds + 2 moves", "1 round", "2 moves". */
export function roundsText(rounds: number, partial: number): string {
  const r = `${rounds} ${rounds === 1 ? 'round' : 'rounds'}`
  const p = `${partial} ${partial === 1 ? 'move' : 'moves'}`
  if (partial > 0 && rounds > 0) return `${r} + ${p}`
  return partial > 0 ? p : r
}

/** Steps a bell weight to the next common bell: 5 lb steps (imperial) or 2 kg steps (metric). Result in kg. */
export function stepBell(kg: number, dir: 1 | -1, system: 'imperial' | 'metric'): number {
  const LB = 2.2046226218
  const unit = system === 'imperial' ? LB : 1
  const step = system === 'imperial' ? 5 : 2
  const x = (kg * unit) / step
  const eps = 0.01 // stored kg carries rounding from the lb the runner typed
  const k = dir > 0 ? Math.floor(x + eps) + 1 : Math.ceil(x - eps) - 1
  if (dir < 0 && k < 1) return kg // already at the lightest step: never go heavier on Lighter
  return (Math.max(1, k) * step) / unit
}

/**
 * The index in `inputs` of the tap that Back would remove, or null. Only a `next` or `flag` tap is removable (pause and
 * resume never are), and only while the workout is running or paused, and only when nothing automatic (a timed move
 * ending, an EMOM minute turning, the AMRAP cap) happened after that tap: undoing past it would rewrite played time.
 */
export function undoable(plan: PlanShape, inputs: InputEvent[], nowMs: number): number | null {
  if (nowMs < 0) return null
  const { state, log } = replay(plan, inputs, nowMs)
  if (state.phase === 'done' || state.phase === 'ready') return null
  let idx = -1
  for (let i = 0; i < inputs.length; i++) {
    const e = inputs[i]!
    if ((e.kind === 'next' || e.kind === 'flag') && e.t_ms <= nowMs && (idx < 0 || e.t_ms >= inputs[idx]!.t_ms)) idx = i
  }
  if (idx < 0) return null
  let lastTap = -1
  for (let i = 0; i < log.length; i++) if (log[i]!.kind === 'next' || log[i]!.kind === 'flag') lastTap = i
  if (lastTap < 0) return null // the tap was ignored (for example while paused), so there is nothing to undo
  for (let i = lastTap + 1; i < log.length; i++) if (log[i]!.kind === 'auto') return null
  return idx
}

/** The inputs without the one at `i`. */
export function withoutInput(inputs: InputEvent[], i: number): InputEvent[] {
  return inputs.filter((_, j) => j !== i)
}
