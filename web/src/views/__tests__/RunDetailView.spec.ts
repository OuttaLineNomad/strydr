import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import RunDetailView from '../RunDetailView.vue'
import { useSettingsStore } from '@/stores/settings'
import { profile, workoutDetail } from '@/mocks/fixtures'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>

async function mountIt(detail = workoutDetail()) {
  get.mockImplementation(async (url: string) => {
    if (url === '/api/v1/workouts/{workout_id}') return { data: detail, response: { status: 200 } }
    if (url === '/api/v1/shoes') return { data: { shoes: [{ id: 1, name: 'Pegasus', retired: false, distance_m: 0, runs: 0 }, { id: 2, name: 'Vomero', retired: false, distance_m: 0, runs: 0 }], default: null }, response: { status: 200 } }
    if (url === '/api/v1/insights') return { data: { items: [], total: 0, limit: 10, offset: 0, disclaimer: 'Not medical advice.' }, response: { status: 200 } }
    return { data: undefined, response: { status: 404 } }
  })
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile()
  const w = mount(RunDetailView, {
    props: { id: 'w-1' },
    global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub, RouteMap: true } },
  })
  await flushPromises()
  return { w, settings: useSettingsStore() }
}

describe('RunDetailView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the run shoe in the picker and saves a change to this workout', async () => {
    const { w } = await mountIt(workoutDetail({ shoe: { id: 1, name: 'Pegasus', retired: false, source: 'chosen' }, shoe_chosen: true }))
    const sel = w.get('[data-testid="shoe-picker"]')
    expect((sel.element as HTMLSelectElement).value).toBe('1')
    expect(w.get('[data-testid="shoe-current"]').text()).toContain('Pegasus')
    put.mockResolvedValue({ data: { shoe: { id: 2, name: 'Vomero', retired: false, source: 'chosen' }, chosen: true }, response: { ok: true } })
    await sel.setValue('2')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/workouts/{workout_id}/shoe', { params: { path: { workout_id: 'w-1' } }, body: { shoe_id: 2 } })
    expect(w.get('[data-testid="shoe-current"]').text()).toContain('Vomero')
  })

  it('switches the splits table between miles and kilometres with the units setting', async () => {
    const { w, settings } = await mountIt()
    expect(w.findAll('[data-testid="splits-table"] tbody tr')).toHaveLength(3)
    expect(w.get('[data-testid="splits-table"] thead').text()).toContain('Mile')
    settings.profile = profile({}, { units: 'metric' })
    await flushPromises()
    expect(w.findAll('[data-testid="splits-table"] tbody tr')).toHaveLength(4)
    expect(w.get('[data-testid="splits-table"] thead').text()).toContain('Km')
  })

  it('renders not available, not zero, for missing series and values', async () => {
    const { w } = await mountIt(
      workoutDetail({
        workout: { ...workoutDetail().workout, avg_hr: null, max_hr: null, elevation_gain_m: null },
        avg_cadence: null,
        hr_series: null,
        pace_series: null,
        elevation_series: null,
        splits_km: null,
        splits_mi: null,
        display_geometry: null,
      }),
    )
    for (const id of ['pace-na', 'hr-na', 'elev-na', 'splits-na']) {
      expect(w.get(`[data-testid="${id}"]`).text()).toContain('not available')
    }
    const values = w.findAll('[data-testid="stat-value"]').map((v) => v.text())
    expect(values.filter((v) => v === 'not available')).toHaveLength(4)
  })

  it('puts every chart behind a table twin', async () => {
    const { w } = await mountIt()
    const toggles = w.findAll('[data-testid="table-toggle"]')
    expect(toggles).toHaveLength(3)
    await toggles[0]!.trigger('click')
    expect(w.find('[data-testid="chart-table"]').exists()).toBe(true)
  })

  it('lists quality-flag notes', async () => {
    const { w } = await mountIt(workoutDetail({ quality_flags: { hr_samples_dropped: 3 } }))
    expect(w.get('[data-testid="quality-notes"]').text()).toContain('3 heart-rate readings were left out')
  })

  it('shows the run summary under the hero', async () => {
    const { w } = await mountIt(workoutDetail({ summary: { text: 'You ran steady.', source: 'ai', key: 'run-summary/w-1', thumb: null } }))
    expect(w.get('[data-testid="run-summary"]').text()).toContain('You ran steady.')
  })

  it('renders no summary when there is none', async () => {
    const { w } = await mountIt(workoutDetail({ summary: null }))
    expect(w.find('[data-testid="run-summary"]').exists()).toBe(false)
  })
})
