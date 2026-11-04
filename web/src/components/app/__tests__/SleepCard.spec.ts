import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import { useWorkoutsStore } from '@/stores/workouts'
import SleepCard from '../SleepCard.vue'
import { formatHours, sleepLine } from '@/lib/sleep'
import type { Sleep } from '@/api/types'

const night: Sleep = {
  night_of: '2026-10-20', total_h: 5.6, deep_h: 0.7, rem_h: 1.0, core_h: 3.9, awake_h: 0.9, bedtime: '00:40', wake: '07:10',
  hours_before_run: 2.5, efficiency_pct: 86, deep_rem_pct: 30, usual_h: 7.1, vs_usual_h: -1.5, quality: 'short', corrected: false, suspicious: false,
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

describe('SleepCard fix', () => {
  const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>
  const del = vi.mocked(api.DELETE) as unknown as ReturnType<typeof vi.fn>
  const late: Sleep = { ...night, total_h: 1.1, suspicious: true }
  function mountIt(sleep: Sleep) {
    const pinia = createPinia()
    setActivePinia(pinia)
    return mount(SleepCard, { props: { sleep, workoutId: 'r1' }, global: { plugins: [pinia] } })
  }
  const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
  function mockGet() {
    get.mockImplementation(async (url: string) => url === '/api/v1/workouts/{workout_id}'
      ? { data: { workout: { workout_id: 'r1' }, sleep: { ...night, total_h: 6.5, corrected: true } }, response: { ok: true, status: 200 } }
      : { data: { recalculating: false }, response: { ok: true, status: 200 } })
  }
  const detailGets = () => get.mock.calls.filter((c) => c[0] === '/api/v1/workouts/{workout_id}').length
  beforeEach(() => vi.clearAllMocks())

  it('flags a late-worn night and offers Fix hours', () => {
    const w = mountIt(late)
    expect(w.get('[data-testid="sleep-flag"]').text()).toContain('watch went on late')
    expect(w.get('[data-testid="sleep-fix"]').text()).toBe('Fix hours')
  })

  it('still lets a normal short night be corrected, without the flag', () => {
    const w = mountIt(night)
    expect(w.find('[data-testid="sleep-flag"]').exists()).toBe(false)
    expect(w.get('[data-testid="sleep-fix"]').text()).toBe('Correct hours')
  })

  it('has no fix control without a run to refresh', () => {
    expect(mount(SleepCard, { props: { sleep: late } }).find('[data-testid="sleep-fix"]').exists()).toBe(false)
  })

  it('saves the hours for the night through PUT', async () => {
    put.mockResolvedValue({ data: { local_date: '2026-10-20', hours: 6.5 }, response: { ok: true, status: 200 } })
    const w = mountIt(late)
    const store = useWorkoutsStore()
    store.detail = { workout: { workout_id: 'r1' } } as unknown as typeof store.detail
    mockGet()
    await w.get('[data-testid="sleep-fix"]').trigger('click')
    await w.get('[data-testid="sleep-hours"]').setValue('6.5')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(detailGets()).toBe(1)
    expect(store.detail?.sleep?.total_h).toBe(6.5)
    expect(put).toHaveBeenCalledWith('/api/v1/sleep/{local_date}/correction', {
      params: { path: { local_date: '2026-10-20' } }, body: { hours: 6.5 },
    })
  })

  it('does not show an earlier error when the form reopens', async () => {
    const w = mountIt(late)
    useWorkoutsStore().sleepError = 'The hours were not saved. Try again.'
    await w.get('[data-testid="sleep-fix"]').trigger('click')
    expect(w.find('[data-testid="sleep-error"]').exists()).toBe(false)
  })

  it('rejects hours out of range inline without calling the API', async () => {
    const w = mountIt(late)
    await w.get('[data-testid="sleep-fix"]').trigger('click')
    for (const bad of ['0', '20', '']) {
      await w.get('[data-testid="sleep-hours"]').setValue(bad)
      await w.get('form').trigger('submit')
      expect(w.get('[data-testid="sleep-error"]').text()).toContain('0.5 to 14')
    }
    expect(put).not.toHaveBeenCalled()
  })

  it('shows the server error when the save is refused', async () => {
    put.mockResolvedValue({ data: undefined, response: { ok: false, status: 422 } })
    const w = mountIt(late)
    await w.get('[data-testid="sleep-fix"]').trigger('click')
    await w.get('[data-testid="sleep-hours"]').setValue('6')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.get('[data-testid="sleep-error"]').text()).toContain('0.5 to 14')
  })

  it('marks a corrected night and clears back to the recorded value through DELETE', async () => {
    del.mockResolvedValue({ data: { local_date: '2026-10-20', hours: null }, response: { ok: true, status: 200 } })
    const w = mountIt({ ...night, total_h: 6.5, corrected: true })
    useWorkoutsStore().detail = { workout: { workout_id: 'r1' } } as never
    mockGet()
    expect(w.find('[data-testid="sleep-total"]').text()).toBe('6h 30m')
    expect(w.find('.bar').exists()).toBe(false)
    expect(w.text()).not.toContain('to 07:10')
    expect(w.get('[data-testid="sleep-corrected"]').text()).toBe('Corrected')
    await w.get('[data-testid="sleep-fix"]').trigger('click')
    await w.get('[data-testid="sleep-clear"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/v1/sleep/{local_date}/correction', { params: { path: { local_date: '2026-10-20' } } })
    expect(detailGets()).toBe(1)
  })
})
