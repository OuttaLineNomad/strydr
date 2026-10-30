import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const replace = vi.fn()
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRouter: () => ({ replace }),
}))
import HistorySwitch from '../HistorySwitch.vue'
import { rememberHistoryRoute, resetHistoryNav } from '@/lib/historyNav'

describe('HistorySwitch', () => {
  beforeEach(() => { vi.clearAllMocks(); resetHistoryNav() })

  it('selects the current page', () => {
    const w = mount(HistorySwitch, { props: { current: 'calendar' } })
    expect(w.get('[role="group"]').attributes('aria-label')).toBe('History view')
    expect(w.get('[data-testid="history-calendar"]').attributes('aria-pressed')).toBe('true')
    expect(w.get('[data-testid="history-weeks"]').attributes('aria-pressed')).toBe('false')
  })

  it('navigates on click', async () => {
    const w = mount(HistorySwitch, { props: { current: 'weeks' } })
    await w.get('[data-testid="history-recap"]').trigger('click')
    expect(replace).toHaveBeenCalledWith('/recap')
  })

  it('does not navigate when the current segment is clicked', async () => {
    const w = mount(HistorySwitch, { props: { current: 'weeks' } })
    await w.get('[data-testid="history-weeks"]').trigger('click')
    expect(replace).not.toHaveBeenCalled()
  })

  it('returns to the remembered month and period', async () => {
    rememberHistoryRoute('/calendar?month=2026-03')
    rememberHistoryRoute('/recap?kind=year&period=2025')
    rememberHistoryRoute('/weeks')
    const w = mount(HistorySwitch, { props: { current: 'weeks' } })
    await w.get('[data-testid="history-calendar"]').trigger('click')
    expect(replace).toHaveBeenLastCalledWith('/calendar?month=2026-03')
    await w.get('[data-testid="history-recap"]').trigger('click')
    expect(replace).toHaveBeenLastCalledWith('/recap?kind=year&period=2025')
  })
})
