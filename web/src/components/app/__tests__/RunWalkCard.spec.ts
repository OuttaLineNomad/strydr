import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn() } }))
import { api } from '@/api'
import RunWalkCard from '../RunWalkCard.vue'
import WalkingShareSection from '../WalkingShareSection.vue'
import type { RunWalk, WeekSummary } from '@/api/types'

const split = (o: Partial<RunWalk> = {}): RunWalk => ({
  run_pct: 71.4, walk_pct: 25, stopped_pct: 3.6, source: 'cadence', cutoff: 130, cutoff_learned: true, ...o,
})

describe('RunWalkCard', () => {
  it('shows the shares, the source and the cutoff', () => {
    const w = mount(RunWalkCard, { props: { runwalk: split(), units: 'imperial' } })
    expect(w.get('[data-testid="runwalk-line"]').text()).toBe('Running 71% · Walking 25% · Stopped 4%')
    expect(w.get('[data-testid="runwalk-how"]').text()).toContain('From cadence')
    expect(w.get('[data-testid="runwalk-how"]').text()).toContain('130 steps per minute, learned from your runs')
  })

  it('hides Stopped at 0 and says pace and the default cutoff', () => {
    const w = mount(RunWalkCard, { props: { runwalk: split({ stopped_pct: 0, run_pct: 75, source: 'pace', cutoff: 2.0633, cutoff_learned: false }), units: 'imperial' } })
    expect(w.get('[data-testid="runwalk-line"]').text()).toBe('Running 75% · Walking 25%')
    expect(w.get('[data-testid="runwalk-how"]').text()).toContain('13:00 /mi, the default')
  })

  it('says not available with no split', () => {
    const w = mount(RunWalkCard, { props: { runwalk: null, units: 'imperial' } })
    expect(w.get('[data-testid="runwalk-na"]').text()).toContain('not available')
  })
})

describe('WalkingShareSection', () => {
  beforeEach(() => vi.clearAllMocks())
  const wk = (id: string, start: string, walk: number | null) => ({ week_id: id, week_start: start, walk_pct: walk }) as unknown as WeekSummary

  it('plots walking share per week and calls a falling line progress', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    vi.mocked(api.GET).mockResolvedValue({ data: [wk('2026-W44', '2026-10-26', 20), wk('2026-W43', '2026-10-19', 30)], response: { ok: true } } as never)
    const w = mount(WalkingShareSection, { global: { plugins: [pinia] } })
    await flushPromises()
    expect(w.get('[data-testid="walking-share"]').text().toLowerCase()).toContain('falling line is progress')
    await w.get('[data-testid="table-toggle"]').trigger('click')
    const cells = w.get('[data-testid="chart-table"]').findAll('tbody td').map((c) => c.text())
    expect(cells).toEqual(expect.arrayContaining(['30%', '20%']))
  })

  it('stays hidden when no week has a split', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    vi.mocked(api.GET).mockResolvedValue({ data: [wk('2026-W44', '2026-10-26', null)], response: { ok: true } } as never)
    const w = mount(WalkingShareSection, { global: { plugins: [pinia] } })
    await flushPromises()
    expect(w.find('[data-testid="walking-share"]').exists()).toBe(false)
  })
})
