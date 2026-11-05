import { describe, expect, it } from 'vitest'
import { replay, roundsText, stepBell, nextMoveIndex, undoable, withoutInput, type InputEvent, type PlanShape } from '../workoutEngine'

const mv = (name: string, o: { reps?: number; seconds?: number } = { reps: 10 }) => ({ name, reps: o.reps ?? null, seconds: o.seconds ?? null, weight_kg: 11.3398 })
const five = ['A', 'B', 'C', 'D', 'E'].map((n) => mv(n))
const amrap = (cap = 20, moves = five): PlanShape => ({ format: 'amrap', cap_min: cap, emom_min: null, rounds: null, moves })
const emom = (min = 12, n = 3): PlanShape => ({ format: 'emom', cap_min: null, emom_min: min, rounds: null, moves: five.slice(0, n) })
const complex = (rounds = 4, moves = five): PlanShape => ({ format: 'complex', cap_min: null, emom_min: null, rounds, moves })
const taps = (...ts: number[]): InputEvent[] => ts.map((t_ms) => ({ t_ms, kind: 'next' }))
const S = 1000

describe('ready', () => {
  it('counts the get-ready time down before the start', () => {
    const r = replay(amrap(), [], -3000)
    expect(r.state.phase).toBe('ready')
    expect(r.state.readyMs).toBe(3000)
  })
})

describe('AMRAP', () => {
  it('shows rest after the last move; the next tap starts round 2', () => {
    const t = [1, 2, 3, 4, 5].map((n) => n * S)
    let r = replay(amrap(), taps(...t.slice(0, 4)), 5 * S)
    expect(r.state).toMatchObject({ phase: 'work', move: 4, round: 0, roundsDone: 0, partialMoves: 4 })
    r = replay(amrap(), taps(...t), 6 * S)
    expect(r.state).toMatchObject({ phase: 'rest', roundsDone: 1, tap: 'start-round', clockMs: 20 * 60 * S - 6 * S })
    r = replay(amrap(), taps(...t, 7 * S), 8 * S)
    expect(r.state).toMatchObject({ phase: 'work', move: 0, round: 1, roundsDone: 1 })
  })

  it('goes to overtime at the cap and the last tap of that round ends it', () => {
    // 3 rounds of 5 taps quickly, then moves 1-3 of round 4 before the 2-minute cap
    const cap = 2
    const t = Array.from({ length: 21 }, (_, i) => (i + 1) * 5 * S) // 3 rounds (with rest taps) + 3 moves, to 105 s
    let r = replay(amrap(cap), taps(...t), 106 * S)
    expect(r.state).toMatchObject({ phase: 'work', move: 3, round: 3 })
    r = replay(amrap(cap), taps(...t), 121 * S)
    expect(r.state).toMatchObject({ phase: 'overtime', clockMs: 1 * S, move: 3 })
    expect(replay(amrap(cap), taps(...t), 120 * S).state).toMatchObject({ phase: 'overtime', clockMs: 0 })
    const fin = replay(amrap(cap), taps(...t, 130 * S, 140 * S), 150 * S)
    expect(fin.state).toMatchObject({ phase: 'done', roundsDone: 4, partialMoves: 0, overtimeMs: 20 * S, endedMs: 140 * S })
    // no tap after the end changes anything, and no new round starts
    expect(replay(amrap(cap), taps(...t, 130 * S, 140 * S, 150 * S), 160 * S).state).toMatchObject({ phase: 'done', roundsDone: 4 })
  })

  it('ends at the cap when it hits during rest: no new round', () => {
    const t = [1, 2, 3, 4, 5].map((n) => n * S)
    const r = replay(amrap(1), taps(...t), 90 * S)
    expect(r.state).toMatchObject({ phase: 'done', roundsDone: 1, partialMoves: 0, endedMs: 60 * S, overtimeMs: 0 })
    expect(r.log[r.log.length - 1]).toMatchObject({ kind: 'auto', t_ms: 60 * S })
    // a tap after the cap in rest does not start a round
    expect(replay(amrap(1), taps(...t, 70 * S), 80 * S).state).toMatchObject({ phase: 'done', roundsDone: 1 })
  })

  it('a seconds move counts down and advances itself with an auto event; a tap skips it', () => {
    const moves = [mv('Plank', { seconds: 30 }), mv('Swing')]
    let r = replay(amrap(20, moves), [], 10 * S)
    expect(r.state).toMatchObject({ move: 0, moveLeftMs: 20 * S })
    r = replay(amrap(20, moves), [], 31 * S)
    expect(r.state).toMatchObject({ move: 1, moveLeftMs: null })
    expect(r.log).toEqual([{ t_ms: 30 * S, kind: 'auto', move: 0, round: 0 }])
    r = replay(amrap(20, moves), taps(12 * S), 13 * S)
    expect(r.state).toMatchObject({ move: 1 })
    expect(r.log[0]).toMatchObject({ kind: 'next', t_ms: 12 * S })
  })

  it('a timed last move ends the round on its own and rests', () => {
    const moves = [mv('Swing'), mv('Plank', { seconds: 10 })]
    const r = replay(amrap(20, moves), taps(2 * S), 20 * S)
    expect(r.state).toMatchObject({ phase: 'rest', roundsDone: 1 })
  })
})

