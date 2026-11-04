import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import RunsView from '../RunsView.vue'
import ActivitiesView from '../ActivitiesView.vue'
import RunDetailView from '../RunDetailView.vue'
import { useWorkoutsStore } from '@/stores/workouts'
import { NAV_ITEMS, isActive } from '@/components/ui/nav'
import { useSettingsStore } from '@/stores/settings'
import { profile, workoutDetail } from '@/mocks/fixtures'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>
const del = vi.mocked(api.DELETE) as unknown as ReturnType<typeof vi.fn>

const item = (over: object = {}) => ({ ...workoutDetail().workout, ...over })
function setup(units: 'imperial' | 'metric' = 'imperial') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile({}, { units })
  return pinia
}
const stubs = { RouterLink: RouterLinkStub, RunsRoutesSwitch: true, RouteMap: true }

describe('lists', () => {
  beforeEach(() => vi.clearAllMocks())

  it('Runs asks for type=run only and has no type filter', async () => {
    get.mockResolvedValue({ data: [item()], response: { ok: true } })
    const w = mount(RunsView, { global: { plugins: [setup()], stubs } })
    await flushPromises()
    expect(get.mock.calls[0]![1].params.query.type).toBe('run')
    expect(w.find('[aria-label="Workout type"]').exists()).toBe(false)
  })

  it('Other activities asks for walk,hike,strength, narrows with the filter, and shows the carry chip', async () => {
    get.mockResolvedValue({ data: [item({ type: 'walk', carry_kg: 11.3 })], response: { ok: true } })
    const w = mount(ActivitiesView, { global: { plugins: [setup()], stubs } })
    await flushPromises()
    expect(get.mock.calls[0]![1].params.query.type).toBe('walk,hike,strength')
    expect(w.get('[data-testid="carry-chip"]').text()).toBe('+25 lb')
    const hikes = w.findAll('button').find((b) => b.text() === 'Hikes')!
    await hikes.trigger('click')
    await flushPromises()
    expect(get.mock.calls[1]![1].params.query.type).toBe('hike')
  })

  it('has a Strength filter that asks for type=strength', async () => {
    get.mockResolvedValue({ data: [item({ type: 'strength', distance_m: null, avg_speed_mps: null })], response: { ok: true } })
    const w = mount(ActivitiesView, { global: { plugins: [setup()], stubs } })
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === 'Strength')!.trigger('click')
    await flushPromises()
    expect(get.mock.calls[1]![1].params.query.type).toBe('strength')
    expect(w.text()).toContain('Strength')
  })

  it('a workout with no distance leads with its time and heart rate, never "not available"', async () => {
    get.mockResolvedValue({ data: [item({ type: 'strength', distance_m: null, avg_speed_mps: null, duration_s: 1320, avg_hr: 136.6 })], response: { ok: true } })
    const w = mount(ActivitiesView, { global: { plugins: [setup()], stubs } })
    await flushPromises()
    expect(w.get('[data-testid="no-distance"]').text()).toBe('22:00')
    expect(w.text()).toContain('137 bpm avg')
    expect(w.text()).not.toContain('not available')
  })

  it('shows the chip in kg for metric', async () => {
    get.mockResolvedValue({ data: [item({ type: 'walk', carry_kg: 11.3 })], response: { ok: true } })
    const w = mount(ActivitiesView, { global: { plugins: [setup('metric')], stubs } })
    await flushPromises()
    expect(w.get('[data-testid="carry-chip"]').text()).toBe('+11.3 kg')
  })

  const many = (n: number, over: object = {}) => Array.from({ length: n }, (_, i) => item({ workout_id: `w${i}`, ...over }))
  const nextBtn = (w: ReturnType<typeof mount>) => w.get('[data-testid="next"]')

  it('pages Runs with type run and offset 20', async () => {
    get.mockResolvedValue({ data: many(21), response: { ok: true } })
    const w = mount(RunsView, { global: { plugins: [setup()], stubs } })
    await flushPromises()
    await nextBtn(w).trigger('click')
    await flushPromises()
    const q = get.mock.calls[1]![1].params.query
    expect(q.type).toBe('run')
    expect(q.offset).toBe(20)
  })

  it('pages Other activities after choosing Hikes', async () => {
    get.mockResolvedValue({ data: many(21, { type: 'hike' }), response: { ok: true } })
    const w = mount(ActivitiesView, { global: { plugins: [setup()], stubs } })
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === 'Hikes')!.trigger('click')
    await flushPromises()
    await nextBtn(w).trigger('click')
    await flushPromises()
    const q = get.mock.calls[2]![1].params.query
    expect(q.type).toBe('hike')
    expect(q.offset).toBe(20)
  })

  it('ignores a late response from the previous tab and clears its cards', async () => {
    setup()
    const store = useWorkoutsStore()
    let release!: (v: unknown) => void
    get.mockImplementationOnce(() => new Promise((r) => (release = r)))
    const slow = store.loadList({ type: 'run', page: 0 })
    get.mockResolvedValueOnce({ data: [item({ workout_id: 'walk-1', type: 'walk' })], response: { ok: true } })
    const fast = store.loadList({ type: 'walk,hike', page: 0 })
    expect(store.items).toEqual([])
    await fast
    release({ data: [item({ workout_id: 'run-1' })], response: { ok: true } })
    await slow
    expect(store.items.map((i) => i.workout_id)).toEqual(['walk-1'])
    expect(store.loading).toBe(false)
  })

  it('highlights Other activities, not Runs, on a walk detail page', () => {
    expect(isActive('/activities', '/runs/w-1', 'walk')).toBe(true)
    expect(isActive('/runs', '/runs/w-1', 'walk')).toBe(false)
    expect(isActive('/runs', '/runs/w-1', 'run')).toBe(true)
    expect(isActive('/runs', '/runs/routes', 'walk')).toBe(true)
    expect(isActive('/runs', '/runs/w-1')).toBe(true)
  })

  it('highlights Other activities on a strength workout page', () => {
    expect(isActive('/activities', '/runs/s-1', 'strength')).toBe(true)
    expect(isActive('/runs', '/runs/s-1', 'strength')).toBe(false)
  })

  it('has an Other activities nav item after Runs', () => {
    const i = NAV_ITEMS.findIndex((n) => n.to === '/activities')
    expect(NAV_ITEMS[i - 1]!.to).toBe('/runs')
  })
})

