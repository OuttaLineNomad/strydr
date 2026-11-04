import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(async () => ({ data: undefined, response: { status: 500 } })) } }))
import { api } from '@/api'
import DashboardView from '../DashboardView.vue'

describe('DashboardView header', () => {
  it('has a Settings gear that links to /settings (the phone has no Settings tab)', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const w = mount(DashboardView, { global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    const gear = w.findAllComponents(RouterLinkStub).find((l) => l.attributes('data-testid') === 'settings-gear')
    expect(gear).toBeDefined()
    expect(gear!.props('to')).toBe('/settings')
    expect(gear!.attributes('aria-label')).toBe('Settings')
  })

  it('mounts a compact streak block that links to /workouts', async () => {
    vi.mocked(api.GET).mockImplementation((async (url: string) => url === '/api/v1/streak'
      ? { data: { weeks: 3, this_week: true, last_streak: 3, recent: [] }, response: { status: 200 } }
      : { data: undefined, response: { status: 500 } }) as never)
    const pinia = createPinia()
    setActivePinia(pinia)
    const w = mount(DashboardView, { global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    expect(w.get('[data-testid="streak-figure"]').text()).toBe('3 weeks')
    expect(w.findAllComponents(RouterLinkStub).some((l) => l.props('to') === '/workouts')).toBe(true)
  })

  it('shows the orphan prompt', async () => {
    vi.mocked(api.GET).mockImplementation((async (url: string) => url === '/api/v1/orphans'
      ? { data: [{ workout_id: 'w1', start_utc: '2026-11-10T18:00:00Z', duration_s: 1800, guess: null }], response: { status: 200 } }
      : { data: undefined, response: { status: 500 } }) as never)
    const pinia = createPinia()
    setActivePinia(pinia)
    const w = mount(DashboardView, { global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    expect(w.find('[data-testid="orphan"]').exists()).toBe(true)
  })
})
