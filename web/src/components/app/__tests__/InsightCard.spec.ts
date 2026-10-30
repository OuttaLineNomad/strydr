import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import InsightCard from '../InsightCard.vue'
import { insight, insightDetail } from '@/mocks/insightFixtures'
import type { InsightOut } from '@/api/types'
import { useSettingsStore } from '@/stores/settings'
import { profile } from '@/mocks/fixtures'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>
const del = vi.mocked(api.DELETE) as unknown as ReturnType<typeof vi.fn>

function mountIt(i: InsightOut = insight(), units: 'imperial' | 'metric' = 'imperial') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile({}, { units })
  return mount(InsightCard, { props: { insight: i }, global: { plugins: [pinia] } })
}

describe('InsightCard', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the number with its unit, the text, and no AI label for template wording', () => {
    const w = mountIt()
    expect(w.get('[data-testid="insight-number"]').text()).toBe('8.2 mi')
    expect(w.get('[data-testid="insight-text"]').text()).toContain('Your long run was 8.2 mi')
    expect(w.find('[data-testid="insight-ai"]').exists()).toBe(false)
  })

  it.each([
    ['m', 21097, 'imperial', '13.1 mi'],
    ['m', 21097, 'metric', '21.1 km'],
    ['m', 10000, 'metric', '10 km'],
    ['kg', 11.3, 'imperial', '25 lb'],
    ['kg', 11.3, 'metric', '11.3 kg'],
    ['s', 844, 'imperial', '14:04'],
    ['%', 38.2, 'imperial', '38.2 %'],
  ] as const)('shows a %s fact of %s in %s as %s', (unit, number, units, shown) => {
    const w = mountIt(insight({ unit, number }), units)
    expect(w.get('[data-testid="insight-number"]').text().replace(/\s+/g, ' ')).toBe(shown)
  })

  it('marks AI-phrased text with a label', () => {
    expect(mountIt(insight({ text_source: 'ai' })).get('[data-testid="insight-ai"]').text()).toContain('AI-phrased')
  })

  it('updates the thumb at once, before the API answers', async () => {
    let resolve!: (v: unknown) => void
    put.mockReturnValue(new Promise((r) => (resolve = r)))
    const w = mountIt()
    await w.get('[data-testid="thumb-up"]').trigger('click')
    expect(w.get('[data-testid="thumb-up"]').attributes('aria-pressed')).toBe('true')
    expect(put).toHaveBeenCalledWith('/api/v1/insights/{insight_key}/feedback', { params: { path: { insight_key: 'k-1' } }, body: { thumb: 'up' } })
    resolve({ data: { insight_key: 'k-1', thumb: 'up' }, response: { ok: true, status: 200 } })
    await flushPromises()
    expect(w.get('[data-testid="thumb-up"]').attributes('aria-pressed')).toBe('true')
    expect(w.find('[data-testid="feedback-error"]').exists()).toBe(false)
  })

  it('rolls the thumb back and says so when the API fails', async () => {
    put.mockResolvedValue({ data: undefined, error: {}, response: { ok: false, status: 500 } })
    const w = mountIt()
    await w.get('[data-testid="thumb-down"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="thumb-down"]').attributes('aria-pressed')).toBe('false')
    expect(w.get('[data-testid="feedback-error"]').text()).toContain('not saved')
  })

  it('tapping the active thumb clears it through DELETE, and rolls back if that fails', async () => {
    del.mockResolvedValueOnce({ response: { ok: true, status: 204 } })
    const w = mountIt(insight({ thumb: 'up' }))
    expect(w.get('[data-testid="thumb-up"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-testid="thumb-up"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/v1/insights/{insight_key}/feedback', { params: { path: { insight_key: 'k-1' } } })
    expect(w.get('[data-testid="thumb-up"]').attributes('aria-pressed')).toBe('false')

    del.mockResolvedValueOnce({ response: { ok: false, status: 500 } })
    put.mockResolvedValueOnce({ data: { thumb: 'up' }, response: { ok: true, status: 200 } })
    await w.get('[data-testid="thumb-up"]').trigger('click') // sets up again
    await flushPromises()
    await w.get('[data-testid="thumb-up"]').trigger('click') // clear fails
    await flushPromises()
    expect(w.get('[data-testid="thumb-up"]').attributes('aria-pressed')).toBe('true')
  })

  it('opens Why? and shows the rule, the data used and the evidence note', async () => {
    get.mockResolvedValue({ data: insightDetail(), response: { status: 200 } })
    const w = mountIt()
    expect(w.find('[data-testid="why-body"]').exists()).toBe(false)
    await w.get('[data-testid="why-toggle"]').trigger('click')
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/v1/insights/{insight_key}', { params: { path: { insight_key: 'k-1' } } })
    expect(w.get('[data-testid="why-toggle"]').attributes('aria-expanded')).toBe('true')
    expect(w.get('[data-testid="why-rule"]').text()).toContain('10% above')
    expect(w.get('[data-testid="why-data"]').text()).toContain('Previous longest mi')
    expect(w.get('[data-testid="why-data"]').text()).toContain('7.4')
    expect(w.get('[data-testid="why-note"]').text()).toBe('Based on 6 runs in the last 30 days.')
  })

  it('says so when the reasoning fails to load', async () => {
    get.mockResolvedValue({ data: undefined, response: { status: 500 } })
    const w = mountIt()
    await w.get('[data-testid="why-toggle"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="why-body"]').text()).toContain('could not load')
  })

  it('styles check-reading neutrally with text and an icon, and attaboy with the gold accent plus text', () => {
    const check = mountIt(insight({ kind: 'check-reading' }))
    expect(check.classes()).toContain('insight--check-reading')
    expect(check.get('[data-testid="insight-kind"]').text()).toBe('Check this reading')
    expect(check.get('[data-testid="insight-kind"]').classes()).toContain('pill--neutral')
    expect(check.find('[data-testid="insight-kind"] svg').exists()).toBe(true)

    const gold = mountIt(insight({ kind: 'attaboy' }))
    expect(gold.classes()).toContain('insight--attaboy')
    expect(gold.get('[data-testid="insight-kind"]').text()).toBe('Nice work')
    expect(gold.get('[data-testid="insight-kind"]').classes()).toContain('pill--tertiary')

    expect(mountIt().find('[data-testid="insight-kind"]').exists()).toBe(false)
  })

  it('shows a duration in seconds as a clock, not raw seconds', () => {
    const w = mountIt({ ...insight(), number: 844.0167, unit: "s" })
    expect(w.get('[data-testid="insight-number"]').text()).toBe('14:04')
  })
})
