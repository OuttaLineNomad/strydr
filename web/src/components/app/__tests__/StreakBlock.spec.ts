import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn() } }))
import { api } from '@/api'
import StreakBlock from '../StreakBlock.vue'
import type { StreakOut } from '@/api/types'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>

function weeks(flags: boolean[]) {
  return flags.map((counted, i) => ({ week_start: new Date(Date.UTC(2026, 8, 14 + i * 7)).toISOString().slice(0, 10), counted }))
}
const data = (o: Partial<StreakOut> & { flags?: boolean[] }): StreakOut => {
  const { flags, ...rest } = o
  return { weeks: 0, this_week: false, last_streak: 0, recent: weeks(flags ?? Array(8).fill(false)), ...rest } as StreakOut
}

async function mountIt(d: StreakOut, compact = false) {
  get.mockResolvedValue({ data: d, response: { status: 200 } })
  const pinia = createPinia()
  setActivePinia(pinia)
  const w = mount(StreakBlock, { props: { compact }, global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return w
}
const text = (w: Awaited<ReturnType<typeof mountIt>>, id: string) => w.get(`[data-testid="${id}"]`).text()

beforeEach(() => get.mockReset())

describe('StreakBlock copy', () => {
  it('this week counts', async () => {
    const w = await mountIt(data({ weeks: 4, this_week: true, last_streak: 4 }))
    expect(text(w, 'streak-figure')).toBe('4 weeks')
    expect(w.text()).toContain('in a row')
    expect(text(w, 'streak-sentence')).toBe('This week counts.')
  })
  it('says 1 week for one', async () => {
    const w = await mountIt(data({ weeks: 1, this_week: true, last_streak: 1 }))
    expect(text(w, 'streak-figure')).toBe('1 week')
  })
  it('open week keeps the streak and says one round keeps it going', async () => {
    const w = await mountIt(data({ weeks: 3, this_week: false, last_streak: 3 }))
    expect(text(w, 'streak-figure')).toBe('3 weeks')
    expect(text(w, 'streak-sentence')).toBe('This week: not yet. One round keeps it going.')
  })
  it('broken streak reports the last one', async () => {
    const w = await mountIt(data({ weeks: 0, last_streak: 5 }))
    expect(text(w, 'streak-figure')).toBe('0 weeks')
    expect(text(w, 'streak-sentence')).toBe('Last streak: 5 weeks. Start again this week.')
    const one = await mountIt(data({ weeks: 0, last_streak: 1 }))
    expect(text(one, 'streak-sentence')).toBe('Last streak: 1 week. Start again this week.')
  })
  it('nothing ever counted', async () => {
    const w = await mountIt(data({}))
    expect(text(w, 'streak-sentence')).toBe('Do one round this week to start a streak.')
    expect(w.text()).not.toContain('!')
  })
})

describe('StreakBlock squares', () => {
  it('draws 8 squares named by week and state; the current week is coral until it counts', async () => {
    const w = await mountIt(data({ weeks: 2, this_week: false, flags: [false, false, false, false, false, true, true, false] }))
    const sq = w.findAll('[data-testid="streak-square"]')
    expect(sq).toHaveLength(8)
    expect(sq[0]!.attributes('aria-label')).toBe('Week of Sep 14: missed')
    expect(sq[5]!.attributes('aria-label')).toBe('Week of Oct 19: counted')
    expect(sq[5]!.classes()).toContain('sq--on')
    expect(sq[7]!.classes()).toContain('sq--now')
    expect(sq[7]!.attributes('aria-label')).toBe('Week of Nov 2: this week, not yet')
    const done = await mountIt(data({ weeks: 1, this_week: true, flags: [false, false, false, false, false, false, false, true] }))
    expect(done.findAll('[data-testid="streak-square"]')[7]!.classes()).not.toContain('sq--now')
  })
  it('compact links to /workouts', async () => {
    const w = await mountIt(data({ weeks: 1, this_week: true }), true)
    expect(w.findComponent(RouterLinkStub).props('to')).toBe('/workouts')
    expect(w.findComponent(RouterLinkStub).attributes('aria-label')).toBe('Weekly streak: 1 week in a row. Open Workouts')
  })
  it('compact renders nothing while loading or on error', async () => {
    get.mockReturnValue(new Promise(() => {}))
    const pinia = createPinia()
    setActivePinia(pinia)
    const loading = mount(StreakBlock, { props: { compact: true }, global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
    expect(loading.findComponent(RouterLinkStub).exists()).toBe(false)
    get.mockResolvedValue({ data: undefined, response: { status: 500 } })
    const p2 = createPinia()
    setActivePinia(p2)
    const failed = mount(StreakBlock, { props: { compact: true }, global: { plugins: [p2], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    expect(failed.findComponent(RouterLinkStub).exists()).toBe(false)
    expect(failed.find('[data-testid="streak-error"]').exists()).toBe(false)
  })
  it('shows an error line when it cannot load', async () => {
    get.mockResolvedValue({ data: undefined, response: { status: 500 } })
    const pinia = createPinia()
    setActivePinia(pinia)
    const w = mount(StreakBlock, { global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    expect(w.get('[data-testid="streak-error"]').text()).toContain('could not load')
  })
})
