import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import NoteEditor from '../NoteEditor.vue'

const put = vi.mocked(api.PUT) as unknown as ReturnType<typeof vi.fn>
const del = vi.mocked(api.DELETE) as unknown as ReturnType<typeof vi.fn>

function mountIt(note: { text: string | null; rpe: number | null; updated_at: string } | null = null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(NoteEditor, { props: { workoutId: 'w-1', note }, global: { plugins: [pinia] } })
}

describe('NoteEditor', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps Save off until there is something to save', async () => {
    const w = mountIt()
    expect(w.get('[data-testid="note-save"]').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="note-text"]').setValue('Felt smooth')
    expect(w.get('[data-testid="note-save"]').attributes('disabled')).toBeUndefined()
  })

  it('saves text and RPE through PUT and confirms', async () => {
    put.mockResolvedValue({ data: { text: 'Felt smooth', rpe: 4, updated_at: '2026-10-25T20:00:00Z' }, response: { ok: true, status: 200 } })
    const w = mountIt()
    await w.get('[data-testid="note-text"]').setValue('Felt smooth')
    await w.get('[data-testid="rpe-4"]').trigger('click')
    expect(w.get('[data-testid="rpe-4"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-testid="note-save"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/api/v1/workouts/{workout_id}/note', {
      params: { path: { workout_id: 'w-1' } },
      body: { text: 'Felt smooth', rpe: 4 },
    })
    expect(w.get('[data-testid="note-status"]').text()).toBe('Note saved.')
  })

  it('deletes an existing note through DELETE and clears the form', async () => {
    del.mockResolvedValue({ response: { ok: true, status: 204 } })
    const w = mountIt({ text: 'Old note', rpe: 7, updated_at: '2026-10-24T20:00:00Z' })
    expect((w.get('[data-testid="note-text"]').element as HTMLTextAreaElement).value).toBe('Old note')
    expect(w.get('[data-testid="rpe-7"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-testid="note-delete"]').trigger('click')
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/api/v1/workouts/{workout_id}/note', { params: { path: { workout_id: 'w-1' } } })
    expect((w.get('[data-testid="note-text"]').element as HTMLTextAreaElement).value).toBe('')
    expect(w.get('[data-testid="note-status"]').text()).toBe('Note deleted.')
  })

  it('shows an error and keeps the text when saving fails', async () => {
    put.mockResolvedValue({ data: undefined, error: {}, response: { ok: false, status: 500 } })
    const w = mountIt()
    await w.get('[data-testid="note-text"]').setValue('Keep me')
    await w.get('[data-testid="note-save"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="note-error"]').text()).toContain('not saved')
    expect((w.get('[data-testid="note-text"]').element as HTMLTextAreaElement).value).toBe('Keep me')
  })
})