const backTo = (w: ReturnType<typeof mount>) =>
  w.findAllComponents(RouterLinkStub).find((c) => c.attributes('data-testid') === 'back-link')!.props('to')

describe('type and carry on the workout page', () => {
  beforeEach(() => vi.clearAllMocks())
  async function mountIt(detail = workoutDetail(), units: 'imperial' | 'metric' = 'imperial') {
    get.mockImplementation(async (url: string) =>
      url === '/api/v1/workouts/{workout_id}' ? { data: detail, response: { status: 200 } }
        : url === '/api/v1/shoes' ? { data: { shoes: [], default: null }, response: { status: 200 } }
        : { data: undefined, response: { status: 404 } })
    const w = mount(RunDetailView, { props: { id: 'w-1' }, global: { plugins: [setup(units)], stubs } })
    await flushPromises()
    return w
  }

  it('changes the type and the back link follows', async () => {
    const w = await mountIt()
    expect(backTo(w)).toEqual({ name: 'runs' })
    put.mockResolvedValue({ data: { workout_id: 'w-1', type: 'walk' }, response: { ok: true } })
    // the stats refresh after the recompute reads the walk back
    const walk = workoutDetail({ workout: { ...workoutDetail().workout, type: 'walk' } })
    get.mockImplementation(async (url: string) => (url === '/api/v1/workouts/{workout_id}' ? { data: walk, response: { status: 200 } } : { data: undefined, response: { status: 404 } }))
    await w.get('[data-testid="type-walk"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/workouts/{workout_id}/type', { params: { path: { workout_id: 'w-1' } }, body: { type: 'walk' } })
    expect(backTo(w)).toEqual({ name: 'activities' })
  })

  it('keeps the type and shows an error when the change fails', async () => {
    const w = await mountIt()
    put.mockResolvedValue({ data: undefined, response: { ok: false } })
    await w.get('[data-testid="type-hike"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="type-error"]').exists()).toBe(true)
    expect(backTo(w)).toEqual({ name: 'runs' })
  })

  it('saves carried weight in lb as kg, then clears it', async () => {
    const w = await mountIt()
    put.mockResolvedValue({ data: { carry_kg: 11.34 }, response: { ok: true } })
    await w.get('[data-testid="carry-input"]').setValue('25')
    await w.get('form.carry').trigger('submit')
    await flushPromises()
    expect(put.mock.calls[0]![0]).toBe('/api/v1/workouts/{workout_id}/carry')
    expect(put.mock.calls[0]![1].body.weight_kg).toBeCloseTo(11.34, 2)
    expect((w.get('[data-testid="carry-input"]').element as HTMLInputElement).value).toBe('25')
    del.mockResolvedValue({ data: { carry_kg: null }, response: { ok: true } })
    await w.get('[data-testid="carry-clear"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/v1/workouts/{workout_id}/carry', { params: { path: { workout_id: 'w-1' } } })
    expect((w.get('[data-testid="carry-input"]').element as HTMLInputElement).value).toBe('')
  })

  it('clears carried weight in metric, and an empty Save clears it too', async () => {
    const w = await mountIt(workoutDetail({ carry_kg: 5 }), 'metric')
    del.mockResolvedValue({ data: { carry_kg: null }, response: { ok: true } })
    await w.get('[data-testid="carry-clear"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledTimes(1)
    expect((w.get('[data-testid="carry-input"]').element as HTMLInputElement).value).toBe('')
    const w2 = await mountIt(workoutDetail({ carry_kg: 5 }), 'metric')
    await w2.get('[data-testid="carry-input"]').setValue('')
    await w2.get('form.carry').trigger('submit')
    await flushPromises()
    expect(del).toHaveBeenCalledTimes(2)
    expect(put).not.toHaveBeenCalled()
  })

  it('shows a tiny weight as 0.1, never 0', async () => {
    const w = await mountIt(workoutDetail({ carry_kg: 0.01 }), 'metric')
    expect((w.get('[data-testid="carry-input"]').element as HTMLInputElement).value).toBe('0.1')
    const lb = await mountIt(workoutDetail({ carry_kg: 0.01 }), 'imperial')
    expect((lb.get('[data-testid="carry-input"]').element as HTMLInputElement).value).toBe('1')
  })

  it('saves carried weight in kg as typed and rejects out-of-range values', async () => {
    const w = await mountIt(workoutDetail({ carry_kg: 5 }), 'metric')
    expect((w.get('[data-testid="carry-input"]').element as HTMLInputElement).value).toBe('5')
    await w.get('[data-testid="carry-input"]').setValue('101')
    await w.get('form.carry').trigger('submit')
    await flushPromises()
    expect(put).not.toHaveBeenCalled()
    expect(w.find('[data-testid="carry-error"]').exists()).toBe(true)
    put.mockResolvedValue({ data: { carry_kg: 11.3 }, response: { ok: true } })
    await w.get('[data-testid="carry-input"]').setValue('11.3')
    await w.get('form.carry').trigger('submit')
    await flushPromises()
    expect(put.mock.calls[0]![1].body).toEqual({ weight_kg: 11.3 })
  })

  it('leaves the shown weight unchanged when the save fails', async () => {
    const w = await mountIt(workoutDetail({ carry_kg: 5 }), 'metric')
    put.mockResolvedValue({ data: undefined, response: { ok: false } })
    await w.get('[data-testid="carry-input"]').setValue('9')
    await w.get('form.carry').trigger('submit')
    await flushPromises()
    expect((w.get('[data-testid="carry-input"]').element as HTMLInputElement).value).toBe('5')
    expect(w.find('[data-testid="carry-error"]').exists()).toBe(true)
  })
})
