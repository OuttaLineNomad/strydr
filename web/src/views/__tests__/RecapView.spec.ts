import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn() } }))
const push = vi.fn()
const query: Record<string, string> = reactive({})
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRoute: () => ({ query }),
  useRouter: () => ({ push }),
}))
import { api } from '@/api'
import RecapView from '../RecapView.vue'
import { NAV_ITEMS } from '@/components/ui/nav'
import { useSettingsStore } from '@/stores/settings'
import { profile, workoutDetail } from '@/mocks/fixtures'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>

const totals = (period: string, over: object = {}) => ({
  period, distance_m: 160934, duration_s: 36000, run_count: 12, long_run_count: 2, elevation_gain_m: 304.8, active_days: 10, ...over,
})
function recap(period = '2026-09', over: object = {}) {
  return {
    period, kind: period.length === 4 ? 'year' : 'month', start_date: `${period}-01`, end_date: `${period}-30`, as_of: '2026-10-26', is_current: false,
    totals: totals(period), previous: totals('2026-08', { distance_m: 80467, run_count: 6 }),
    longest_runs: [{ ...workoutDetail().workout, workout_id: 'w-9', distance_m: 16093.4 }],
    top_routes: [{ route_key: 'r1', distance_m: 8046.7, runs: 4 }],
    shoes: [{ id: 1, name: 'Blue', retired: false, distance_m: 40233.5, runs: 5 }],
    fitness: { start: 30, end: 42, series: [{ local_date: '2026-09-01', fitness: 30 }, { local_date: '2026-09-02', fitness: 31 }, { local_date: '2026-09-03', fitness: 33 }] },
    best_weeks: [{ week_id: '2026-W37', week_start: '2026-09-07', week_end: '2026-09-13', distance_m: 32186.9, run_count: 3 }],
    ...over,
  }
}
function setup(units: 'imperial' | 'metric') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile({}, { units })
  return pinia
}
async function mountIt(data: object, units: 'imperial' | 'metric' = 'imperial') {
  get.mockResolvedValue({ data, response: { ok: true } })
  const w = mount(RecapView, { global: { plugins: [setup(units)], stubs: { RouterLink: RouterLinkStub, LineChart: true } } })
  await flushPromises()
  return w
}

