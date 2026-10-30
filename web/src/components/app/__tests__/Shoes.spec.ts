import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn(), PATCH: vi.fn() } }))
import { api } from '@/api'
import ShoesPanel from '../ShoesPanel.vue'
import ShoePicker from '../ShoePicker.vue'
import { useWorkoutsStore } from '@/stores/workouts'
import { useSettingsStore } from '@/stores/settings'
import { profile, workoutDetail } from '@/mocks/fixtures'

const m = (f: unknown) => vi.mocked(f) as unknown as ReturnType<typeof vi.fn>
const get = m(api.GET), put = m(api.PUT), post = m(api.POST), del = m(api.DELETE), patch = m(api.PATCH)

const list = (over: object = {}) => ({
  shoes: [
    { id: 1, name: 'Pegasus', retired: false, distance_m: 160934.4, runs: 20 },
    { id: 2, name: 'Old Ghost', retired: true, distance_m: 8046.72, runs: 1 },
  ],
  default: { shoe_id: 1, from_date: '2026-10-01' },
  history: [
    { shoe_id: null, from_date: '2999-01-01' },
    { shoe_id: 1, from_date: '2026-10-01' },
    { shoe_id: 2, from_date: '2026-09-01' },
  ],
  ...over,
})
const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })

async function setup() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile()
  return pinia
}

