import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SleepCard from '../SleepCard.vue'
import { formatHours, sleepLine } from '@/lib/sleep'
import type { Sleep } from '@/api/types'

const night: Sleep = {
  night_of: '2026-10-20', total_h: 5.6, deep_h: 0.7, rem_h: 1.0, core_h: 3.9, awake_h: 0.9, bedtime: '00:40', wake: '07:10',
  hours_before_run: 2.5, efficiency_pct: 86, deep_rem_pct: 30, usual_h: 7.1, vs_usual_h: -1.5, quality: 'short',
  rhr_bpm: 61, rhr_usual_bpm: 56, hrv_ms: 38, hrv_usual_ms: 45,
}

describe('SleepCard', () => {
  it('shows hours, stages, usual and the morning readings', () => {
    const w = mount(SleepCard, { props: { sleep: night } })
    expect(w.get('[data-testid="sleep-total"]').text()).toBe('5h 36m')
    expect(w.get('[data-testid="sleep-quality"]').text()).toBe('Short night')
    expect(w.text()).toContain('1h 30m under your usual 7h 06m')
    expect(w.text()).toContain('00:40 to 07:10')
    expect(w.text()).toContain('Deep')
    expect(w.text()).toContain('+5 vs usual')
    expect(w.text()).toContain('-7 vs usual')
  })

  it('says so when no night was recorded', () => {
    expect(mount(SleepCard, { props: { sleep: null } }).get('[data-testid="sleep-na"]').text()).toContain('No sleep')
  })

  it('formats hours for the hero', () => {
    expect(formatHours(0.5)).toBe('30m')
    expect(sleepLine(night)).toBe('5h 36m sleep')
  })
})
