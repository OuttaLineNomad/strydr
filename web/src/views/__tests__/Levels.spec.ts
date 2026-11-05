import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ query: {} }), RouterLink: { template: '<a><slot /></a>' } }))
import { api } from '@/api'
import PlanEditView from '../PlanEditView.vue'
import WorkoutPlanView from '../WorkoutPlanView.vue'
import SessionSummaryView from '../SessionSummaryView.vue'
import StepChart from '@/components/ui/StepChart.vue'
import { useSettingsStore } from '@/stores/settings'
import { profile } from '@/mocks/fixtures'
import { memoryStorage } from '@/mocks/memoryStorage'
import type { LadderSet, PlanOut, PlanProgress, SessionSummary } from '@/api/types'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const post = vi.mocked(api.POST) as unknown as ReturnType<typeof vi.fn>
const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>

function pinia() {
  const p = createPinia()
  setActivePinia(p)
  useSettingsStore().profile = profile({}, { units: 'imperial' }) as never
  return p
}
const move = { name: 'Incline push-up', reps: 12, seconds: null, weight_kg: null, ladder: 'push-up' as const, rung: 1 }
const planOut = (o: Partial<PlanOut> = {}): PlanOut => ({
  id: 1, name: 'Push day', format: 'complex', cap_min: null, emom_min: null, rounds: 3, tap_per: 'move', video_url: null, created_at: '', updated_at: '', last_session: null,
  moves: [move], ...o,
})