describe('RecapView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const k of Object.keys(query)) delete query[k]
  })

  it('has a Recap nav item after Calendar', () => {
    const i = NAV_ITEMS.findIndex((n) => n.to === '/recap')
    expect(NAV_ITEMS[i - 1]!.to).toBe('/calendar')
  })

  it('renders a month in miles and feet with every section', async () => {
    query.period = '2026-09'
    const w = await mountIt(recap())
    expect(get.mock.calls[0]![1].params.path.period).toBe('2026-09')
    const t = w.get('[data-testid="recap-totals"]').text()
    expect(t).toContain('ft')
    expect(t).not.toContain('km')
    expect(w.get('[data-testid="recap-longest"]').text()).toContain('10.0 mi')
    expect(w.get('[data-testid="recap-route"]').text()).toContain('5.0 mi route')
    expect(w.get('[data-testid="recap-route"]').text()).toContain('4 runs this month')
    expect(w.get('[data-testid="recap-shoe"]').text()).toContain('25.0 mi')
    expect(w.find('[data-testid="recap-fitness"]').exists()).toBe(true)
    const links = w.findAllComponents(RouterLinkStub).map((c) => c.props('to'))
    expect(links).toContainEqual({ name: 'run-detail', params: { id: 'w-9' } })
    expect(links).toContainEqual({ name: 'route-detail', params: { routeKey: 'r1' } })
    expect(links).toContainEqual({ name: 'week-detail', params: { id: '2026-W37' } })
  })

  it('renders the year in metric', async () => {
    query.period = '2026'
    const w = await mountIt(recap('2026'), 'metric')
    const t = w.get('[data-testid="recap-totals"]').text()
    expect(t).toContain('305')
    expect(t).not.toContain('ft')
    expect(w.get('[data-testid="recap-longest"]').text()).toContain('16.1 km')
    expect(w.get('[data-testid="recap-route"]').text()).toContain('this year')
  })

  it('switches between month and year and steps by period', async () => {
    query.period = '2026-09'
    const w = await mountIt(recap())
    await w.get('[data-testid="recap-year"]').trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'recap', query: { period: '2026' } })
    await w.get('[data-testid="recap-prev"]').trigger('click')
    expect(push).toHaveBeenLastCalledWith({ name: 'recap', query: { period: '2026-08' } })
    await w.get('[data-testid="recap-next"]').trigger('click')
    expect(push).toHaveBeenLastCalledWith({ name: 'recap', query: { period: '2026-10' } })
  })

  it('goes from year to the as_of month in the current year, else December', async () => {
    const now = new Date()
    const y = String(now.getFullYear())
    query.period = y
    const w = await mountIt(recap(y, { is_current: true }))
    await w.get('[data-testid="recap-month"]').trigger('click')
    expect(push).toHaveBeenLastCalledWith({ name: 'recap', query: { period: `${y}-${String(now.getMonth() + 1).padStart(2, '0')}` } })
    query.period = '2025'
    const w2 = await mountIt(recap('2025'))
    await w2.get('[data-testid="recap-month"]').trigger('click')
    expect(push).toHaveBeenLastCalledWith({ name: 'recap', query: { period: '2025-12' } })
  })

  it('defaults to this month, says so far, and disables next at the current period', async () => {
    const now = new Date()
    const p = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    const w = await mountIt(recap(p, { is_current: true }))
    expect(get.mock.calls[0]![1].params.path.period).toBe(p)
    expect(w.get('[data-testid="recap-period"]').text()).toContain('so far')
    expect((w.get('[data-testid="recap-next"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(w.get('[data-testid="recap-totals"]').text()).toContain('Distance so far')
  })

  it('shows one line for an empty period and hides the sections', async () => {
    query.period = '2026-03'
    const w = await mountIt(recap('2026-03', {
      totals: totals('2026-03', { distance_m: 0, duration_s: 0, run_count: 0, long_run_count: 0, elevation_gain_m: null, active_days: 0 }),
      longest_runs: [], top_routes: [], shoes: [], fitness: null, best_weeks: [],
    }))
    expect(w.get('[data-testid="recap-empty"]').text()).toBe('No runs in March 2026.')
    expect(w.find('[data-testid="recap-totals"]').exists()).toBe(false)
    expect(w.findAll('h2')).toHaveLength(0)
  })

  it('shows the distance trend for a past month, and not without a previous or for the current period', async () => {
    query.period = '2026-09'
    const w = await mountIt(recap())
    const trend = w.get('[data-testid="stat-trend"]')
    expect(trend.text()).toContain('+50.0 mi vs August 2026')
    expect(trend.classes()).toContain('pill--success')
    const none = await mountIt(recap('2026-09', { previous: totals('2026-08', { run_count: 0, distance_m: 0 }) }))
    expect(none.find('[data-testid="stat-trend"]').exists()).toBe(false)
    const cur = await mountIt(recap('2026-09', { is_current: true }))
    expect(cur.find('[data-testid="stat-trend"]').exists()).toBe(false)
  })

  it('clears the old period when navigation fails, and keeps next usable', async () => {
    query.period = '2026-09'
    const w = await mountIt(recap())
    expect(w.find('[data-testid="recap-totals"]').exists()).toBe(true)
    get.mockResolvedValue({ data: undefined, response: { ok: false } })
    query.period = '2026-08'
    await flushPromises()
    expect(w.find('[data-testid="recap-totals"]').exists()).toBe(false)
    expect(w.text()).not.toContain('100.0')
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect(w.get('[data-testid="recap-period"]').text()).toBe('August 2026')
    expect((w.get('[data-testid="recap-next"]').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('guards a null distance and tags a retired shoe', async () => {
    query.period = '2026-09'
    const w = await mountIt(recap('2026-09', {
      longest_runs: [{ ...workoutDetail().workout, workout_id: 'w-9', distance_m: null }],
      shoes: [{ id: 1, name: 'Old', retired: true, distance_m: 1000, runs: 1 }],
    }))
    expect(w.get('[data-testid="recap-run"]').text()).not.toMatch(/available\s+mi/)
    expect(w.find('[data-testid="recap-retired"]').exists()).toBe(true)
  })

  it('hides a section that has no items', async () => {
    query.period = '2026-09'
    const w = await mountIt(recap('2026-09', { top_routes: [], shoes: [], best_weeks: [], fitness: null }))
    expect(w.find('[data-testid="recap-routes"]').exists()).toBe(false)
    expect(w.find('[data-testid="recap-shoes"]').exists()).toBe(false)
    expect(w.find('[data-testid="recap-longest"]').exists()).toBe(true)
  })
})
