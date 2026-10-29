import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: vi.fn() }), RouterLink: { template: '<a><slot /></a>' } }))
import { api } from '@/api'
import SettingsView from '../SettingsView.vue'
import { hrmaxText } from '@/lib/profile'
import { profile } from '@/mocks/fixtures'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>

async function mountIt() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const w = mount(SettingsView, { global: { plugins: [pinia], stubs: { ZonePicker: true } } })
  await flushPromises()
  return w
}

describe('HRmax source text', () => {
  it('says where each source came from', () => {
    expect(hrmaxText(profile({ hrmax: 193, hrmax_source: 'observed' }).resolved)).toBe('193 bpm') // an older generation's row
    expect(hrmaxText(profile({ hrmax: 188, hrmax_source: 'tanaka' }).resolved)).toBe('188 bpm, estimated from your age')
    expect(hrmaxText(profile({ hrmax: 190, hrmax_source: 'override' }).resolved)).toBe('190 bpm, set by you')
  })
  it('says not available rather than a number when there is none', () => {
    expect(hrmaxText(profile({ hrmax: null, hrmax_source: 'unavailable' }).resolved)).toMatch(/^not available/)
    expect(hrmaxText(null)).toMatch(/^not available/)
  })
})

let current = profile()
describe('SettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    current = profile()
    // Only the profile call is answered; the privacy, AI and threshold panels get a failed read and stay empty.
    get.mockImplementation(async (url: string) =>
      url === '/api/v1/profile' ? { data: current, response: { status: 200 } } : { data: undefined, response: { status: 500 } })
  })

  it('shows the resolved HRmax and its source in words', async () => {
    current = profile({ hrmax: 193, hrmax_source: 'override' })
    const w = await mountIt()
    expect(w.get('[data-testid="hrmax-source"]').text()).toBe('Your HRmax: 193 bpm, set by you')
  })

  it('shows each zone limit with a % sign and the bpm it works out to', async () => {
    current = profile({ hrmax: 180, hrmax_source: 'tanaka' })
    const w = await mountIt()
    expect([1, 2, 3, 4].map((i) => w.get(`[data-testid="zone-bpm-${i}"]`).text())).toEqual(['108 bpm', '126 bpm', '144 bpm', '162 bpm'])
    expect(w.get('[data-testid="zone-5"]').text()).toBe('Zone 5: above 162 bpm')
    expect(w.findAll('.pct-sign')).toHaveLength(4)
    expect(w.get('[data-testid="hrmax-override"]').attributes('placeholder')).toBe('Leave empty to use your age')
  })

  it('works the bpm out from the override typed in the form, before saving', async () => {
    current = profile({ hrmax: 180, hrmax_source: 'tanaka' })
    const w = await mountIt()
    await w.get('[data-testid="hrmax-override"]').setValue('200')
    expect(w.get('[data-testid="zone-bpm-1"]').text()).toBe('120 bpm')
    expect(w.get('[data-testid="zone-5"]').text()).toBe('Zone 5: above 180 bpm')
    await w.get('[data-testid="zone-pct-2"]').setValue('75')
    expect(w.get('[data-testid="zone-bpm-2"]').text()).toBe('150 bpm')
  })

  it('ignores an out-of-range or fractional override in the preview', async () => {
    current = profile({ hrmax: 180, hrmax_source: 'tanaka' })
    const w = await mountIt()
    for (const v of ['20', '180.5']) {
      await w.get('[data-testid="hrmax-override"]').setValue(v)
      expect([1, 2, 3, 4].map((i) => w.get(`[data-testid="zone-bpm-${i}"]`).text())).toEqual(['108 bpm', '126 bpm', '144 bpm', '162 bpm'])
    }
  })

  it('hides the bpm when a saved override is cleared in the form', async () => {
    current = profile({ hrmax: 190, hrmax_source: 'override' }, { hrmax_override: 190 })
    const w = await mountIt()
    expect(w.get('[data-testid="zone-bpm-1"]').text()).toBe('114 bpm')
    await w.get('[data-testid="hrmax-override"]').setValue('')
    expect(w.find('[data-testid="zone-bpm-1"]').exists()).toBe(false)
  })

  it('hides the bpm text when there is no HRmax', async () => {
    current = profile({ hrmax: null, hrmax_source: 'unavailable' })
    const w = await mountIt()
    expect(w.find('[data-testid="zone-bpm-1"]').exists()).toBe(false)
    expect(w.find('[data-testid="zone-5"]').exists()).toBe(false)
    expect(w.get('[data-testid="hrmax-source"]').text()).toMatch(/not available/)
  })

  it('shows the estimate wording when HRmax comes from age', async () => {
    current = profile({ hrmax: 181, hrmax_source: 'tanaka' })
    const w = await mountIt()
    expect(w.get('[data-testid="hrmax-source"]').text()).toContain('181 bpm, estimated from your age')
  })

  it('shows Recalculating… after saving until the profile refreshes', async () => {
    vi.useFakeTimers()
    try {
      current = profile()
      const w = await mountIt()
      expect(w.find('[data-testid="recalculating"]').exists()).toBe(false)

      put.mockResolvedValue({ data: profile({}, { hrmax_override: 190 }, true), response: { status: 200 } })
      current = profile({ hrmax: 190, hrmax_source: 'override' }, { hrmax_override: 190 }, false)
      await w.get('[data-testid="hrmax-override"]').setValue('190')
      await w.get('form').trigger('submit')
      await flushPromises()
      expect(put).toHaveBeenCalledOnce()
      expect(w.get('[data-testid="recalculating"]').text()).toContain('Recalculating…')

      await vi.advanceTimersByTimeAsync(2100)
      await flushPromises()
      expect(w.find('[data-testid="recalculating"]').exists()).toBe(false)
      expect(w.get('[data-testid="hrmax-source"]').text()).toContain('190 bpm, set by you')
    } finally {
      vi.useRealTimers()
    }
  })

  it('rejects a bad HRmax override before calling the API', async () => {
    current = profile()
    const w = await mountIt()
    await w.get('[data-testid="hrmax-override"]').setValue('20')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(put).not.toHaveBeenCalled()
    expect(w.get('[data-testid="form-error"]').text()).toContain('100 to 230')
  })

  it('renders the import panel right after the weather panel', async () => {
    const w = await mountIt()
    const html = w.html()
    const weather = html.indexOf('data-testid="weather-settings"')
    const imp = html.indexOf('data-testid="import-panel"')
    expect(weather).toBeGreaterThan(-1)
    expect(imp).toBeGreaterThan(weather)
  })
})
