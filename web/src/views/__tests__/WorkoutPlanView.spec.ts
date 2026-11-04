import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn() } }))
import { api } from '@/api'
import WorkoutPlanView from '../WorkoutPlanView.vue'
import { useSettingsStore } from '@/stores/settings'
import { profile } from '@/mocks/fixtures'
import type { PlanProgress, ProgressSession } from '@/api/types'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>

const plan: PlanProgress['plan'] = {
  id: 1, name: 'Swing circuit', format: 'amrap', cap_min: 20, emom_min: null, rounds: null, video_url: null, created_at: '', updated_at: '', last_session: null,
  moves: [{ name: 'Swing', reps: 10, seconds: null, weight_kg: 11.3398 }, { name: 'Squat', reps: 12, seconds: null, weight_kg: 11.3398 }],
}
function row(o: Partial<ProgressSession> = {}): ProgressSession {
  return { id: 1, date: '2026-09-03T18:00:00Z', weight_kg: 11.3398, rounds_done: 4, partial_moves: 0, active_s: 1200, overtime_s: 0, effort: 8, missed_reps: null, changed: false, cap_min: 20, target_rounds: null, move_count: 2, ...o }
}
const then = { ...row(), avg_hr: 120 }
const now = { ...row({ id: 2, date: '2026-11-03T18:00:00Z', weight_kg: 15.8757, rounds_done: 6, effort: 6 }), avg_hr: null }

