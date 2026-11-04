import { describe, expect, it, vi } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia } from 'pinia'

let path = '/'
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRoute: () => ({ path, params: {}, query: {} }),
}))
import TabBar from '../TabBar.vue'
import SideNav from '../SideNav.vue'
import { NAV_ITEMS, PHONE_NAV_ITEMS, isActive } from '../nav'
import { rememberHistoryRoute, resetHistoryNav } from '@/lib/historyNav'

const opts = () => ({ global: { plugins: [createPinia()], stubs: { RouterLink: RouterLinkStub } } })

describe('phone tab bar', () => {
  it('renders five tabs', () => {
    path = '/'
    const w = mount(TabBar, opts())
    expect(w.findAll('.tab').map((t) => t.text())).toEqual(['Home', 'Runs', 'Activities', 'Workouts', 'History'])
  })

  it.each(['/weeks', '/weeks/2026-W40', '/calendar', '/recap'])('lights History on %s', (p) => {
    path = p
    const w = mount(TabBar, opts())
    const active = w.findAll('.tab.active')
    expect(active).toHaveLength(1)
    expect(active[0]!.text()).toBe('History')
  })
})

describe('desktop side menu', () => {
  it('lists Workouts after Other activities, keeps Settings, and lights only Calendar on /calendar', () => {
    path = '/calendar'
    expect(NAV_ITEMS).toHaveLength(8)
    const labels = NAV_ITEMS.map((i) => i.label)
    expect(labels[labels.indexOf('Other activities') + 1]).toBe('Workouts')
    expect(labels).toContain('Settings')
    const w = mount(SideNav, opts())
    const links = w.findAllComponents(RouterLinkStub)
    expect(links.length).toBeGreaterThanOrEqual(8)
    const active = w.findAll('.active')
    expect(active).toHaveLength(1)
    expect(active[0]!.text()).toContain('Calendar')
  })
})

describe('Workouts tab', () => {
  it.each(['/workouts', '/workouts/new', '/workouts/3/edit'])('lights Workouts on %s', (p) => {
    path = p
    const active = mount(TabBar, opts()).findAll('.tab.active')
    expect(active).toHaveLength(1)
    expect(active[0]!.text()).toBe('Workouts')
  })
  it('does not light Workouts on /workoutsx', () => {
    expect(isActive('/workouts', '/workoutsx')).toBe(false)
  })
})

describe('isActive with match', () => {
  const history = PHONE_NAV_ITEMS.find((i) => i.label === 'History')!
  it('matches the three pages and their sub-paths, not near-misses', () => {
    expect(isActive(history.to, '/recap', null, history.match)).toBe(true)
    expect(isActive(history.to, '/weeks/2026-W40', null, history.match)).toBe(true)
    expect(isActive(history.to, '/weeksfoo', null, history.match)).toBe(false)
    expect(isActive(history.to, '/calendarx', null, history.match)).toBe(false)
  })
})

describe('History tab link', () => {
  it('opens the last history route, defaulting to /weeks', () => {
    path = '/'
    resetHistoryNav()
    const link = () => mount(TabBar, opts()).findAllComponents(RouterLinkStub).find((l) => l.text().includes('History'))!
    expect(link().props('to')).toBe('/weeks')
    rememberHistoryRoute('/calendar?month=2026-03')
    expect(link().props('to')).toBe('/calendar?month=2026-03')
    resetHistoryNav()
  })
})
