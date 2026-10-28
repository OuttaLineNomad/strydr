import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
vi.mock('@/api', () => ({ api: { GET: vi.fn() } }))
import { api } from '@/api'
import ImportPanel from '../ImportPanel.vue'

const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>

const st = (over: object = {}) => ({
  payload_id: 1, state: 'queued', workouts: 0, merged: 0, kept_existing: 0, metrics: 0, nights: 0,
  date_from: null, date_to: null, error: null, updated_at: '2026-10-28T10:00:00Z', ...over,
})
const reply = (body: unknown) => ({ data: body, response: { ok: true, status: 200 } })

class FakeXHR {
  static last: FakeXHR
  upload: { onprogress: ((e: object) => void) | null } = { onprogress: null }
  withCredentials = false
  status = 0
  responseText = ''
  method = ''
  url = ''
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: unknown = null
  constructor() { FakeXHR.last = this }
  open(m: string, u: string) { this.method = m; this.url = u }
  setRequestHeader() {}
  send(b: unknown) { this.sent = b }
  abort() {}
}

function pick(w: ReturnType<typeof mount>, name = 'export.zip') {
  const input = w.get('[data-testid="import-file"]')
  Object.defineProperty(input.element, 'files', { value: [new File(['PK'], name)], configurable: true })
  return input.trigger('change')
}

describe('ImportPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    get.mockReset()
    vi.stubGlobal('XMLHttpRequest', FakeXHR)
  })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

  it('uploads with progress, then polls while writing and shows counts, range, done', async () => {
    get.mockResolvedValueOnce(reply(null))
    const w = mount(ImportPanel)
    await flushPromises()
    expect(w.find('[data-testid="import-status"]').exists()).toBe(false)

    await pick(w)
    const x = FakeXHR.last
    expect(x.method).toBe('POST')
    expect(x.url).toBe('/api/v1/import/apple')
    expect(x.withCredentials).toBe(true)
    x.upload.onprogress!({ lengthComputable: true, loaded: 50, total: 100 })
    await flushPromises()
    expect(w.get('[data-testid="import-progress"]').attributes('aria-valuenow')).toBe('50')

    x.status = 202
    x.responseText = JSON.stringify(st({ state: 'validating' }))
    x.onload!()
    await flushPromises()
    expect(w.find('[data-testid="import-progress"]').exists()).toBe(false)
    expect(w.get('[data-testid="import-state"]').text()).toBe('Checking the export')
    expect(w.find('[data-testid="import-counts"]').exists()).toBe(false) // no counts before writing starts

    get.mockResolvedValueOnce(reply(st({ state: 'writing', workouts: 3 })))
    await vi.advanceTimersByTimeAsync(2000)
    expect(w.get('[data-testid="import-state"]').text()).toBe('Importing')
    expect(w.get('[data-testid="import-counts"]').text()).toContain('3 new workouts')

    get.mockResolvedValueOnce(reply(st({ state: 'done', workouts: 5, merged: 2, kept_existing: 1, metrics: 40, nights: 9, date_from: '2026-03-01', date_to: '2026-03-31' })))
    await vi.advanceTimersByTimeAsync(2000)
    expect(w.get('[data-testid="import-state"]').text()).toBe('Done')
    expect(w.get('[data-testid="import-counts"]').text()).toContain('5 new workouts, 2 merged with existing, 1 already there')
    expect(w.get('[data-testid="import-range"]').text()).toContain('2026-03-01 to 2026-03-31')

    const calls = get.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(get.mock.calls.length).toBe(calls) // polling stopped once done
  })

  it('shows the error class when the import failed', async () => {
    get.mockResolvedValueOnce(reply(st({ state: 'failed', error: 'AdapterError' })))
    const w = mount(ImportPanel)
    await flushPromises()
    expect(w.get('[data-testid="import-state"]').text()).toBe('Failed')
    expect(w.get('[data-testid="import-error"]').text()).toContain('AdapterError')
  })

  it('rejects a non-zip with a message and the server 415 too', async () => {
    get.mockResolvedValueOnce(reply(null))
    const w = mount(ImportPanel)
    await flushPromises()
    await pick(w, 'notes.txt')
    expect(w.get('[data-testid="import-upload-error"]').text()).toContain('export.zip')

    await pick(w)
    FakeXHR.last.status = 415
    FakeXHR.last.onload!()
    await flushPromises()
    expect(w.get('[data-testid="import-upload-error"]').text()).toContain('not a zip')
  })

  it.each([
    [413, 'too large'],
    [409, 'already stored'],
    [400, 'empty'],
    [500, 'upload failed'],
  ])('shows a specific message for a %i', async (code, text) => {
    get.mockResolvedValueOnce(reply(null))
    const w = mount(ImportPanel)
    await flushPromises()
    await pick(w)
    FakeXHR.last.status = code
    FakeXHR.last.onload!()
    await flushPromises()
    expect(w.get('[data-testid="import-upload-error"]').text()).toContain(text)
  })

  it('stops polling and says so when the session ends mid-import', async () => {
    get.mockResolvedValueOnce(reply(st({ state: 'writing' })))
    const w = mount(ImportPanel)
    await flushPromises()
    get.mockResolvedValueOnce({ data: undefined, response: { ok: false, status: 401 } })
    await vi.advanceTimersByTimeAsync(2000)
    expect(w.get('[data-testid="import-upload-error"]').text()).toContain('signed out')
    const calls = get.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(get.mock.calls.length).toBe(calls)
  })
})