describe('EMOM', () => {
  it('rotates moves by minute and advances on its own', () => {
    expect(replay(emom(), [], 10 * S).state).toMatchObject({ move: 0, minute: 0, clockMs: 50 * S, phase: 'work' })
    expect(replay(emom(), [], 61 * S).state).toMatchObject({ move: 1, minute: 1, round: 0, clockMs: 59 * S })
    expect(replay(emom(), [], 4 * 60 * S + 5 * S).state).toMatchObject({ move: 1, minute: 4, round: 1 })
    expect(replay(emom(), [], 61 * S).log).toEqual([{ t_ms: 60 * S, kind: 'auto', move: 0, round: 0 }])
  })

  it('flags a fell-short minute with a tap, and a second tap in the same minute unflags it', () => {
    const at5 = 4 * 60 * S + 20 * S // minute 5 (1-based)
    let r = replay(emom(), [{ t_ms: at5, kind: 'flag' }], at5 + S)
    expect(r.state.fellShort).toEqual([5])
    expect(r.log[r.log.length - 1]).toMatchObject({ kind: 'flag' })
    r = replay(emom(), [{ t_ms: at5, kind: 'flag' }, { t_ms: at5 + 5 * S, kind: 'flag' }], at5 + 6 * S)
    expect(r.state.fellShort).toEqual([])
    // flagged minute stays flagged after the minute turns
    r = replay(emom(), [{ t_ms: at5, kind: 'flag' }], 6 * 60 * S)
    expect(r.state.fellShort).toEqual([5])
  })

  it('ends after the last minute', () => {
    const r = replay(emom(12, 3), [], 13 * 60 * S)
    expect(r.state).toMatchObject({ phase: 'done', roundsDone: 4, partialMoves: 0, endedMs: 12 * 60 * S })
  })

  it('ending mid-way records full rotations plus the partial', () => {
    // 5 whole minutes done on a 3 move list
    const r = replay(emom(12, 3), [{ t_ms: 5 * 60 * S + 10 * S, kind: 'end' }], 6 * 60 * S)
    expect(r.state).toMatchObject({ phase: 'done', roundsDone: 1, partialMoves: 2 })
  })
})

describe('complex', () => {
  it('ends after round N last move; the clock counts up', () => {
    const moves = five.slice(0, 2)
    const t = Array.from({ length: 8 }, (_, i) => (i + 1) * 10 * S) // 4 rounds x 2 moves, but rest taps in between
    // rounds: m1 m2 (rest tap) m1 m2 ...: 4 rounds need 8 move taps + 3 rest taps = 11
    const all = Array.from({ length: 11 }, (_, i) => (i + 1) * 10 * S)
    expect(t.length).toBe(8)
    let r = replay(complex(4, moves), taps(...all.slice(0, 2)), 25 * S)
    expect(r.state).toMatchObject({ phase: 'rest', clockMs: 25 * S, roundsDone: 1 })
    r = replay(complex(4, moves), taps(...all.slice(0, 10)), 110 * S)
    expect(r.state).toMatchObject({ phase: 'work', round: 3, move: 1 })
    r = replay(complex(4, moves), taps(...all), 120 * S)
    expect(r.state).toMatchObject({ phase: 'done', roundsDone: 4, partialMoves: 0, endedMs: 110 * S })
  })
})

