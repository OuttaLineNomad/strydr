import { describe, expect, it } from 'vitest'
import { scoreLine, scoreText, shortDate, better, gainLine, headline, roundsFigure, sessionLine } from '../progress'
import type { ProgressSession } from '@/api/types'

function row(o: Partial<ProgressSession> = {}): ProgressSession {
  return {
    id: 1, date: '2026-09-03T18:00:00Z', weight_kg: 11.3398, rounds_done: 4, partial_moves: 0, active_s: 1200, overtime_s: 0, effort: 8,
    missed_reps: null, changed: false, cap_min: 20, target_rounds: null, move_count: 5, ...o,
  }
}
const amrap = { format: 'amrap' as const }
const complex = { format: 'complex' as const }
const emom = { format: 'emom' as const }

describe('headline', () => {
  it('names both bells in the runner units with their efforts', () => {
    const then = row()
    const now = row({ id: 2, date: '2026-11-03T18:00:00Z', weight_kg: 15.8757, effort: 6 })
    expect(headline(then, now, 'imperial')).toMatch(/^35 lb felt 6\/10\. On \d+ Sep, 25 lb felt 8\/10\.$/)
    expect(headline(then, now, 'metric')).toMatch(/^15\.9 kg felt 6\/10\. On \d+ Sep, 11\.3 kg felt 8\/10\.$/)
  })
  it('prints a dash for a missing effort and Bodyweight for no bell', () => {
    expect(headline(row({ weight_kg: null, effort: null }), row({ weight_kg: null, effort: null }), 'imperial')).toMatch(/^Bodyweight felt —\/10\. On \d+ Sep, Bodyweight felt —\/10\.$/)
  })
})

describe('gainLine', () => {
  it('AMRAP: more, fewer, same, partial and a changed cap', () => {
    expect(gainLine(amrap, row({ rounds_done: 4 }), row({ rounds_done: 6 }))).toBe('2 more rounds in the same 20 minutes')
    expect(gainLine(amrap, row({ rounds_done: 6 }), row({ rounds_done: 5 }))).toBe('1 fewer round in the same 20 minutes')
    expect(gainLine(amrap, row({ rounds_done: 6 }), row({ rounds_done: 6 }))).toBe('Same rounds in 20 minutes')
    expect(gainLine(amrap, row({ rounds_done: 4 }), row({ rounds_done: 4, partial_moves: 2 }))).toBe('0.4 more rounds in the same 20 minutes')
    expect(gainLine(amrap, row({ cap_min: 20 }), row({ cap_min: 30 }))).toBe("The time cap changed, so rounds aren't compared.")
  })
  it('shows partial rounds to one decimal only when not whole', () => {
    expect(roundsFigure(row({ rounds_done: 4, partial_moves: 2 }))).toBe('4.4 rounds')
    expect(roundsFigure(row({ rounds_done: 6 }))).toBe('6 rounds')
  })
  it('complex: faster, slower, and unfinished or different rounds', () => {
    const done = { target_rounds: 4, rounds_done: 4 }
    expect(gainLine(complex, row({ ...done, active_s: 860 }), row({ ...done, active_s: 725 }))).toBe('2:15 faster for the same 4 rounds')
    expect(gainLine(complex, row({ ...done, active_s: 700 }), row({ ...done, active_s: 725 }))).toBe('0:25 slower for the same 4 rounds')
    expect(gainLine(complex, row(done), row({ target_rounds: 4, rounds_done: 2 }))).toBe("Rounds differ, so time isn't compared.")
    expect(gainLine(complex, row(done), row({ target_rounds: 5, rounds_done: 5 }))).toBe("Rounds differ, so time isn't compared.")
  })
  it('EMOM: fewer, more, none and unknown', () => {
    expect(gainLine(emom, row({ missed_reps: 10 }), row({ missed_reps: 4 }))).toBe('6 fewer missed reps')
    expect(gainLine(emom, row({ missed_reps: 4 }), row({ missed_reps: 10 }))).toBe('6 more missed reps')
    expect(gainLine(emom, row({ missed_reps: 4 }), row({ missed_reps: 4 }))).toBe('No change in missed reps')
    expect(gainLine(emom, row({ missed_reps: null }), row({ missed_reps: 4 }))).toBe('Answer the fell-short minutes to compare.')
  })
})

describe('better', () => {
  it('higher rounds, shorter time, fewer missed, lower effort and a heavier bell win', () => {
    expect(better('rounds', row({ rounds_done: 4 }), row({ rounds_done: 6 }))).toBe('b')
    expect(better('time', row({ active_s: 800 }), row({ active_s: 700 }))).toBe('b')
    expect(better('missed', row({ missed_reps: 2 }), row({ missed_reps: 9 }))).toBe('a')
    expect(better('effort', row({ effort: 8 }), row({ effort: 6 }))).toBe('b')
    expect(better('bell', row({ weight_kg: 11 }), row({ weight_kg: 16 }))).toBe('b')
  })
  it('marks nothing for ties or missing values', () => {
    expect(better('effort', row({ effort: null }), row({ effort: 6 }))).toBeNull()
    expect(better('rounds', row(), row())).toBeNull()
    expect(better('bell', row({ weight_kg: null }), row({ weight_kg: null }))).toBeNull()
    expect(better('bell', row({ weight_kg: null }), row({ weight_kg: 11 }))).toBe('b')
  })
})

describe('sessionLine', () => {
  it('is bell, rounds and effort', () => {
    expect(sessionLine(row({ rounds_done: 4, partial_moves: 2, effort: 7 }), amrap, 'imperial')).toBe('25 lb · 4 rounds + 2 · effort 7')
    expect(sessionLine(row({ weight_kg: null, effort: null, active_s: 725 }), complex, 'imperial')).toBe('Bodyweight · 12:05 · effort —')
  })
})

describe('shortDate', () => {
  it('adds the year only when it is not the current one', () => {
    const today = new Date(2026, 10, 4)
    expect(shortDate('2026-09-03T12:00:00Z', today)).toBe('3 Sep')
    expect(shortDate('2025-09-03T12:00:00Z', today)).toBe('3 Sep 2025')
  })
})

describe('strength score copy', () => {
  it('prints the change with a plus or a true minus', () => {
    expect(scoreLine(12)).toBe('+12 since the first time')
    expect(scoreLine(-5)).toBe('\u22125 since the first time')
    expect(scoreLine(0)).toBe('No change since the first time')
  })
  it('prints the score, or nothing', () => {
    expect(scoreText(112)).toBe('Strength 112')
    expect(scoreText(null)).toBeNull()
  })
})
