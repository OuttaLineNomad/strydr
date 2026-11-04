import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(async () => ({ data: undefined, response: { status: 500 } })) } }))
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
})