describe('PlanEditView Level control', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers Level on a bodyweight move, renames the move from the rung and saves ladder and rung', async () => {
    get.mockResolvedValue({ data: [], response: { status: 200 } })
    post.mockResolvedValue({ data: planOut(), response: { status: 201 } })
    const w = mount(PlanEditView, { global: { plugins: [pinia()], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    await w.get('[data-testid="plan-name-input"]').setValue('Push day')
    await w.get('[data-testid="move-amount"]').setValue('12')
    expect(w.find('[data-testid="move-level"]').exists()).toBe(true)
    expect(w.find('[data-testid="level-rung-0"]').exists()).toBe(false)
    await w.get('[data-testid="level-ladder-push-up"]').trigger('click')
    expect(w.findAll('[data-testid^="level-rung-"]').map((b) => b.text())).toEqual(['Wall', 'Incline', 'Knee', 'Full', 'Decline'])
    await w.get('[data-testid="level-rung-1"]').trigger('click')
    expect((w.get('[data-testid="move-name"]').element as HTMLInputElement).value).toBe('Incline push-up')
    expect(w.find('[data-testid="move-weight"]').exists()).toBe(false)
    await w.get('[data-testid="plan-save"]').trigger('submit')
    await flushPromises()
    const body = post.mock.calls[0]![1].body
    expect(body.moves[0]).toMatchObject({ name: 'Incline push-up', reps: 12, weight_kg: null, ladder: 'push-up', rung: 1 })
  })

  it('loads an existing ladder plan and saves it back with ladder and rung intact', async () => {
    get.mockResolvedValue({ data: [planOut()], response: { status: 200 } })
    put.mockResolvedValue({ data: planOut(), response: { status: 200 } })
    const w = mount(PlanEditView, { props: { id: '1' }, global: { plugins: [pinia()], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    expect(w.get('[data-testid="level-rung-1"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-testid="plan-save"]').trigger('submit')
    await flushPromises()
    expect(put.mock.calls[0]![1].body.moves[0]).toMatchObject({ name: 'Incline push-up', reps: 12, weight_kg: null, ladder: 'push-up', rung: 1 })
  })

  it('asks for a rung when a ladder is chosen without one, and drops the old auto name on a ladder change', async () => {
    get.mockResolvedValue({ data: [planOut()], response: { status: 200 } })
    const w = mount(PlanEditView, { props: { id: '1' }, global: { plugins: [pinia()], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    await w.get('[data-testid="level-ladder-pull-up"]').trigger('click')
    expect((w.get('[data-testid="move-name"]').element as HTMLInputElement).value).toBe('')
    await w.get('[data-testid="plan-save"]').trigger('submit')
    await flushPromises()
    expect(w.get('[data-testid="move-error"]').text()).toBe('Pick a rung for the level.')
    expect(put).not.toHaveBeenCalled()
  })

  it('hides Level on a move with a bell and clears it with None', async () => {
    get.mockResolvedValue({ data: [], response: { status: 200 } })
    const w = mount(PlanEditView, { global: { plugins: [pinia()], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    await w.get('[data-testid="move-weight"]').setValue('25')
    expect(w.find('[data-testid="move-level"]').exists()).toBe(false)
    await w.get('[data-testid="move-weight"]').setValue('')
    await w.get('[data-testid="level-ladder-pull-up"]').trigger('click')
    expect(w.findAll('[data-testid^="level-rung-"]')).toHaveLength(3)
    await w.get('[data-testid="level-none"]').trigger('click')
    expect(w.find('[data-testid="level-rung-0"]').exists()).toBe(false)
  })
})

describe('WorkoutPlanView unlock offer and staircase', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('localStorage', memoryStorage())
  })
  const row = (id: number) => ({ id, date: '2026-11-0' + id + 'T18:00:00Z', weight_kg: null, rounds_done: 3, partial_moves: 0, active_s: 600, overtime_s: 0, effort: null, missed_reps: null, changed: false, cap_min: null, target_rounds: 3, move_count: 1 })
  const unlock = { move_index: 0, ladder: 'push-up' as const, from_rung: 1, to_rung: 2 }
  const progress = (): PlanProgress => ({ plan: planOut({ unlocks: [unlock] }), sessions: [row(2), row(1)], then: null, now: null })
  const history = [{ session_id: 1, date: '2026-11-01T18:00:00Z', rung: 1, reps: 12 }, { session_id: 2, date: '2026-11-02T18:00:00Z', rung: 2, reps: 6 }]
  function setup() {
    get.mockImplementation(async (path: string) => (path.includes('ladders') ? { data: history, response: { status: 200 } } : { data: progress(), response: { status: 200 } }))
    return mount(WorkoutPlanView, { props: { id: '1' }, global: { plugins: [pinia()], stubs: { RouterLink: RouterLinkStub } } })
  }

  it('offers the next rung, and Yes puts the plan with it', async () => {
    const w = setup()
    await flushPromises()
    expect(w.get('[data-testid="unlock-text"]').text()).toBe('Unlocked: Knee push-up. Use it from now on?')
    put.mockResolvedValue({ data: planOut({ moves: [{ ...move, name: 'Knee push-up', rung: 2 }], unlocks: [] }), response: { status: 200 } })
    await w.get('[data-testid="unlock-yes"]').trigger('click')
    await flushPromises()
    const sent = put.mock.calls[0]![1]
    expect(sent.params.path.plan_id).toBe(1)
    expect(sent.body.moves[0]).toMatchObject({ rung: 2, ladder: 'push-up' })
    expect(w.find('[data-testid="unlock-offer"]').exists()).toBe(false)
  })

  it('Yes keeps a round-mode plan on tap per round', async () => {
    get.mockImplementation(async (path: string) => (path.includes('ladders') ? { data: history, response: { status: 200 } } : { data: { ...progress(), plan: planOut({ unlocks: [unlock], tap_per: 'round' }) }, response: { status: 200 } }))
    const w = mount(WorkoutPlanView, { props: { id: '1' }, global: { plugins: [pinia()], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    put.mockResolvedValue({ data: planOut({ tap_per: 'round' }), response: { status: 200 } })
    await w.get('[data-testid="unlock-yes"]').trigger('click')
    await flushPromises()
    expect(put.mock.calls[0]![1].body.tap_per).toBe('round')
  })

  it('Not yet hides the offer until the next session', async () => {
    const w = setup()
    await flushPromises()
    await w.get('[data-testid="unlock-later"]').trigger('click')
    expect(w.find('[data-testid="unlock-offer"]').exists()).toBe(false)
    const again = setup()
    await flushPromises()
    expect(again.find('[data-testid="unlock-offer"]').exists()).toBe(false)
  })

  it('shows the staircase with rung names as direct labels', async () => {
    const w = setup()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/v1/ladders/{ladder}/history', { params: { path: { ladder: 'push-up' } } })
    expect(w.findAll('[data-testid="step"]')).toHaveLength(2)
    expect(w.findAll('[data-testid="step-label"]').map((l) => l.text())).toEqual(['Incline', 'Knee'])
  })
})

describe('StepChart', () => {
  it('names each run of a rung once and has a table twin', async () => {
    const pts = [{ label: 'Nov 1', rung: 1, reps: 12 }, { label: 'Nov 2', rung: 1, reps: 14 }, { label: 'Nov 3', rung: 2, reps: 6 }]
    const w = mount(StepChart, { props: { title: 'Push-up levels', ladder: 'push-up', points: pts } })
    expect(w.findAll('[data-testid="step-label"]').map((l) => l.text())).toEqual(['Incline', 'Knee'])
    await w.get('[data-testid="table-toggle"]').trigger('click')
    expect(w.findAll('tbody tr').map((r) => r.text())).toEqual(['Nov 1Incline12 reps', 'Nov 2Incline14 reps', 'Nov 3Knee6 reps'])
  })
})

describe('SessionSummaryView step-down', () => {
  beforeEach(() => vi.clearAllMocks())
  const sets: LadderSet[] = [0, 1, 2].map((i) => ({ move_index: 0, instance: i, move: 'Incline push-up', ladder: 'push-up', planned_rung: 1, rung: 1, reps: 12 }))
  const sm = (ladder_sets = sets): SessionSummary => ({
    session: { id: 3, plan_id: 1, plan: { name: 'Push day', format: 'complex', cap_min: null, emom_min: null, rounds: 3, tap_per: 'move', moves: [move], video_url: null }, weight_kg: null, start_utc: '2026-11-03T18:00:00Z', end_utc: '2026-11-03T18:10:00Z', events: [], rounds_done: 3, partial_moves: 0, fell_short: [], active_s: 600, overtime_s: 0, created_at: '' },
    matched_workout_id: null, avg_hr: null, effort: null, effort_source: null, effort_estimated: false, moves: [], rounds: [], zone_seconds: null, zone_bounds_bpm: null, fell_short: [], ladder_sets, unlocked: ['Knee push-up'],
  })
  async function setup() {
    get.mockResolvedValue({ data: sm(), response: { status: 200 } })
    const w = mount(SessionSummaryView, { props: { id: '3' }, global: { plugins: [pinia()], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    return w
  }

  it('says what was unlocked and logs an easier level with one pick, then undoes it', async () => {
    const w = await setup()
    expect(w.get('[data-testid="summary-unlocked"]').text()).toBe('You unlocked Knee push-up.')
    expect(w.findAll('[data-testid="ladder-row"]')).toHaveLength(3)
    await w.get('[data-testid="ladder-easier-0:2"]').trigger('click')
    expect(w.findAll('[data-testid^="ladder-pick-0:2-"]').map((b) => b.text())).toEqual(['Wall'])
    put.mockResolvedValue({ data: { '0:2': 0 }, response: { status: 200 } })
    get.mockResolvedValue({ data: { ...sm(sets.map((x) => (x.instance === 2 ? { ...x, rung: 0 } : x))), unlocked: [] }, response: { status: 200 } })
    await w.get('[data-testid="ladder-pick-0:2-0"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/sessions/{session_id}/rungs', { params: { path: { session_id: 3 } }, body: { '0:2': 0 } })
    expect(w.get('[data-testid="ladder-state-0:2"]').text()).toBe('Did Wall')
    expect(w.find('[data-testid="summary-unlocked"]').exists()).toBe(false) // a blocking step-down withdraws the line
    put.mockResolvedValue({ data: {}, response: { status: 200 } })
    get.mockResolvedValue({ data: sm(), response: { status: 200 } })
    await w.get('[data-testid="ladder-undo-0:2"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenLastCalledWith('/api/v1/sessions/{session_id}/rungs', { params: { path: { session_id: 3 } }, body: { '0:2': null } })
    expect(w.get('[data-testid="ladder-state-0:2"]').text()).toBe('Incline')
  })
})