describe('pause', () => {
  it('freezes the clocks, records the pause, and excludes it from active time', () => {
    const ev: InputEvent[] = [{ t_ms: 10 * S, kind: 'pause' }, { t_ms: 130 * S, kind: 'resume' }]
    let r = replay(amrap(), ev, 100 * S)
    expect(r.state).toMatchObject({ phase: 'paused', base: 'work', activeMs: 10 * S, clockMs: 20 * 60 * S - 10 * S })
    r = replay(amrap(), ev, 140 * S)
    expect(r.state).toMatchObject({ phase: 'work', activeMs: 20 * S })
    expect(r.log.map((e) => e.kind)).toEqual(['pause', 'resume'])
  })

  it('a timed move does not tick down while paused', () => {
    const moves = [mv('Plank', { seconds: 30 })]
    const ev: InputEvent[] = [{ t_ms: 10 * S, kind: 'pause' }, { t_ms: 70 * S, kind: 'resume' }]
    expect(replay(amrap(20, moves), ev, 70 * S).state).toMatchObject({ move: 0, moveLeftMs: 20 * S })
    expect(replay(amrap(20, moves), ev, 91 * S).state.phase).toBe('rest')
  })

  it('taps while paused are ignored', () => {
    const ev: InputEvent[] = [{ t_ms: 10 * S, kind: 'pause' }, { t_ms: 20 * S, kind: 'next' }]
    expect(replay(amrap(), ev, 30 * S).state).toMatchObject({ phase: 'paused', move: 0 })
  })
})

describe('end early', () => {
  it('keeps the partial round: round 2, move 3 saves 1 round + 2 moves', () => {
    const t = [...[1, 2, 3, 4, 5].map((n) => n * S), 6 * S, 7 * S, 8 * S] // round 1, rest tap, round 2 moves 1-2 -> on move 3
    const r = replay(amrap(), [...taps(...t), { t_ms: 9 * S, kind: 'end' }], 10 * S)
    expect(r.state).toMatchObject({ phase: 'done', roundsDone: 1, partialMoves: 2, endedMs: 9 * S })
    expect(roundsText(r.state.roundsDone, r.state.partialMoves)).toBe('1 round + 2 moves')
  })

  it('ending while paused freezes active time at the pause', () => {
    const ev: InputEvent[] = [{ t_ms: 10 * S, kind: 'pause' }, { t_ms: 50 * S, kind: 'end' }]
    expect(replay(amrap(), ev, 60 * S).state).toMatchObject({ phase: 'done', activeMs: 10 * S, endedMs: 50 * S })
  })

  it('ending in rest counts only the finished round', () => {
    const r = replay(amrap(), [...taps(1 * S, 2 * S, 3 * S, 4 * S, 5 * S), { t_ms: 8 * S, kind: 'end' }], 9 * S)
    expect(r.state).toMatchObject({ roundsDone: 1, partialMoves: 0 })
  })
})

describe('helpers', () => {
  it('steps the bell to the next common bell', () => {
    expect(stepBell(11.3398, 1, 'imperial') * 2.2046226218).toBeCloseTo(30, 3)
    expect(stepBell(11.3398, -1, 'imperial') * 2.2046226218).toBeCloseTo(20, 3)
    expect(stepBell(16, 1, 'metric')).toBe(18)
    expect(stepBell(16, -1, 'metric')).toBe(14)
    expect(stepBell(16, 1, 'imperial') * 2.2046226218).toBeCloseTo(40, 3)
    expect(stepBell(2, -1, 'metric')).toBe(2)
    expect(stepBell(1, -1, 'metric')).toBe(1) // below one step, Lighter never goes heavier
    expect(stepBell(1, -1, 'imperial')).toBe(1)
  })
  it('words rounds and partials', () => {
    expect(roundsText(3, 2)).toBe('3 rounds + 2 moves')
    expect(roundsText(4, 0)).toBe('4 rounds')
    expect(roundsText(0, 1)).toBe('1 move')
  })
  it('names the move after this one', () => {
    const p = amrap()
    expect(nextMoveIndex(p, replay(p, [], 1 * S).state)).toBe(1)
    expect(nextMoveIndex(p, replay(p, taps(1 * S, 2 * S, 3 * S, 4 * S), 5 * S).state)).toBe(0)
  })
})

