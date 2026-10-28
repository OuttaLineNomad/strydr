import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import WeekNoteEditor from '../WeekNoteEditor.vue'

const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>
const del = vi.mocked(api.DELETE) as unknown as ReturnType<typeof vi.fn>

function mountIt(note: { text: string; updated_at: string } | null = null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(WeekNoteEditor, { props: { weekId: '2026-W43', note }, global: { plugins: [pinia] } })
}

describe('WeekNoteEditor', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps Save off until there is text', async () => {
    const w = mountIt()
    expect(w.get('[data-testid="week-note-save"]').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="week-note-text"]').setValue('Good week')
    expect(w.get('[data-testid="week-note-save"]').attributes('disabled')).toBeUndefined()
  })

  it('saves through PUT and confirms', async () => {
    put.mockResolvedValue({ data: { text: 'Good week', updated_at: '2026-10-25T20:00:00Z' }, response: { ok: true, status: 200 } })
    const w = mountIt()
    await w.get('[data-testid="week-note-text"]').setValue('Good week')
    await w.get('[data-testid="week-note-save"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/weeks/{week_id}/note', { params: { path: { week_id: '2026-W43' } }, body: { text: 'Good week' } })
    expect(w.get('[data-testid="week-note-status"]').text()).toBe('Note saved.')
  })

  it('deletes through DELETE and clears the box', async () => {
    del.mockResolvedValue({ response: { ok: true, status: 204 } })
    const w = mountIt({ text: 'Old', updated_at: '2026-10-24T20:00:00Z' })
    expect((w.get('[data-testid="week-note-text"]').element as HTMLTextAreaElement).value).toBe('Old')
    await w.get('[data-testid="week-note-delete"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/v1/weeks/{week_id}/note', { params: { path: { week_id: '2026-W43' } } })
    expect((w.get('[data-testid="week-note-text"]').element as HTMLTextAreaElement).value).toBe('')
    expect(w.get('[data-testid="week-note-status"]').text()).toBe('Note deleted.')
  })

  it('keeps the text and shows an error when saving fails', async () => {
    put.mockResolvedValue({ data: undefined, error: {}, response: { ok: false, status: 500 } })
    const w = mountIt()
    await w.get('[data-testid="week-note-text"]').setValue('Keep me')
    await w.get('[data-testid="week-note-save"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="week-note-error"]').text()).toContain('not saved')
    expect((w.get('[data-testid="week-note-text"]').element as HTMLTextAreaElement).value).toBe('Keep me')
  })
})