async function mountIt(data: PlanProgress | null, status = 500) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile({}, { units: 'imperial' }) as never
  get.mockResolvedValue(data ? { data, response: { status: 200 } } : { data: undefined, response: { status } })
  const w = mount(WorkoutPlanView, { props: { id: '1' }, global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return w
}
const t = (w: ReturnType<typeof mount>, id: string) => w.get(`[data-testid="${id}"]`).text()

describe('WorkoutPlanView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the headline, gain line, then-vs-now and sessions for two sessions', async () => {
    const w = await mountIt({ plan, sessions: [now, then], then, now })
    expect(get).toHaveBeenCalledWith('/api/v1/plans/{plan_id}/progress', { params: { path: { plan_id: 1 } } })
    expect(t(w, 'plan-title')).toBe('Swing circuit')
    expect(t(w, 'progress-headline')).toMatch(/^35 lb felt 6\/10\. On \d+ Sep, 25 lb felt 8\/10\.$/)
    expect(t(w, 'progress-gain')).toBe('2 more rounds in the same 20 minutes')
    expect(w.get('[data-testid="cmp-rounds"]').findAll('td').map((c) => c.text())).toEqual(['4 rounds', '6 rounds (better)'])
    expect(w.get('[data-testid="cmp-rounds"] td[data-col="now"]').classes()).toContain('win')
    expect(w.get('[data-testid="cmp-effort"] td[data-col="now"]').classes()).toContain('win')
    expect(w.get('[data-testid="cmp-bell"] td[data-col="now"]').classes()).toContain('win')
    expect(w.get('[data-testid="cmp-hr"]').findAll('td').map((c) => c.text())).toEqual(['120 bpm', '—'])
    expect(w.get('[data-testid="cmp-hr"]').findAll('td.win')).toHaveLength(0)
    expect(w.find('[data-testid="progress-changed"]').exists()).toBe(false)
    const rows = w.findAll('[data-testid="session-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('35 lb · 6 rounds · effort 6')
    expect(w.find('[data-testid="plan-start"]').exists()).toBe(true)
  })

  it('notes a changed workout', async () => {
    const w = await mountIt({ plan, sessions: [now, { ...then, changed: true }], then: { ...then, changed: true }, now })
    expect(t(w, 'progress-changed')).toBe('This workout has changed since then.')
  })

  it('keeps the frame and Start with one session', async () => {
    const w = await mountIt({ plan, sessions: [now], then: null, now: null })
    expect(t(w, 'progress-empty')).toBe('Do it once more to see progress.')
    expect(w.find('[data-testid="compare"]').exists()).toBe(false)
    expect(t(w, 'plan-title')).toBe('Swing circuit')
    expect(w.find('[data-testid="plan-start"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="session-row"]')).toHaveLength(1)
  })

  it('says so for an unknown workout', async () => {
    const w = await mountIt(null, 404)
    expect(w.find('[data-testid="plan-missing"]').exists()).toBe(true)
  })

  it('marks no winner on rounds when the cap changed, and hides the hidden text for the unmarked', async () => {
    const w = await mountIt({ plan, sessions: [], then, now: { ...now, cap_min: 30 } })
    expect(t(w, 'progress-gain')).toBe("The time cap changed, so rounds aren't compared.")
    expect(w.get('[data-testid="cmp-rounds"]').findAll('td.win')).toHaveLength(0)
    expect(w.get('[data-testid="cmp-effort"] td.win').text()).toContain('(better)')
  })

  it('shows Time for a complex, with no winner when rounds differ', async () => {
    const cplan = { ...plan, format: 'complex' as const, cap_min: null, rounds: 4 }
    const a = { ...then, cap_min: null, target_rounds: 4, rounds_done: 4, active_s: 860 }
    const b = { ...now, cap_min: null, target_rounds: 4, rounds_done: 4, active_s: 725 }
    let w = await mountIt({ plan: cplan, sessions: [], then: a, now: b })
    expect(w.get('[data-testid="cmp-time"]').findAll('td').map((c) => c.text())).toEqual(['14:20', '12:05 (better)'])
    expect(w.find('[data-testid="cmp-rounds"]').exists()).toBe(false)
    w = await mountIt({ plan: cplan, sessions: [], then: a, now: { ...b, rounds_done: 2 } })
    expect(w.get('[data-testid="cmp-time"]').findAll('td.win')).toHaveLength(0)
  })

  it('shows Missed reps for an EMOM, with a dash when unknown', async () => {
    const eplan = { ...plan, format: 'emom' as const, cap_min: null, emom_min: 12 }
    const a = { ...then, missed_reps: 10 }
    const b = { ...now, missed_reps: null }
    const w = await mountIt({ plan: eplan, sessions: [], then: a, now: b })
    const cells = w.get('[data-testid="cmp-missed"]').findAll('td')
    expect(cells.map((c) => c.text())).toEqual(['10', '—'])
    expect(w.get('[data-testid="cmp-missed"]').findAll('td.win')).toHaveLength(0)
  })

  it('shows the strength score, its change, the explainer and a score on each row', async () => {
    const w = await mountIt({ plan: { ...plan, strength_score: 112, strength_change: 12 }, sessions: [{ ...now, score: 112 }, { ...then, score: 100 }], then, now })
    expect(t(w, 'strength-score')).toBe('Strength 112')
    expect(t(w, 'strength-change')).toBe('+12 since the first time')
    expect(t(w, 'strength-explainer')).toContain('100 is your first session.')
    expect(w.findAll('[data-testid="session-score"]').map((x) => x.text())).toEqual(['Strength 112', 'Strength 100'])
    expect(t(w, 'plan-summary')).not.toContain('Strength')
  })

  it('shows a dash for a null row score and no score with one session', async () => {
    const w = await mountIt({ plan: { ...plan, strength_score: null, strength_change: null }, sessions: [{ ...now, score: null }, { ...then, score: 100 }], then, now })
    expect(w.find('[data-testid="strength"]').exists()).toBe(false)
    expect(w.findAll('[data-testid="session-score"]').map((x) => x.text())).toEqual(['—', 'Strength 100'])
    const one = await mountIt({ plan, sessions: [{ ...then, score: 100 }], then: null, now: null })
    expect(one.find('[data-testid="session-score"]').exists()).toBe(false)
    expect(one.find('[data-testid="strength"]').exists()).toBe(false)
  })
})