describe('undoable (Back)', () => {
  const back = (p: PlanShape, inputs: InputEvent[], now: number) => {
    const i = undoable(p, inputs, now)
    return i == null ? null : replay(p, withoutInput(inputs, i), now)
  }
  it('undoes an accidental next and keeps the clock', () => {
    const p = amrap()
    const base = replay(p, taps(1 * S, 2 * S), 5 * S).state
    const r = back(p, taps(1 * S, 2 * S, 4 * S), 5 * S)!
    expect(r.state).toMatchObject({ move: base.move, round: 0, clockMs: base.clockMs })
  })
  it('two backs return to the original move', () => {
    const p = amrap()
    const inputs = taps(1 * S, 2 * S)
    const i1 = undoable(p, inputs, 3 * S)!
    const once = withoutInput(inputs, i1)
    const i2 = undoable(p, once, 3 * S)!
    expect(replay(p, withoutInput(once, i2), 3 * S).state.move).toBe(0)
    expect(undoable(p, withoutInput(once, i2), 3 * S)).toBeNull()
  })
  it('crosses a round boundary back to the last move', () => {
    const p = amrap()
    const t = [1, 2, 3, 4, 5, 6].map((n) => n * S)
    expect(replay(p, taps(...t), 7 * S).state).toMatchObject({ round: 1, move: 0 })
    expect(back(p, taps(...t), 7 * S)!.state).toMatchObject({ phase: 'rest', roundsDone: 1 })
    expect(back(p, taps(...t.slice(0, 5)), 7 * S)!.state).toMatchObject({ round: 0, move: 4 })
  })
  it('removes the latest EMOM flag', () => {
    const p = emom()
    const inputs: InputEvent[] = [{ t_ms: 4 * 60 * S + 5 * S, kind: 'flag' }]
    expect(replay(p, inputs, 4 * 60 * S + 10 * S).state.fellShort).toEqual([5])
    expect(back(p, inputs, 4 * 60 * S + 10 * S)!.state.fellShort).toEqual([])
  })
  it('is null once an auto advance came after the tap', () => {
    const p = amrap(20, [mv('A'), mv('Plank', { seconds: 30 }), mv('C')])
    expect(undoable(p, taps(1 * S), 10 * S)).toBe(0)
    expect(undoable(p, taps(1 * S), 40 * S)).toBeNull()
    const e = emom()
    expect(undoable(e, [{ t_ms: 5 * S, kind: 'flag' }], 61 * S)).toBeNull()
  })
  it('while paused removes the tap before the pause and stays paused', () => {
    const p = amrap()
    const inputs: InputEvent[] = [{ t_ms: 1 * S, kind: 'next' }, { t_ms: 2 * S, kind: 'pause' }]
    const i = undoable(p, inputs, 3 * S)
    expect(i).toBe(0)
    const r = replay(p, withoutInput(inputs, i!), 3 * S)
    expect(r.state).toMatchObject({ phase: 'paused', move: 0 })
    expect(r.log.some((e) => e.kind === 'pause')).toBe(true)
    expect(r.log.some((e) => e.kind === 'next')).toBe(false)
  })
  it('is null with nothing to undo, in Get ready, and after the end', () => {
    const p = amrap()
    expect(undoable(p, [], 3 * S)).toBeNull()
    expect(undoable(p, [{ t_ms: 1 * S, kind: 'pause' }], 3 * S)).toBeNull()
    expect(undoable(p, taps(1 * S), -2 * S)).toBeNull()
    expect(undoable(p, [...taps(1 * S), { t_ms: 2 * S, kind: 'end' }], 3 * S)).toBeNull()
  })
  it('the saved log loses the removed tap', () => {
    const p = amrap()
    const inputs = [...taps(1 * S, 2 * S), { t_ms: 3 * S, kind: 'end' as const }]
    const noEnd = taps(1 * S, 2 * S)
    const i = undoable(p, noEnd, 2.5 * S)!
    const r = replay(p, [...withoutInput(noEnd, i), { t_ms: 3 * S, kind: 'end' }], 4 * S)
    expect(r.log.filter((e) => e.kind === 'next')).toHaveLength(1)
    expect(inputs).toHaveLength(3)
  })
})

