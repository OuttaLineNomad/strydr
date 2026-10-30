import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn() } }))
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRoute: () => ({ query: {}, path: '/' }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))
import { api } from '@/api'
import WeeksView from '../WeeksView.vue'
import CalendarView from '../CalendarView.vue'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>

describe.each([
  ['WeeksView', WeeksView, 'weeks'],
  ['CalendarView', CalendarView, 'calendar'],
] as const)('%s', (_name, View, page) => {
  beforeEach(() => {
    vi.clearAllMocks()
    get.mockResolvedValue({ data: undefined, error: { message: 'x' }, response: { ok: false, status: 500 } })
  })

  it('renders the history switch with its own segment pressed', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const w = mount(View, { global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub, LoadSection: true } } })
    await flushPromises()
    for (const p of ['weeks', 'calendar', 'recap']) {
      expect(w.get(`[data-testid="history-${p}"]`).attributes('aria-pressed')).toBe(String(p === page))
    }
  })
})
