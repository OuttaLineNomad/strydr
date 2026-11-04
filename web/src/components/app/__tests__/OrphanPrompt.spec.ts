import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import OrphanPrompt from '../OrphanPrompt.vue'
import { useSettingsStore } from '@/stores/settings'
import { profile } from '@/mocks/fixtures'
import type { Orphan, PlanOut } from '@/api/types'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const post = vi.mocked(api.POST) as unknown as ReturnType<typeof vi.fn>

const plan = (id: number, name: string, kg: number | null = 16): PlanOut =>
  ({ id, name, format: 'amrap', cap_min: 20, emom_min: null, rounds: null, video_url: null, moves: [{ name: 'Swing', reps: 10, seconds: null, weight_kg: kg }] }) as unknown as PlanOut
const guess = (o: Partial<NonNullable<Orphan['guess']>> = {}) => ({
  plan_id: 1, plan_name: 'Swing circuit', weight_kg: 15.88, rounds_done: 7, partial_moves: 0, format: 'amrap' as const,
  session_date: '2026-11-03', same_weekday: true, ...o,
})
const orphan = (id: string, g: Orphan['guess']): Orphan => ({ workout_id: id, start_utc: '2026-11-10T18:00:00Z', duration_s: 1800, guess: g })

async function mountIt(orphans: Orphan[], units: 'metric' | 'imperial' = 'imperial') {
  get.mockImplementation(async (url: string) => {
    if (url === '/api/v1/orphans') return { data: orphans, response: { status: 200 } }
    if (url === '/api/v1/plans') return { data: [plan(1, 'Swing circuit'), plan(2, 'Press day', null)], response: { status: 200 } }
    return { data: undefined, response: { status: 404 } }
  })
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile({}, { units }) as never
  const w = mount(OrphanPrompt, { global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return w
}
const tid = (w: Awaited<ReturnType<typeof mountIt>>, id: string) => w.get(`[data-testid="${id}"]`)

beforeEach(() => {
  get.mockReset()
  post.mockReset()
})

describe('OrphanPrompt', () => {
  it('renders nothing with no orphan', async () => {
    const w = await mountIt([])
    expect(w.find('[data-testid="orphan"]').exists()).toBe(false)
  })

  it('shows the guess sentence in lb and the three answers', async () => {
    const w = await mountIt([orphan('w1', guess())])
    const s = tid(w, 'orphan-sentence').text()
    expect(s).toMatch(/^Same as last \w+day: Swing circuit, 35 lb, 7 rounds\?$/)
    expect(tid(w, 'orphan-yes').text()).toBe('Yes, log it')
    expect(tid(w, 'orphan-other').text()).toBe('Something else')
    expect(tid(w, 'orphan-no').text()).toBe('Not a Strydr workout')
  })

  it('says last time when the weekday differs and kg in metric', async () => {
    const w = await mountIt([orphan('w1', guess({ same_weekday: false, weight_kg: null }))], 'metric')
    expect(tid(w, 'orphan-sentence').text()).toBe('Same as last time: Swing circuit, bodyweight, 7 rounds?')
  })

  it('yes logs the guess, links to the summary and moves on to the next orphan', async () => {
    post.mockResolvedValue({ data: { id: 42 }, response: { status: 201, ok: true } })
    const w = await mountIt([orphan('w1', guess()), orphan('w2', null)])
    await tid(w, 'orphan-yes').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/api/v1/orphans/{workout_id}/log', {
      params: { path: { workout_id: 'w1' } }, body: { plan_id: 1, weight_kg: 15.88, rounds_done: 7, partial_moves: 0 },
    })
    expect(tid(w, 'orphan-logged').text()).toContain('Logged Swing circuit')
    expect(w.getComponent(RouterLinkStub).props('to')).toBe('/workouts/sessions/42')
    expect(tid(w, 'orphan-sentence').text()).toMatch(/^Your watch logged a strength workout/)
  })

  it('with no history only Something else and Not a Strydr workout are offered', async () => {
    const w = await mountIt([orphan('w1', null)])
    expect(tid(w, 'orphan-sentence').text()).toMatch(/^Your watch logged a strength workout/)
    expect(w.find('[data-testid="orphan-yes"]').exists()).toBe(false)
    expect(w.find('[data-testid="orphan-other"]').exists()).toBe(true)
    expect(w.find('[data-testid="orphan-no"]').exists()).toBe(true)
  })

  it('something else picks another plan, weight and rounds', async () => {
    post.mockResolvedValue({ data: { id: 7 }, response: { status: 201, ok: true } })
    const w = await mountIt([orphan('w1', guess())])
    await tid(w, 'orphan-other').trigger('click')
    expect((tid(w, 'orphan-weight').element as HTMLInputElement).value).toBe('35')
    await tid(w, 'orphan-plan').setValue(2)
    expect((tid(w, 'orphan-weight').element as HTMLInputElement).value).toBe('')
    await tid(w, 'orphan-weight').setValue('53')
    await tid(w, 'orphan-minus').trigger('click')
    await tid(w, 'orphan-minus').trigger('click')
    expect(tid(w, 'orphan-rounds').text()).toBe('5')
    await tid(w, 'orphan-form').trigger('submit')
    await flushPromises()
    const body = post.mock.calls[0]![1].body
    expect(body.plan_id).toBe(2)
    expect(body.rounds_done).toBe(5)
    expect(body.weight_kg).toBeCloseTo(53 / 2.20462, 2)
  })

  it('rejects an impossible weight without posting', async () => {
    const w = await mountIt([orphan('w1', guess())])
    await tid(w, 'orphan-other').trigger('click')
    await tid(w, 'orphan-weight').setValue('abc')
    await tid(w, 'orphan-form').trigger('submit')
    expect(w.find('[data-testid="orphan-form-error"]').exists()).toBe(true)
    expect(post).not.toHaveBeenCalled()
  })

  it('not a Strydr workout dismisses it', async () => {
    post.mockResolvedValue({ data: undefined, response: { status: 204, ok: true } })
    const w = await mountIt([orphan('w1', guess())])
    await tid(w, 'orphan-no').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/api/v1/orphans/{workout_id}/dismiss', { params: { path: { workout_id: 'w1' } } })
    expect(w.find('[data-testid="orphan"]').exists()).toBe(false)
  })

  it('a failed log keeps the prompt and says so', async () => {
    post.mockResolvedValue({ data: undefined, response: { status: 500, ok: false } })
    const w = await mountIt([orphan('w1', guess())])
    await tid(w, 'orphan-yes').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="orphan-error"]').exists()).toBe(true)
    expect(w.find('[data-testid="orphan"]').exists()).toBe(true)
  })
})

describe('OrphanPrompt gone workouts', () => {
  it('a 404 on log drops the orphan', async () => {
    post.mockResolvedValue({ data: undefined, response: { status: 404, ok: false } })
    const w = await mountIt([orphan('w1', guess())])
    await tid(w, 'orphan-yes').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="orphan"]').exists()).toBe(false)
  })

  it('a 404 on dismiss drops the orphan', async () => {
    post.mockResolvedValue({ data: undefined, response: { status: 404, ok: false } })
    const w = await mountIt([orphan('w1', guess())])
    await tid(w, 'orphan-no').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="orphan"]').exists()).toBe(false)
  })

  it('a successful log reloads the plans and streak once loaded', async () => {
    post.mockResolvedValue({ data: { id: 5 }, response: { status: 201, ok: true } })
    const w = await mountIt([orphan('w1', guess())])
    const before = get.mock.calls.filter((c) => c[0] === '/api/v1/plans').length
    await tid(w, 'orphan-yes').trigger('click')
    await flushPromises()
    expect(get.mock.calls.filter((c) => c[0] === '/api/v1/plans').length).toBe(before + 1)
  })
})