describe('tap per round', () => {
  const four = five.slice(0, 4)
  const cx = (rounds = 3, moves = four): PlanShape => ({ ...complex(rounds, moves), tap_per: 'round' })
  const am = (cap = 20, moves = four): PlanShape => ({ ...amrap(cap, moves), tap_per: 'round' })

  it('complex: a tap ends the round into rest (count-up), the next starts round 2, the last tap ends', () => {
    let r = replay(cx(), taps(10 * S), 12 * S)
    expect(r.state).toMatchObject({ phase: 'rest', roundsDone: 1, tap: 'start-round', restMs: 2 * S, clockMs: 2 * S })
    expect(r.log).toEqual([{ t_ms: 10 * S, kind: 'next', move: 3, round: 0 }])
    r = replay(cx(), taps(10 * S, 20 * S), 25 * S)
    expect(r.state).toMatchObject({ phase: 'work', round: 1, roundsDone: 1, restMs: 0, tap: 'next' })
    expect(r.log[1]).toEqual({ t_ms: 20 * S, kind: 'next', move: 3, round: 0 })
    r = replay(cx(), taps(10 * S, 20 * S, 30 * S, 40 * S, 50 * S), 60 * S)
    expect(r.state).toMatchObject({ phase: 'done', roundsDone: 3, partialMoves: 0 })
    expect(r.log.filter((e) => e.kind === 'next').map((e) => e.move)).toEqual([3, 3, 3, 3, 3])
  })

  it('a seconds move runs no timer and never advances on its own', () => {
    const p = cx(3, [mv('Hold', { seconds: 30 }), mv('B')])
    const r = replay(p, [], 5 * 60 * S)
    expect(r.state).toMatchObject({ phase: 'work', move: 0, moveLeftMs: null })
    expect(r.log).toEqual([])
  })

  it('AMRAP: cap mid-round is overtime and the tap finishes it; a round tap past the cap ends', () => {
    const p = am(1)
    let r = replay(p, taps(10 * S, 20 * S), 61 * S)
    expect(r.state).toMatchObject({ phase: 'overtime', base: 'overtime', clockMs: 1 * S })
    r = replay(p, taps(10 * S, 20 * S, 70 * S), 80 * S)
    expect(r.state).toMatchObject({ phase: 'done', roundsDone: 2, partialMoves: 0 })
  })

  it('AMRAP: the cap during rest ends the workout', () => {
    const r = replay(am(1), taps(10 * S), 61 * S)
    expect(r.state).toMatchObject({ phase: 'done', roundsDone: 1, partialMoves: 0 })
    expect(r.log[r.log.length - 1]).toMatchObject({ kind: 'auto' })
  })

  it('End in work carries the stepper count (clamped to n-1); End in rest has no partial', () => {
    const end = (partial: number): InputEvent[] => [...taps(10 * S, 20 * S), { t_ms: 40 * S, kind: 'end', partial }]
    expect(replay(cx(5), end(2), 50 * S).state).toMatchObject({ phase: 'done', roundsDone: 1, partialMoves: 2 })
    expect(replay(cx(5), end(9), 50 * S).state.partialMoves).toBe(3)
    expect(replay(cx(5), end(-4), 50 * S).state.partialMoves).toBe(0)
    expect(replay(cx(5), [...taps(10 * S), { t_ms: 15 * S, kind: 'end', partial: 2 }], 20 * S).state).toMatchObject({ roundsDone: 1, partialMoves: 0 })
    expect(replay(cx(5), [{ t_ms: 15 * S, kind: 'end' }], 20 * S).state).toMatchObject({ roundsDone: 0, partialMoves: 0 })
  })

  it('Back undoes the round tap, and the rest tap', () => {
    const p = cx()
    let inputs = taps(10 * S)
    let i = undoable(p, inputs, 12 * S)!
    expect(i).toBe(0)
    expect(replay(p, withoutInput(inputs, i), 12 * S).state).toMatchObject({ phase: 'work', round: 0, roundsDone: 0 })
    inputs = taps(10 * S, 20 * S)
    i = undoable(p, inputs, 22 * S)!
    expect(replay(p, withoutInput(inputs, i), 22 * S).state).toMatchObject({ phase: 'rest', roundsDone: 1 })
  })

  it('EMOM ignores tap_per, and a plan without it behaves per move', () => {
    const e: PlanShape = { ...emom(), tap_per: 'round' }
    expect(replay(e, [], 70 * S).state).toMatchObject({ minute: 1, move: 1 })
    expect(replay(complex(), taps(1 * S), 2 * S).state).toMatchObject({ phase: 'work', move: 1 })
  })

  it('pauses do not count toward the rest clock', () => {
    const inputs: InputEvent[] = [...taps(10 * S), { t_ms: 12 * S, kind: 'pause' }, { t_ms: 22 * S, kind: 'resume' }]
    expect(replay(cx(), inputs, 25 * S).state).toMatchObject({ phase: 'rest', restMs: 5 * S })
  })
})
