import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import RunSummary from '../RunSummary.vue'
import type { WorkoutDetail } from '@/api/types'

const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>
type Summary = NonNullable<WorkoutDetail['summary']>
const summary = (o: Partial<Summary> = {}): Summary => ({ text: 'You ran steady.', source: 'ai', key: 'run-summary/r1', thumb: null, ...o })

function mountIt(s: Summary | null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(RunSummary, { props: { summary: s }, global: { plugins: [pinia] } })
}

describe('RunSummary', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the AI tag only for an AI summary', () => {
    expect(mountIt(summary()).get('[data-testid="summary-ai"]').text()).toContain('AI summary')
    const t = mountIt(summary({ source: 'template' }))
    expect(t.find('[data-testid="summary-ai"]').exists()).toBe(false)
    expect(t.get('[data-testid="summary-text"]').text()).toBe('You ran steady.')
  })

  it('renders nothing for a null summary', () => {
    expect(mountIt(null).find('[data-testid="run-summary"]').exists()).toBe(false)
  })

  it('sends thumbs through the store under the summary key', async () => {
    put.mockResolvedValue({ data: { insight_key: 'run-summary/r1', thumb: 'up' }, response: { ok: true, status: 200 } })
    const w = mountIt(summary())
    await w.get('[data-testid="thumb-up"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/insights/{insight_key}/feedback', { params: { path: { insight_key: 'run-summary/r1' } }, body: { thumb: 'up' } })
    expect(w.get('[data-testid="thumb-up"]').attributes('aria-pressed')).toBe('true')
  })
})