describe('ShoesPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  async function mountPanel() {
    const pinia = await setup()
    get.mockResolvedValue(ok(list()))
    const w = mount(ShoesPanel, { global: { plugins: [pinia] } })
    await flushPromises()
    return w
  }

  it('lists shoes with distance in the user units and run counts, retired ones included', async () => {
    const w = await mountPanel()
    const rows = w.findAll('[data-testid="shoe-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('100.0 mi, 20 runs')
    expect(rows[1]!.text()).toContain('(retired)')
    expect(rows[1]!.text()).toContain('1 run')
    expect(w.get('[data-testid="shoe-default-now"]').text()).toContain('Pegasus')
  })

  it('starts the default select on the current default', async () => {
    const w = await mountPanel()
    expect((w.get('[data-testid="shoe-default-select"]').element as HTMLSelectElement).value).toBe('1')
  })

  it('does not send a blank rename', async () => {
    const w = await mountPanel()
    await w.findAll('[data-testid="shoe-rename"]')[0]!.trigger('click')
    await w.get('[data-testid="shoe-rename-input"]').setValue('   ')
    await w.get('[data-testid="shoe-rename-save"]').trigger('click')
    await flushPromises()
    expect(patch).not.toHaveBeenCalled()
  })

  it('adds a shoe', async () => {
    const w = await mountPanel()
    post.mockResolvedValue(ok(list()))
    await w.get('[data-testid="shoe-name-input"]').setValue('  Vomero ')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/api/v1/shoes', { body: { name: 'Vomero' } })
  })

  it('renames a shoe', async () => {
    const w = await mountPanel()
    patch.mockResolvedValue(ok(list()))
    await w.findAll('[data-testid="shoe-rename"]')[0]!.trigger('click')
    await w.get('[data-testid="shoe-rename-input"]').setValue('Pegasus 41')
    await w.get('[data-testid="shoe-rename-save"]').trigger('click')
    await flushPromises()
    expect(patch).toHaveBeenCalledWith('/api/v1/shoes/{shoe_id}', { params: { path: { shoe_id: 1 } }, body: { name: 'Pegasus 41' } })
    expect(w.find('[data-testid="shoe-rename-input"]').exists()).toBe(false)
  })

  it('retires and unretires', async () => {
    const w = await mountPanel()
    patch.mockResolvedValue(ok(list()))
    const buttons = w.findAll('[data-testid="shoe-retire"]')
    expect(buttons.map((b) => b.text())).toEqual(['Retire', 'Unretire'])
    await buttons[0]!.trigger('click')
    await buttons[1]!.trigger('click')
    await flushPromises()
    expect(patch).toHaveBeenNthCalledWith(1, '/api/v1/shoes/{shoe_id}', { params: { path: { shoe_id: 1 } }, body: { retired: true } })
    expect(patch).toHaveBeenNthCalledWith(2, '/api/v1/shoes/{shoe_id}', { params: { path: { shoe_id: 2 } }, body: { retired: false } })
  })

  it('sets the default with a date that starts at today, offering only active shoes', async () => {
    const w = await mountPanel()
    const date = w.get('[data-testid="shoe-default-date"]').element as HTMLInputElement
    expect(date.value).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(date.value).toBe(new Date().toLocaleDateString('en-CA', { timeZone: 'America/Denver' }))
    expect(w.findAll('[data-testid="shoe-default-select"] option').map((o) => o.text())).toEqual(['No default', 'Pegasus'])
    put.mockResolvedValue(ok(list()))
    await w.get('[data-testid="shoe-default-select"]').setValue('1')
    await w.get('[data-testid="shoe-default-date"]').setValue('2026-09-01')
    await w.get('[data-testid="shoe-default-save"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/shoes/default', { body: { shoe_id: 1, from_date: '2026-09-01' } })
  })

  it('lists the default history with Now and Scheduled marks', async () => {
    const w = await mountPanel()
    const rows = w.findAll('[data-testid="shoe-history-row"]')
    expect(rows).toHaveLength(3)
    expect(rows[0]!.text()).toContain('No default shoe')
    expect(rows[0]!.text()).toContain('Scheduled')
    expect(rows[1]!.text()).toContain('Pegasus')
    expect(rows[1]!.text()).toContain('Now')
    expect(rows[2]!.text()).toContain('Old Ghost')
    expect(rows[2]!.text()).not.toMatch(/Now|Scheduled/)
  })

  it('edits a history row', async () => {
    const w = await mountPanel()
    put.mockResolvedValue(ok(list()))
    await w.findAll('[data-testid="shoe-history-edit"]')[1]!.trigger('click')
    await w.get('[data-testid="shoe-history-date"]').setValue('2026-09-20')
    await w.get('[data-testid="shoe-history-save"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/shoes/default/{from_date}', {
      params: { path: { from_date: '2026-10-01' } },
      body: { shoe_id: 1, from_date: '2026-09-20' },
    })
    expect(w.find('[data-testid="shoe-history-save"]').exists()).toBe(false)
  })

  it('deletes a history row only after the inline confirm', async () => {
    const w = await mountPanel()
    del.mockResolvedValue(ok(list()))
    await w.findAll('[data-testid="shoe-history-delete"]')[0]!.trigger('click')
    expect(del).not.toHaveBeenCalled()
    expect(w.text()).toContain('Delete this change?')
    await w.get('[data-testid="shoe-history-confirm"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/v1/shoes/default/{from_date}', { params: { path: { from_date: '2999-01-01' } } })
  })

  it('cancelling the confirm does not call the API', async () => {
    const w = await mountPanel()
    await w.findAll('[data-testid="shoe-history-delete"]')[0]!.trigger('click')
    await w.get('[data-testid="shoe-history-confirm-cancel"]').trigger('click')
    expect(del).not.toHaveBeenCalled()
    expect(w.text()).not.toContain('Delete this change?')
  })

  it('shows the error when a history edit fails and keeps the row open', async () => {
    const w = await mountPanel()
    put.mockResolvedValue({ data: undefined, response: { ok: false, status: 409 } })
    await w.findAll('[data-testid="shoe-history-edit"]')[1]!.trigger('click')
    await w.get('[data-testid="shoe-history-save"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="shoes-error"]').text()).toContain('not saved')
    expect(w.find('[data-testid="shoe-history-save"]').exists()).toBe(true)
  })

  it('editing the retired-shoe row offers that shoe and sends its id', async () => {
    const w = await mountPanel()
    put.mockResolvedValue(ok(list()))
    await w.findAll('[data-testid="shoe-history-edit"]')[2]!.trigger('click')
    expect(w.findAll('[data-testid="shoe-history-select"] option').map((o) => o.text())).toEqual(['No default shoe', 'Pegasus', 'Old Ghost'])
    await w.get('[data-testid="shoe-history-date"]').setValue('2026-09-02')
    await w.get('[data-testid="shoe-history-save"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/shoes/default/{from_date}', {
      params: { path: { from_date: '2026-09-01' } },
      body: { shoe_id: 2, from_date: '2026-09-02' },
    })
  })

  it('editing the no-default row sends shoe_id null', async () => {
    const w = await mountPanel()
    put.mockResolvedValue(ok(list()))
    await w.findAll('[data-testid="shoe-history-edit"]')[0]!.trigger('click')
    await w.get('[data-testid="shoe-history-save"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/shoes/default/{from_date}', {
      params: { path: { from_date: '2999-01-01' } },
      body: { shoe_id: null, from_date: '2999-01-01' },
    })
  })

  it.each([[409, 'already on that date'], [422, 'another shoe']])('says why a %s edit failed', async (status, text) => {
    const w = await mountPanel()
    put.mockResolvedValue({ data: undefined, response: { ok: false, status } })
    await w.findAll('[data-testid="shoe-history-edit"]')[1]!.trigger('click')
    await w.get('[data-testid="shoe-history-save"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="shoes-error"]').text()).toContain(text)
  })

  it('a 404 reloads the list, closes the row and says the change is gone', async () => {
    const w = await mountPanel()
    put.mockResolvedValue({ data: undefined, response: { ok: false, status: 404 } })
    await w.findAll('[data-testid="shoe-history-edit"]')[1]!.trigger('click')
    get.mockResolvedValue(ok(list({ history: [{ shoe_id: 2, from_date: '2026-09-01' }] })))
    await w.get('[data-testid="shoe-history-save"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="shoes-error"]').text()).toContain('already gone')
    expect(w.find('[data-testid="shoe-history-save"]').exists()).toBe(false)
    expect(w.findAll('[data-testid="shoe-history-row"]')).toHaveLength(1)
  })

  it('shows an error and keeps the list when a write fails', async () => {
    const w = await mountPanel()
    post.mockResolvedValue({ data: undefined, response: { ok: false, status: 422 } })
    await w.get('[data-testid="shoe-name-input"]').setValue('pegasus')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.get('[data-testid="shoes-error"]').text()).toContain('not added')
    expect(w.findAll('[data-testid="shoe-row"]')).toHaveLength(2)
  })
})

