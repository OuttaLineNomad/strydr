import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import PrivacyZonesPanel from '../PrivacyZonesPanel.vue'
import AiSettingsPanel from '../AiSettingsPanel.vue'
import ThresholdsPanel from '../ThresholdsPanel.vue'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>
const post = vi.mocked(api.POST) as unknown as ReturnType<typeof vi.fn>
const del = vi.mocked(api.DELETE) as unknown as ReturnType<typeof vi.fn>

async function mountIt(comp: object) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const w = mount(comp, { global: { plugins: [pinia], stubs: { ZonePicker: true } } })
  await flushPromises()
  return w
}

const aiOut = (over: object = {}) => ({
  provider: 'nvidia', base_url: null, model: null, enabled: false, has_key: false,
  default_base_url: 'https://integrate.api.nvidia.com/v1', default_model: 'nvidia/some-model', ...over,
})

describe('PrivacyZonesPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists zones by radius only and shows no coordinates', async () => {
    // Even if a server ever sent a centre, the panel has nowhere to show it.
    get.mockResolvedValue({ data: [{ id: 1, radius_m: 400, lat: 39.7392, lon: -104.9903 }, { id: 2, radius_m: 250.4 }], response: { status: 200 } })
    const w = await mountIt(PrivacyZonesPanel)
    const labels = w.findAll('[data-testid="zone-label"]').map((l) => l.text())
    expect(labels).toEqual(['Zone (400 m)', 'Zone (250 m)'])
    expect(w.text()).not.toMatch(/39\.7|104\.9|-?\d{1,3}\.\d{3,}/)
    expect(w.get('[data-testid="zones-caveat"]').text()).toContain('reduce the risk')
    expect(w.get('[data-testid="zones-caveat"]').text()).toContain('do not remove it')
  })

  it('deletes a zone through DELETE and drops it from the list', async () => {
    get.mockResolvedValue({ data: [{ id: 7, radius_m: 400 }], response: { status: 200 } })
    del.mockResolvedValue({ response: { ok: true, status: 204 } })
    const w = await mountIt(PrivacyZonesPanel)
    await w.get('[data-testid="zone-delete"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/v1/privacy-zones/{zone_id}', { params: { path: { zone_id: 7 } } })
    expect(w.find('[data-testid="zone-label"]').exists()).toBe(false)
    expect(w.find('[data-testid="zones-empty"]').exists()).toBe(true)
  })

  it('adds a zone from the picked point with the default 400 m radius, and shows only the radius after', async () => {
    get.mockResolvedValue({ data: [], response: { status: 200 } })
    post.mockResolvedValue({ data: { id: 3, radius_m: 400 }, response: { status: 201 } })
    const w = await mountIt(PrivacyZonesPanel)
    expect((w.get('[data-testid="zone-radius"]').element as HTMLInputElement).value).toBe('400')
    expect(w.get('[data-testid="zone-add"]').attributes('disabled')).toBeDefined()
    w.getComponent({ name: 'ZonePicker' }).vm.$emit('pick', { lat: 39.1, lon: -104.2 })
    await flushPromises()
    await w.get('[data-testid="zone-add"]').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/api/v1/privacy-zones', { body: { lat: 39.1, lon: -104.2, radius_m: 400 } })
    expect(w.get('[data-testid="zone-label"]').text()).toBe('Zone (400 m)')
    expect(w.text()).not.toContain('39.1')
  })
})

describe('AiSettingsPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('says AI phrasing is off until a key is set, and explains what is sent', async () => {
    get.mockResolvedValue({ data: aiOut(), response: { status: 200 } })
    const w = await mountIt(AiSettingsPanel)
    expect(w.get('[data-testid="ai-status"]').text()).toBe('AI phrasing is off')
    expect(w.get('[data-testid="ai-explainer"]').text()).toMatch(/derived numbers/)
    expect(w.get('[data-testid="ai-explainer"]').text()).toMatch(/GPS points, names and exact times are never sent/)
  })

  it('never shows a stored key: the field is empty, a password field, and cleared after saving', async () => {
    get.mockResolvedValue({ data: aiOut({ enabled: true, has_key: true }), response: { status: 200 } })
    put.mockResolvedValue({ data: aiOut({ enabled: true, has_key: true }), response: { status: 200 } })
    const w = await mountIt(AiSettingsPanel)
    const key = w.get('[data-testid="ai-key"]')
    expect(w.get('[data-testid="ai-status"]').text()).toBe('AI phrasing is on')
    expect((key.element as HTMLInputElement).value).toBe('')
    expect(key.attributes('type')).toBe('password')
    expect(key.attributes('placeholder')).toContain('A key is stored')

    await key.setValue('nvapi-secret-123')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/settings/ai', { body: expect.objectContaining({ provider: 'nvidia', api_key: 'nvapi-secret-123' }) })
    expect((w.get('[data-testid="ai-key"]').element as HTMLInputElement).value).toBe('')
    expect(w.html()).not.toContain('nvapi-secret-123')
  })

  it('does not send the key field when nothing was typed', async () => {
    get.mockResolvedValue({ data: aiOut({ enabled: true, has_key: true }), response: { status: 200 } })
    put.mockResolvedValue({ data: aiOut({ enabled: true, has_key: true }), response: { status: 200 } })
    const w = await mountIt(AiSettingsPanel)
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(put.mock.calls[0]![1].body).not.toHaveProperty('api_key')
  })
})

describe('ThresholdsPanel', () => {
  beforeEach(() => vi.clearAllMocks())
  const th = (overrides = {}) => ({ defaults: { engine: { run_lookback_days: 14 }, load: { warmup_days: 42 } }, overrides, recompute_pending: false })

  it('shows defaults, saves only changed values, and resets to defaults', async () => {
    get.mockResolvedValue({ data: th(), response: { status: 200 } })
    put.mockResolvedValue({ data: th({ engine: { run_lookback_days: 21 } }), response: { status: 200 } })
    const w = await mountIt(ThresholdsPanel)
    expect(w.find('[data-testid="th-engine-run_lookback_days"]').exists()).toBe(false) // advanced: hidden until opened
    await w.get('[data-testid="thresholds-toggle"]').trigger('click')
    await flushPromises()
    await w.get('[data-testid="th-engine-run_lookback_days"]').setValue('21')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/settings/thresholds', { body: { overrides: { engine: { run_lookback_days: 21 } } } })
    expect(w.get('[data-testid="threshold-changed"]').text()).toContain('default 14')

    put.mockResolvedValue({ data: th(), response: { status: 200 } })
    await w.get('[data-testid="thresholds-reset"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenLastCalledWith('/api/v1/settings/thresholds', { body: { overrides: {} } })
    expect(w.find('[data-testid="threshold-changed"]').exists()).toBe(false)
  })
})
