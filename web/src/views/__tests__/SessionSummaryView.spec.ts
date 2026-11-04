import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() } }))
const replace = vi.fn()
vi.mock('vue-router', async (orig) => ({ ...(await orig<typeof import('vue-router')>()), useRouter: () => ({ push: vi.fn(), replace }) }))
import { api } from '@/api'
import SessionSummaryView from '../SessionSummaryView.vue'
import { useSettingsStore } from '@/stores/settings'
import { profile } from '@/mocks/fixtures'
import type { SessionSummary } from '@/api/types'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>
const del = vi.mocked(api.DELETE) as unknown as ReturnType<typeof vi.fn>

const moves = [
  { name: 'Swing', reps: 10, seconds: null, weight_kg: 11.3398 },
  { name: 'Goblet squat', reps: 12, seconds: null, weight_kg: 11.3398 },
]
function summary(o: Partial<SessionSummary> = {}, session: Partial<SessionSummary['session']> = {}): SessionSummary {
  return {
    session: {
      id: 3, plan_id: 1, plan: { name: 'Swing circuit', format: 'amrap', cap_min: 20, emom_min: null, rounds: null, moves, video_url: null },
      weight_kg: 11.3398, start_utc: '2026-11-03T18:00:00Z', end_utc: '2026-11-03T18:21:00Z', events: [], rounds_done: 3, partial_moves: 2,
      fell_short: [], active_s: 1260, overtime_s: 60, created_at: '2026-11-03T18:21:00Z', ...session,
    },
    matched_workout_id: 's1', avg_hr: 131.4, effort: 5, effort_source: 'watch', effort_estimated: false,
    moves: [{ name: 'Swing', avg_hr: 140.2, instances: 3 }, { name: 'Goblet squat', avg_hr: 126, instances: 3 }],
    rounds: [{ round: 1, time_s: 300, moves: 2, avg_hr: 120 }, { round: 2, time_s: 310, moves: 2, avg_hr: 132 }],
    zone_seconds: [60, 300, 600, 200, 100], zone_bounds_bpm: [100, 120, 140, 160], fell_short: [], ...o,
  }
}

