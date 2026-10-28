import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import LoadSection from '../LoadSection.vue'
import { loadOut } from '@/mocks/insightFixtures'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>

async function mountIt(data = loadOut()) {
  get.mockResolvedValue({ data, response: { status: 200 } })
  const pinia = createPinia()
  setActivePinia(pinia)
  const w = mount(LoadSection, { global: { plugins: [pinia] } })
  await flushPromises()
  return w
}

describe('LoadSection', () => {
  beforeEach(() => vi.clearAllMocks())

  it('puts ACWR and ramp in the table twin, with an estimated marker and no risk wording', async () => {
    const w = await mountIt()
    await w.get('[data-testid="table-toggle"]').trigger('click')
    const table = w.get('[data-testid="chart-table"]')
    const heads = table.findAll('thead th').map((h) => h.text())
    expect(heads).toEqual(['Day', 'Fitness', 'Fatigue', 'Form', 'Day load', 'ACWR', 'Ramp'])
    expect(table.text()).toContain('1.18')
    expect(table.text()).toContain('+6%')
    expect(table.text()).toContain('(estimated)')
    expect(table.text()).toContain('not available') // the first day has no ACWR
    // Nothing on the whole section may use risk wording (FR-24c).
    expect(w.text().toLowerCase()).not.toMatch(/risk|danger|injur|safe|warning|spike/)
  })

  it('shows ACWR only in the chart tooltip and table, never as a tile or label elsewhere', async () => {
    const w = await mountIt()
    expect(w.text()).not.toContain('ACWR 1.18') // not shown until the table or a hover
    expect(w.get('[data-testid="chart-plot"]').html()).toContain('ACWR') // hover/focus text is present for assistive tech
  })

  it('shows the training state with text and an icon', async () => {
    const w = await mountIt()
    const chip = w.get('[data-testid="training-state"]')
    expect(chip.text()).toContain('Building')
    expect(chip.find('svg').exists()).toBe(true)
    expect(chip.find('[data-state="Building"]').exists()).toBe(true)
  })

  it('shows the 42-day warm-up note only while it applies', async () => {
    expect((await mountIt()).find('[data-testid="load-warmup"]').text()).toContain('42 days')
    const done = loadOut()
    done.series.forEach((d) => (d.warmup = false))
    expect((await mountIt(done)).find('[data-testid="load-warmup"]').exists()).toBe(false)
  })

  it('reloads with the chosen range', async () => {
    const w = await mountIt()
    await w.get('[data-testid="load-range-365"]').trigger('click')
    await flushPromises()
    expect(get).toHaveBeenLastCalledWith('/api/v1/load', { params: { query: { days: 365 } } })
  })
})
