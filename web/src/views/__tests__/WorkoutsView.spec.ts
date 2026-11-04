import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() } }))
import { api } from '@/api'
import WorkoutsView from '../WorkoutsView.vue'
import { useSettingsStore } from '@/stores/settings'
import { lastLine, planSummary, planWeight } from '@/lib/plans'
import { profile } from '@/mocks/fixtures'
import type { PlanOut, SessionOut } from '@/api/types'
import { memoryStorage } from '@/mocks/memoryStorage'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const post = vi.mocked(api.POST) as unknown as ReturnType<typeof vi.fn>
const del = vi.mocked(api.DELETE) as unknown as ReturnType<typeof vi.fn>

const plan = (o: Partial<PlanOut> = {}): PlanOut => ({
  id: 1, name: 'Swing circuit', format: 'amrap', cap_min: 20, emom_min: null, rounds: null, video_url: null,
  moves: Array.from({ length: 5 }, (_, i) => ({ name: `Move ${i}`, reps: 10, seconds: null, weight_kg: 11.3398 })),
  created_at: '2026-11-03T00:00:00', updated_at: '2026-11-03T00:00:00', ...o,
})

async function mountIt(plans: PlanOut[], units: 'imperial' | 'metric' = 'imperial', recent: SessionOut[] = []) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile({}, { units }) as never
  get.mockImplementation(async (url: string) => ({
    data: url === '/api/v1/sessions' ? recent : url === '/api/v1/streak' ? { weeks: 2, this_week: true, last_streak: 2, recent: [] } : plans,
    response: { status: 200 },
  }))
  const w = mount(WorkoutsView, { global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return w
}

describe('streak block', () => {
  it('mounts under the title row, above the library', async () => {
    const w = await mountIt([plan()])
    const html = w.html()
    expect(w.find('[data-testid="streak"]').exists()).toBe(true)
    expect(html.indexOf('data-testid="streak"')).toBeGreaterThan(html.indexOf('class="title-row"'))
    expect(html.indexOf('data-testid="streak"')).toBeLessThan(html.indexOf('data-testid="workouts-list"'))
  })
})

describe('From a video', () => {
  it('links to the new-workout editor in import mode', async () => {
    const w = await mountIt([plan()])
    expect(w.findComponent(RouterLinkStub).props('to')).toBe('/workouts/new?import=1')
  })
})

describe('plan summaries', () => {
  it('AMRAP, EMOM, complex and bodyweight read as the spec says', () => {
    expect(planSummary(plan(), 'imperial')).toBe('AMRAP · 20 min · 5 moves · 25 lb')
    expect(planSummary(plan({ format: 'emom', cap_min: null, emom_min: 12, moves: plan().moves.slice(0, 3) }), 'imperial')).toContain('EMOM · 12 min · 3 moves rotating')
    const bw = plan({ format: 'complex', cap_min: null, rounds: 4, moves: plan().moves.map((m) => ({ ...m, weight_kg: null })) })
    expect(planSummary(bw, 'imperial')).toBe('Complex · 4 rounds · 5 moves · bodyweight')
  })
  it('converts units: 16 kg is 35.3 lb', () => {
    expect(planWeight(16, 'metric')).toBe('16')
    expect(planWeight(16, 'imperial')).toBe('35.3')
  })
})

describe('WorkoutsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('localStorage', memoryStorage())
  })

  it('shows a loading line before the first load finishes', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    get.mockReturnValue(new Promise(() => {}))
    const w = mount(WorkoutsView, { global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    expect(w.get('[data-testid="workouts-loading"]').text()).toBe('Loading workouts.')
  })

  it('shows the empty state with a New workout button', async () => {
    const w = await mountIt([])
    expect(w.get('[data-testid="workouts-empty"]').text()).toContain('No workouts yet')
    expect(w.find('[data-testid="new-workout-empty"]').exists()).toBe(true)
  })

  it('lists plans with a summary, a Start that opens the live view, and Watch how in a new tab', async () => {
    const w = await mountIt([plan({ video_url: 'https://example.com/v' })])
    expect(w.get('[data-testid="plan-summary"]').text()).toBe('AMRAP · 20 min · 5 moves · 25 lb')
    expect(w.get('[data-testid="plan-start"]').attributes('disabled')).toBeUndefined()
    expect(w.findAllComponents(RouterLinkStub).some((c) => c.props('to') === '/workouts/1/run')).toBe(true)
    const a = w.get('[data-testid="plan-video"]')
    expect(a.text()).toBe('Watch how')
    expect(a.attributes('target')).toBe('_blank')
  })

  it('shows the Last line only for a plan with a session', async () => {
    const date = new Date(Date.now() - 86_400_000).toISOString()
    const w = await mountIt([plan({ last_session: { id: 7, rounds: 4, partial_moves: 0, date } }), plan({ id: 2, name: 'Zed' })])
    const rows = w.findAll('[data-testid="plan-row"]')
    expect(rows[0]!.get('[data-testid="plan-last"]').text()).toMatch(/^Last: 4 rounds · \w+/)
    expect(rows[1]!.find('[data-testid="plan-last"]').exists()).toBe(false)
    expect(w.findAllComponents(RouterLinkStub).some((c) => c.props('to') === '/workouts/sessions/7')).toBe(true)
    expect(lastLine({ id: 7, rounds: 3, partial_moves: 2, date }, new Date())).toContain('3 rounds + 2 moves')
  })

  it('lists the recent sessions, each linking to its summary', async () => {
    const x = (id: number, rounds_done: number, partial_moves = 0) => ({
      id, plan_id: 1, plan: plan(), weight_kg: null, start_utc: '2026-11-03T18:00:00Z', end_utc: '2026-11-03T18:10:00Z', events: [],
      rounds_done, partial_moves, fell_short: [], active_s: 600, overtime_s: 0, created_at: '2026-11-03T18:10:00Z',
    }) as SessionOut
    const w = await mountIt([plan()], 'imperial', [x(5, 4, 2), x(4, 3)])
    const rows = w.findAll('[data-testid="recent-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('4 rounds + 2 moves')
    expect(get).toHaveBeenCalledWith('/api/v1/sessions', { params: { query: { plan_id: undefined, limit: 10 } } })
    expect(w.findAllComponents(RouterLinkStub).some((c) => c.props('to') === '/workouts/sessions/5')).toBe(true)
  })

  it('has no Recent sessions panel before the first session', async () => {
    const w = await mountIt([plan()])
    expect(w.find('[data-testid="recent-sessions"]').exists()).toBe(false)
  })

  it('retries a session kept on the phone before it loads the list', async () => {
    const rec = { plan_id: 1, plan: plan(), weight_kg: null, start_utc: 'a', end_utc: 'b', events: [], rounds_done: 1, partial_moves: 0, fell_short: [] }
    localStorage.setItem('strydr.sessionOutbox', JSON.stringify([rec]))
    post.mockResolvedValue({ data: { id: 9 }, response: { status: 201 } })
    await mountIt([plan()])
    expect(post).toHaveBeenCalledWith('/api/v1/sessions', { body: rec })
    expect(localStorage.getItem('strydr.sessionOutbox')).toBeNull()
  })

  it('links each plan name to its page', async () => {
    const w = await mountIt([plan(), plan({ id: 2, name: 'Other' })])
    const links = w.findAll('[data-testid="plan-link"]').map((l) => l.findComponent(RouterLinkStub).props('to'))
    expect(links.sort()).toEqual(['/workouts/1', '/workouts/2'])
  })

  it('duplicates a plan', async () => {
    const w = await mountIt([plan()])
    post.mockResolvedValue({ data: plan({ id: 2, name: 'Swing circuit (copy)' }), response: { status: 201 } })
    await w.get('[data-testid="plan-duplicate"]').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/api/v1/plans/{plan_id}/duplicate', { params: { path: { plan_id: 1 } } })
    expect(w.findAll('[data-testid="plan-name"]').map((n) => n.text())).toEqual(['Swing circuit', 'Swing circuit (copy)'])
  })

  it('confirms by name, then deletes', async () => {
    const w = await mountIt([plan()])
    await w.get('[data-testid="plan-delete"]').trigger('click')
    expect(w.get('[data-testid="plan-confirm"]').text()).toContain('Delete Swing circuit?')
    del.mockResolvedValue({ response: { ok: true, status: 204 } })
    await w.get('[data-testid="plan-confirm-yes"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="plan-row"]').exists()).toBe(false)
    expect(w.find('[data-testid="workouts-empty"]').exists()).toBe(true)
  })

  it('keeps the plan when Keep is chosen', async () => {
    const w = await mountIt([plan()])
    await w.get('[data-testid="plan-delete"]').trigger('click')
    await w.get('[data-testid="plan-confirm-cancel"]').trigger('click')
    expect(w.find('[data-testid="plan-confirm"]').exists()).toBe(false)
    expect(del).not.toHaveBeenCalled()
  })

  it('shows a load failure inside the block with Retry', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    get.mockResolvedValue({ data: undefined, response: { status: 500 } })
    const w = mount(WorkoutsView, { global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    expect(w.get('[data-testid="workouts-error"]').text()).toContain('could not load')
    expect(w.get('[data-testid="workouts-error"]').text()).toContain('Retry')
  })
})