async function mountIt(sm: SessionSummary | null, status = 500) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile({}, { units: 'imperial' }) as never
  get.mockResolvedValue(sm ? { data: sm, response: { status: 200 } } : { data: undefined, response: { status } })
  const w = mount(SessionSummaryView, { props: { id: '3' }, global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return w
}
const t = (w: ReturnType<typeof mount>, id: string) => w.get(`[data-testid="${id}"]`).text()

describe('SessionSummaryView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the headline figures, HR per move, zones and the round table for a matched session', async () => {
    const w = await mountIt(summary())
    expect(get).toHaveBeenCalledWith('/api/v1/sessions/{session_id}/summary', { params: { path: { session_id: 3 } } })
    expect(t(w, 'summary-title')).toBe('Swing circuit')
    expect(t(w, 'summary-sub')).toContain('AMRAP · 20 min')
    expect(t(w, 'fig-rounds')).toBe('3 rounds + 2 moves')
    expect(t(w, 'fig-time')).toBe('21:00')
    expect(t(w, 'fig-overtime')).toBe('+1:00')
    expect(t(w, 'fig-bell')).toBe('25 lb')
    expect(t(w, 'fig-hr')).toBe('131 bpm')
    expect(t(w, 'fig-effort')).toBe('5 / 10')
    expect(t(w, 'effort-source')).toBe('from your watch')
    const bars = w.findAll('[data-testid="move-bar"]')
    expect(bars.map((b) => b.text())).toEqual(['Swing140 bpm', 'Goblet squat126 bpm'])
    expect(w.findAll('[data-testid="zone-row"]')).toHaveLength(5)
    const rows = w.findAll('[data-testid="round-row"]').map((r) => r.findAll('th, td').map((c) => c.text()))
    expect(rows).toEqual([['1', '5:00', '120'], ['2', '5:10', '132']])
  })

  it('has no picker when the watch gave the effort', async () => {
    const w = await mountIt(summary())
    expect(w.find('[data-testid="effort-picker"]').exists()).toBe(false)
  })

  it('without a watch workout: no HR sections, dashes, and the effort picker', async () => {
    const w = await mountIt(summary({ matched_workout_id: null, avg_hr: null, effort: null, effort_source: null, moves: [], zone_seconds: null, zone_bounds_bpm: null,
      rounds: [{ round: 1, time_s: 300, moves: 2, avg_hr: null }] }))
    expect(w.find('[data-testid="hr-moves"]').exists()).toBe(false)
    expect(w.find('[data-testid="zones"]').exists()).toBe(false)
    expect(t(w, 'fig-hr')).toBe('—')
    expect(t(w, 'fig-effort')).toBe('—')
    expect(w.find('[data-testid="round-row"]').text()).toContain('—')
    expect(w.findAll('[data-testid^="effort-"]').filter((b) => /^effort-\d+$/.test(b.attributes('data-testid')!))).toHaveLength(10)
  })

  it('saves a manual effort and lets it change', async () => {
    put.mockResolvedValue({ data: { effort: 7 }, response: { status: 200 } })
    const w = await mountIt(summary({ matched_workout_id: null, effort: null, effort_source: null }))
    await w.get('[data-testid="effort-7"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/sessions/{session_id}/effort', { params: { path: { session_id: 3 } }, body: { effort: 7 } })
    expect(t(w, 'fig-effort')).toBe('7 / 10')
    expect(w.get('[data-testid="effort-7"]').attributes('aria-pressed')).toBe('true')
    put.mockResolvedValue({ data: { effort: 4 }, response: { status: 200 } })
    await w.get('[data-testid="effort-4"]').trigger('click')
    await flushPromises()
    expect(t(w, 'fig-effort')).toBe('4 / 10')
  })

  it('puts the old effort back and says so when the save fails', async () => {
    put.mockRejectedValue(new Error('offline'))
    const w = await mountIt(summary({ effort: null, effort_source: null }))
    await w.get('[data-testid="effort-6"]').trigger('click')
    await flushPromises()
    expect(t(w, 'fig-effort')).toBe('—')
    expect(w.get('[data-testid="effort-error"]').text()).toContain('not saved')
  })

  it('offers number buttons for each fell-short minute and saves the choice', async () => {
    put.mockResolvedValue({ data: { '5': 8 }, response: { status: 200 } })
    const w = await mountIt(summary({
      fell_short: [{ minute: 5, move: 'Swings', target_reps: 10, short_reps: null }, { minute: 9, move: 'Swings', target_reps: 10, short_reps: 7 }],
    }, { plan: { name: 'E', format: 'emom', cap_min: null, emom_min: 12, rounds: null, moves, video_url: null } }))
    const rows = w.findAll('[data-testid="short-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('Minute 5 · Swings × 10')
    expect(t(w, 'short-state-5')).toBe('fell short')
    expect(t(w, 'short-state-9')).toBe('Did 7')
    expect([5, 6, 7, 8, 9].every((v) => w.find(`[data-testid="short-5-${v}"]`).exists())).toBe(true)
    expect(w.find('[data-testid="short-5-10"]').exists()).toBe(false)
    await w.get('[data-testid="short-5-8"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/sessions/{session_id}/short', { params: { path: { session_id: 3 } }, body: { '5': 8 } })
    expect(t(w, 'short-state-5')).toBe('Did 8')
  })

  it('takes an Other number for a fell-short minute', async () => {
    put.mockResolvedValue({ data: { '5': 3 }, response: { status: 200 } })
    const w = await mountIt(summary({ fell_short: [{ minute: 5, move: 'Swings', target_reps: 10, short_reps: null }] }))
    await w.get('[data-testid="short-other-5"]').setValue('3')
    await w.get('[data-testid="short-other-save-5"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/sessions/{session_id}/short', { params: { path: { session_id: 3 } }, body: { '5': 3 } })
    expect(t(w, 'short-state-5')).toBe('Did 3')
  })

  it('takes a chosen answer back when it is tapped again', async () => {
    put.mockResolvedValue({ data: {}, response: { status: 200 } })
    const w = await mountIt(summary({ fell_short: [{ minute: 5, move: 'Swings', target_reps: 10, short_reps: 8 }] }))
    await w.get('[data-testid="short-5-8"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/sessions/{session_id}/short', { params: { path: { session_id: 3 } }, body: { '5': null } })
    expect(t(w, 'short-state-5')).toBe('fell short')
  })

  it('says so for an invalid Other value, and clears the field after a good one', async () => {
    put.mockResolvedValue({ data: { '5': 3 }, response: { status: 200 } })
    const w = await mountIt(summary({ fell_short: [{ minute: 5, move: 'Swings', target_reps: 10, short_reps: null }] }))
    await w.get('[data-testid="short-other-5"]').setValue('2.5')
    await w.get('[data-testid="short-other-save-5"]').trigger('click')
    await flushPromises()
    expect(put).not.toHaveBeenCalled()
    expect(t(w, 'short-other-error-5')).toContain('whole number')
    await w.get('[data-testid="short-other-5"]').setValue('3')
    await w.get('[data-testid="short-other-save-5"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="short-other-error-5"]').exists()).toBe(false)
    expect((w.get('[data-testid="short-other-5"]').element as HTMLInputElement).value).toBe('')
  })

  it('an estimated watch effort says so and keeps the picker', async () => {
    const w = await mountIt(summary({ effort: 4, effort_source: 'watch', effort_estimated: true }))
    expect(t(w, 'effort-source')).toBe('estimated by your watch')
    expect(w.find('[data-testid="effort-picker"]').exists()).toBe(true)
  })

  it('shows each zone\'s bpm range', async () => {
    const w = await mountIt(summary())
    const rows = w.findAll('[data-testid="zone-row"]').map((r) => r.get('th').text())
    expect(rows[0]).toBe('Zone 1 · up to 100 bpm')
    expect(rows[1]).toBe('Zone 2 · 100–120 bpm')
    expect(rows[4]).toBe('Zone 5 · over 160 bpm')
  })

  it('says a missing session is gone, with a way back', async () => {
    const w = await mountIt(null, 404)
    expect(t(w, 'summary-missing')).toContain('This session no longer exists.')
    expect(w.find('[data-testid="summary-error"]').exists()).toBe(false)
    expect(w.findAllComponents(RouterLinkStub).some((c) => c.props('to') === '/workouts' && c.attributes('data-testid') === 'summary-missing-back')).toBe(true)
  })

  it('ignores a slow reply from an earlier load', async () => {
    const w = await mountIt(summary())
    let slow!: (v: unknown) => void
    get.mockReturnValueOnce(new Promise((r) => (slow = r)))
    void w.setProps({ id: '4' })
    await flushPromises()
    get.mockResolvedValueOnce({ data: summary({}, { id: 5, plan: { ...summary().session.plan, name: 'Second' } }), response: { status: 200 } })
    void w.setProps({ id: '5' })
    await flushPromises()
    slow({ data: summary({}, { id: 4, plan: { ...summary().session.plan, name: 'First' } }), response: { status: 200 } })
    await flushPromises()
    expect(t(w, 'summary-title')).toBe('Second')
  })

  it('hides the fell-short block when no minute was flagged', async () => {
    const w = await mountIt(summary())
    expect(w.find('[data-testid="short-block"]').exists()).toBe(false)
  })

  it('Do it again starts the same plan with this session\'s bell', async () => {
    const w = await mountIt(summary({}, { weight_kg: 13.6078 }))
    const link = w.findAllComponents(RouterLinkStub).find((c) => (c.props('to') as { path?: string }).path === '/workouts/1/run')!
    expect(link.props('to')).toEqual({ path: '/workouts/1/run', query: { weight: '13.6078' } })
  })

  it('has no Do it again when the plan was deleted', async () => {
    const w = await mountIt(summary({}, { plan_id: null }))
    expect(w.find('[data-testid="do-again"]').exists()).toBe(false)
  })

  it('shows Retry when the summary does not load', async () => {
    const w = await mountIt(null)
    expect(w.find('[data-testid="summary-error"]').exists()).toBe(true)
    get.mockResolvedValue({ data: summary(), response: { status: 200 } })
    await w.get('[data-testid="summary-error"] button').trigger('click')
    await flushPromises()
    expect(t(w, 'summary-title')).toBe('Swing circuit')
  })

  describe('delete this session', () => {
    it('asks first, and Keep it closes the row without deleting', async () => {
      const w = await mountIt(summary())
      expect(t(w, 'session-delete')).toBe('Delete this session')
      await w.get('[data-testid="session-delete"]').trigger('click')
      expect(t(w, 'session-delete-confirm')).toContain("This can't be undone.")
      await w.get('[data-testid="session-delete-no"]').trigger('click')
      expect(w.find('[data-testid="session-delete-confirm"]').exists()).toBe(false)
      expect(del).not.toHaveBeenCalled()
    })

    it('deletes, then goes to /workouts', async () => {
      del.mockResolvedValue({ response: { ok: true, status: 204 } })
      const w = await mountIt(summary())
      await w.get('[data-testid="session-delete"]').trigger('click')
      await w.get('[data-testid="session-delete-yes"]').trigger('click')
      await flushPromises()
      expect(del).toHaveBeenCalledWith('/api/v1/sessions/{session_id}', { params: { path: { session_id: 3 } } })
      expect(replace).toHaveBeenCalledWith('/workouts')
    })

    it('says so and stays on the page when the delete fails', async () => {
      del.mockResolvedValue({ response: { ok: false, status: 500 } })
      const w = await mountIt(summary())
      await w.get('[data-testid="session-delete"]').trigger('click')
      await w.get('[data-testid="session-delete-yes"]').trigger('click')
      await flushPromises()
      expect(t(w, 'session-delete-error')).toBe('That was not deleted. Try again.')
      expect(replace).not.toHaveBeenCalled()
    })
  })
})