describe('ShoePicker', () => {
  beforeEach(() => vi.clearAllMocks())

  async function mountPicker(shoe: object | null, chosen = shoe != null && (shoe as { source: string }).source === 'chosen') {
    const pinia = await setup()
    get.mockResolvedValue(ok(list()))
    const wk = useWorkoutsStore()
    wk.detail = workoutDetail({ shoe, shoe_chosen: chosen } as never)
    const w = mount(ShoePicker, { props: { workoutId: 'w-1', shoe: shoe as never, chosen }, global: { plugins: [pinia] } })
    await flushPromises()
    return { w, wk }
  }
  const def = { id: 1, name: 'Pegasus', retired: false, source: 'default' }
  const sel = (w: ReturnType<typeof mount>) => w.get('[data-testid="shoe-picker"]')

  it('offers active shoes, No shoe and Use default, and hides retired shoes unless current', async () => {
    const { w } = await mountPicker(def)
    expect(w.findAll('option').map((o) => o.text())).toEqual(['Pegasus', 'No shoe', 'Use default'])
    expect(w.get('[data-testid="shoe-current"]').text()).toContain('Pegasus (default)')
    const retired = await mountPicker({ id: 2, name: 'Old Ghost', retired: true, source: 'chosen' })
    expect(retired.w.findAll('option').map((o) => o.text())).toEqual(['Pegasus', 'Old Ghost (retired)', 'No shoe', 'Use default'])
  })

  it('selects Use default when not chosen, the shoe when chosen, and No shoe when chosen with none', async () => {
    expect((sel((await mountPicker(def)).w).element as HTMLSelectElement).value).toBe('default')
    expect((sel((await mountPicker(null, false)).w).element as HTMLSelectElement).value).toBe('default')
    expect((sel((await mountPicker({ ...def, source: 'chosen' })).w).element as HTMLSelectElement).value).toBe('1')
    expect((sel((await mountPicker(null, true)).w).element as HTMLSelectElement).value).toBe('none')
  })

  it('still shows a chosen shoe when the shoe list failed to load, and says so', async () => {
    const pinia = await setup()
    get.mockResolvedValue({ data: undefined, response: { ok: false, status: 500 } })
    const w = mount(ShoePicker, { props: { workoutId: 'w-1', shoe: { ...def, source: 'chosen' } as never, chosen: true }, global: { plugins: [pinia] } })
    await flushPromises()
    expect((w.get('[data-testid="shoe-picker"]').element as HTMLSelectElement).value).toBe('1')
    expect(w.find('[data-testid="shoe-list-error"]').exists()).toBe(true)
  })

  it('chooses a shoe and updates the shown shoe', async () => {
    const { w, wk } = await mountPicker(null)
    put.mockResolvedValue({ data: { shoe: { id: 1, name: 'Pegasus', retired: false, source: 'chosen' }, chosen: true }, response: { ok: true } })
    await sel(w).setValue('1')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/workouts/{workout_id}/shoe', { params: { path: { workout_id: 'w-1' } }, body: { shoe_id: 1 } })
    expect(wk.detail?.shoe?.source).toBe('chosen')
    expect(wk.detail?.shoe_chosen).toBe(true)
  })

  it('chooses no shoe', async () => {
    const { w, wk } = await mountPicker(def)
    put.mockResolvedValue({ data: { shoe: null, chosen: true }, response: { ok: true } })
    await sel(w).setValue('none')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/workouts/{workout_id}/shoe', { params: { path: { workout_id: 'w-1' } }, body: { shoe_id: null } })
    expect(wk.detail?.shoe).toBeNull()
  })

  it('uses the default by deleting the override', async () => {
    const { w, wk } = await mountPicker({ ...def, source: 'chosen' })
    del.mockResolvedValue({ data: { shoe: def, chosen: false }, response: { ok: true } })
    await sel(w).setValue('default')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/v1/workouts/{workout_id}/shoe', { params: { path: { workout_id: 'w-1' } } })
    expect(wk.detail?.shoe?.source).toBe('default')
    expect(wk.detail?.shoe_chosen).toBe(false)
  })

  it('shows an error and leaves the shoe unchanged on failure', async () => {
    const { w, wk } = await mountPicker(def)
    put.mockResolvedValue({ data: undefined, response: { ok: false, status: 500 } })
    await sel(w).setValue('none')
    await flushPromises()
    expect(w.get('[data-testid="shoe-error"]').text()).toContain('not saved')
    expect(wk.detail?.shoe).toEqual(def)
    expect((sel(w).element as HTMLSelectElement).value).toBe('default')
  })
})
