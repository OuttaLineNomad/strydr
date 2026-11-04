import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), POST: vi.fn() } }))
import { api } from '@/api'
import { useSessionsStore } from '../sessions'
import { memoryStorage } from '@/mocks/memoryStorage'
import type { SessionIn } from '@/api/types'

const post = vi.mocked(api.POST) as unknown as ReturnType<typeof vi.fn>
const KEY = 'strydr.sessionOutbox'
const rec = (n = 1): SessionIn => ({
  plan_id: 1,
  plan: { name: 'P', format: 'amrap', cap_min: 20, emom_min: null, rounds: null, video_url: null, moves: [{ name: 'Swing', reps: 10, seconds: null, weight_kg: null }] },
  weight_kg: null, start_utc: `2026-11-0${n}T10:00:00.000Z`, end_utc: `2026-11-0${n}T10:20:00.000Z`, events: [], rounds_done: 3, partial_moves: 2, fell_short: [],
})

describe('sessions store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('localStorage', memoryStorage())
    setActivePinia(createPinia())
  })

  it('posts a record and keeps nothing when the server takes it', async () => {
    post.mockResolvedValue({ data: { id: 1 }, response: { status: 201 } })
    expect(await useSessionsStore().save(rec())).toBe('saved')
    expect(post).toHaveBeenCalledWith('/api/v1/sessions', { body: rec() })
    expect(localStorage.getItem(KEY)).toBeNull()
  })

  it('keeps a failed record in localStorage, on a 500 and on a network error', async () => {
    const s = useSessionsStore()
    post.mockResolvedValueOnce({ data: undefined, response: { status: 500 } })
    expect(await s.save(rec(1))).toBe('kept')
    post.mockRejectedValueOnce(new Error('offline'))
    expect(await s.save(rec(2))).toBe('kept')
    expect(JSON.parse(localStorage.getItem(KEY)!)).toHaveLength(2)
    expect(s.pending).toBe(2)
  })

  it('retries the outbox: sent records go, failed ones stay', async () => {
    localStorage.setItem(KEY, JSON.stringify([rec(1), rec(2), rec(3)]))
    const s = useSessionsStore()
    post.mockResolvedValueOnce({ data: { id: 1 }, response: { status: 201 } })
    post.mockRejectedValueOnce(new Error('offline'))
    post.mockResolvedValueOnce({ data: { id: 3 }, response: { status: 201 } })
    expect(await s.flush()).toBe(2)
    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual([rec(2)])
    post.mockResolvedValueOnce({ data: { id: 2 }, response: { status: 201 } })
    expect(await s.flush()).toBe(1)
    expect(localStorage.getItem(KEY)).toBeNull()
    expect(await s.flush()).toBe(0)
  })

  it('moves a 422 record to a dead-letter key instead of retrying or deleting it', async () => {
    localStorage.setItem(KEY, JSON.stringify([rec(1)]))
    post.mockResolvedValue({ data: undefined, response: { status: 422 } })
    expect(await useSessionsStore().flush()).toBe(0)
    expect(localStorage.getItem(KEY)).toBeNull()
    expect(JSON.parse(localStorage.getItem('strydr.sessionDeadLetter')!)).toEqual([rec(1)])
  })

  it('a fresh save the server rejects goes to the dead letter too', async () => {
    post.mockResolvedValue({ data: undefined, response: { status: 422 } })
    expect(await useSessionsStore().save(rec())).toBe('rejected')
    expect(JSON.parse(localStorage.getItem('strydr.sessionDeadLetter')!)).toHaveLength(1)
  })

  it.each([400, 401, 404, 408, 413, 429, 503])('a %i is retried, not dropped', async (status) => {
    post.mockResolvedValue({ data: undefined, response: { status } })
    expect(await useSessionsStore().save(rec())).toBe('kept')
    expect(JSON.parse(localStorage.getItem(KEY)!)).toHaveLength(1)
    expect(localStorage.getItem('strydr.sessionDeadLetter')).toBeNull()
  })

  it('survives localStorage throwing', async () => {
    const blocked = () => {
      throw new Error('blocked')
    }
    vi.stubGlobal('localStorage', { getItem: blocked, setItem: blocked, removeItem: blocked })
    post.mockRejectedValue(new Error('offline'))
    expect(await useSessionsStore().save(rec())).toBe('unsaved') // nothing could be stored, and it says so
  })

  it('lists sessions for a plan', async () => {
    const get = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
    get.mockResolvedValue({ data: [{ id: 1 }], response: { status: 200 } })
    expect(await useSessionsStore().list(5)).toEqual([{ id: 1 }])
    expect(get).toHaveBeenCalledWith('/api/v1/sessions', { params: { query: { plan_id: 5, limit: 20 } } })
  })
})
