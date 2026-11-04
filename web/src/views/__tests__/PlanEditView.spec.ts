import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() } }))
const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), RouterLink: { template: '<a><slot /></a>' } }))
import { api } from '@/api'
import PlanEditView from '../PlanEditView.vue'
import { useSettingsStore } from '@/stores/settings'
import { profile } from '@/mocks/fixtures'
import type { PlanOut } from '@/api/types'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const post = vi.mocked(api.POST) as unknown as ReturnType<typeof vi.fn>
const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>

const saved = (o: Partial<PlanOut> = {}): PlanOut => ({
  id: 7, name: 'Swing circuit', format: 'amrap', cap_min: 20, emom_min: null, rounds: null, video_url: 'https://example.com/v',
  moves: [
    { name: 'Swing', reps: 15, seconds: null, weight_kg: 16 },
    { name: 'Plank', reps: null, seconds: 30, weight_kg: null },
  ],
  created_at: '2026-11-03T00:00:00', updated_at: '2026-11-03T00:00:00', ...o,
})

async function mountIt(id?: string, plans: PlanOut[] = [], units: 'imperial' | 'metric' = 'imperial') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile({}, { units }) as never
  get.mockResolvedValue({ data: plans, response: { status: 200 } })
  const w = mount(PlanEditView, { props: { id }, global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return w
}
const set = (w: Awaited<ReturnType<typeof mountIt>>, sel: string, v: string, i = 0) => w.findAll(sel)[i]!.setValue(v)

async function fillOne(w: Awaited<ReturnType<typeof mountIt>>) {
  await set(w, '[data-testid="plan-name-input"]', 'Swing circuit')
  await set(w, '[data-testid="move-name"]', 'Swing')
  await set(w, '[data-testid="move-amount"]', '10')
}

describe('PlanEditView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('creates an AMRAP with weights converted from lb to kg', async () => {
    const w = await mountIt()
    await fillOne(w)
    await set(w, '[data-testid="move-weight"]', '35')
    post.mockResolvedValue({ data: saved(), response: { status: 201 } })
    await w.get('form').trigger('submit')
    await flushPromises()
    const body = post.mock.calls[0]![1].body
    expect(body).toMatchObject({ name: 'Swing circuit', format: 'amrap', cap_min: 20, emom_min: null, rounds: null, video_url: null })
    expect(body.moves[0]).toMatchObject({ name: 'Swing', reps: 10, seconds: null })
    expect(body.moves[0].weight_kg).toBeCloseTo(15.876, 2)
    expect(push).toHaveBeenCalledWith('/workouts')
  })

  it('stores kg as entered for a metric runner', async () => {
    const w = await mountIt(undefined, [], 'metric')
    await fillOne(w)
    await set(w, '[data-testid="move-weight"]', '16')
    post.mockResolvedValue({ data: saved(), response: { status: 201 } })
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(post.mock.calls[0]![1].body.moves[0].weight_kg).toBe(16)
  })

  it('a blank weight is bodyweight, and EMOM and complex send their own setting', async () => {
    const w = await mountIt()
    await fillOne(w)
    await w.get('[data-testid="format-emom"]').trigger('click')
    await set(w, '[data-testid="plan-emom"]', '12')
    post.mockResolvedValue({ data: saved(), response: { status: 201 } })
    await w.get('form').trigger('submit')
    await flushPromises()
    let body = post.mock.calls[0]![1].body
    expect(body).toMatchObject({ format: 'emom', emom_min: 12, cap_min: null, rounds: null })
    expect(body.moves[0].weight_kg).toBeNull()
    await w.get('[data-testid="format-complex"]').trigger('click')
    await set(w, '[data-testid="plan-rounds"]', '4')
    await w.get('form').trigger('submit')
    await flushPromises()
    body = post.mock.calls[1]![1].body
    expect(body).toMatchObject({ format: 'complex', rounds: 4, emom_min: null, cap_min: null })
  })

  it('sends seconds instead of reps for a timed move', async () => {
    const w = await mountIt()
    await fillOne(w)
    await w.get('[data-testid="move-mode-seconds"]').trigger('click')
    await set(w, '[data-testid="move-amount"]', '30')
    post.mockResolvedValue({ data: saved(), response: { status: 201 } })
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(post.mock.calls[0]![1].body.moves[0]).toMatchObject({ reps: null, seconds: 30 })
  })

  it('blocks a bad move inline and sends nothing', async () => {
    const w = await mountIt()
    await set(w, '[data-testid="plan-name-input"]', 'X')
    await set(w, '[data-testid="move-name"]', 'Swing')
    await set(w, '[data-testid="move-amount"]', '0')
    await w.get('form').trigger('submit')
    expect(w.get('[data-testid="move-error"]').text()).toBe('Reps is 1 to 500.')
    expect(post).not.toHaveBeenCalled()
    await set(w, '[data-testid="move-amount"]', '5')
    await set(w, '[data-testid="move-weight"]', '1')
    await w.get('form').trigger('submit')
    expect(w.get('[data-testid="move-error"]').text()).toContain('Bell is')
    expect(post).not.toHaveBeenCalled()
  })

  it('rejects a video link that is not http(s)', async () => {
    const w = await mountIt()
    await fillOne(w)
    await set(w, '[data-testid="plan-video-input"]', 'ftp://x.com/v')
    await w.get('form').trigger('submit')
    expect(w.find('[data-testid="plan-video-error"]').exists()).toBe(true)
    expect(post).not.toHaveBeenCalled()
  })

  it('Same weight for all fills weighted moves and leaves blank ones bodyweight', async () => {
    const w = await mountIt()
    await w.get('[data-testid="add-move"]').trigger('click')
    await w.get('[data-testid="add-move"]').trigger('click')
    await set(w, '[data-testid="move-weight"]', '20', 0)
    await set(w, '[data-testid="move-weight"]', '25', 2)
    await set(w, '[data-testid="same-weight"]', '35')
    await w.get('[data-testid="same-apply"]').trigger('click')
    const ws = w.findAll('[data-testid="move-weight"]').map((i) => (i.element as HTMLInputElement).value)
    expect(ws).toEqual(['35', '', '35'])
  })

  it('moves rows up and down and removes one', async () => {
    const w = await mountIt()
    await w.get('[data-testid="add-move"]').trigger('click')
    await set(w, '[data-testid="move-name"]', 'A', 0)
    await set(w, '[data-testid="move-name"]', 'B', 1)
    await w.findAll('[data-testid="move-down"]')[0]!.trigger('click')
    expect(w.findAll('[data-testid="move-name"]').map((i) => (i.element as HTMLInputElement).value)).toEqual(['B', 'A'])
    await w.findAll('[data-testid="move-remove"]')[0]!.trigger('click')
    expect(w.findAll('[data-testid="move-row"]')).toHaveLength(1)
  })

  it('offers move names from other plans', async () => {
    const w = await mountIt(undefined, [saved()])
    expect(w.findAll('#move-names option').map((o) => o.attributes('value'))).toEqual(['Plank', 'Swing'])
  })

  it('shows a taken name inline by the name field', async () => {
    const w = await mountIt()
    await fillOne(w)
    post.mockResolvedValue({ data: undefined, error: { detail: 'a workout with that name exists' }, response: { status: 422 } })
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.get('[data-testid="plan-name-error"]').text()).toContain('already has this name')
    expect(push).not.toHaveBeenCalled()
  })

  it('reopens a saved plan with every field intact, and shows weights in the runner units', async () => {
    const w = await mountIt('7', [saved()])
    expect((w.get('[data-testid="plan-name-input"]').element as HTMLInputElement).value).toBe('Swing circuit')
    expect((w.get('[data-testid="plan-cap"]').element as HTMLInputElement).value).toBe('20')
    expect((w.get('[data-testid="plan-video-input"]').element as HTMLInputElement).value).toBe('https://example.com/v')
    const names = w.findAll('[data-testid="move-name"]').map((i) => (i.element as HTMLInputElement).value)
    expect(names).toEqual(['Swing', 'Plank'])
    expect(w.findAll('[data-testid="move-amount"]').map((i) => (i.element as HTMLInputElement).value)).toEqual(['15', '30'])
    expect(w.findAll('[data-testid="move-weight"]').map((i) => (i.element as HTMLInputElement).value)).toEqual(['35.3', ''])
    expect(w.findAll('[data-testid="move-mode-seconds"]')[1]!.attributes('aria-pressed')).toBe('true')
  })

  it('saves an edit with PUT', async () => {
    const w = await mountIt('7', [saved()])
    put.mockResolvedValue({ data: saved({ cap_min: 25 }), response: { status: 200 } })
    await set(w, '[data-testid="plan-cap"]', '25')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(put.mock.calls[0]![1].params.path.plan_id).toBe(7)
    expect(put.mock.calls[0]![1].body.cap_min).toBe(25)
  })

  it('opening and saving an unchanged plan keeps weight_kg exactly', async () => {
    const w = await mountIt('7', [saved({ moves: [{ name: 'Swing', reps: 15, seconds: null, weight_kg: 16 }] })])
    put.mockResolvedValue({ data: saved(), response: { status: 200 } })
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(put.mock.calls[0]![1].body.moves[0].weight_kg).toBe(16)
  })

  it('keeps the exact kg across a units switch, and converts only a weight the user changed', async () => {
    const w = await mountIt('7', [saved({ moves: [{ name: 'A', reps: 5, seconds: null, weight_kg: 16 }, { name: 'B', reps: 5, seconds: null, weight_kg: 16 }] })])
    await set(w, '[data-testid="move-weight"]', '40', 1)
    useSettingsStore().profile = profile({}, { units: 'metric' }) as never
    await flushPromises()
    put.mockResolvedValue({ data: saved(), response: { status: 200 } })
    await w.get('form').trigger('submit')
    await flushPromises()
    const ms = put.mock.calls[0]![1].body.moves
    expect(ms[0].weight_kg).toBe(16)
    expect(ms[1].weight_kg).toBe(18.1) // 40 lb, as shown in kg after the switch
  })

  it('refills when the id changes, so Save never writes one plan onto another', async () => {
    const a = saved({ id: 7, name: 'Plan A' })
    const b = saved({ id: 8, name: 'Plan B' })
    const w = await mountIt('7', [a, b])
    await w.setProps({ id: '8' })
    await flushPromises()
    expect((w.get('[data-testid="plan-name-input"]').element as HTMLInputElement).value).toBe('Plan B')
    put.mockResolvedValue({ data: b, response: { status: 200 } })
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(put.mock.calls[0]![1].params.path.plan_id).toBe(8)
  })

  it('treats a non-numeric id as missing', async () => {
    const w = await mountIt('abc', [saved()])
    expect(w.find('[data-testid="plan-missing"]').exists()).toBe(true)
  })

  it('shows a load error with Retry instead of "gone"', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    get.mockResolvedValue({ data: undefined, response: { status: 500 } })
    const w = mount(PlanEditView, { props: { id: '7' }, global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    expect(w.find('[data-testid="plan-missing"]').exists()).toBe(false)
    expect(w.get('[data-testid="plan-load-error"]').text()).toContain('Retry')
    get.mockResolvedValue({ data: [saved()], response: { status: 200 } })
    await w.get('[data-testid="plan-load-retry"]').trigger('click')
    await flushPromises()
    expect((w.get('[data-testid="plan-name-input"]').element as HTMLInputElement).value).toBe('Swing circuit')
  })

  it('rejects http:foo as a video link', async () => {
    const w = await mountIt()
    await fillOne(w)
    await set(w, '[data-testid="plan-video-input"]', 'http:foo')
    await w.get('form').trigger('submit')
    expect(w.find('[data-testid="plan-video-error"]').exists()).toBe(true)
    expect(post).not.toHaveBeenCalled()
  })

  it('shows only a taken-name 422 by the name field, other 422s as a save failure', async () => {
    const w = await mountIt()
    await fillOne(w)
    post.mockResolvedValue({ data: undefined, error: { detail: 'something else' }, response: { status: 422 } })
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.find('[data-testid="plan-name-error"]').exists()).toBe(false)
    expect(w.get('[data-testid="plan-save-error"]').text()).toContain('was not saved')
  })

  it('says so when the plan is gone', async () => {
    const w = await mountIt('99', [saved()])
    expect(w.find('[data-testid="plan-missing"]').exists()).toBe(true)
  })
})
