import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { SessionIn, SessionOut } from '@/api/types'

const KEY = 'strydr.sessionOutbox'
/** Records the server refused as invalid (422). Kept, never retried and never deleted. */
const DEAD = 'strydr.sessionDeadLetter'

function readBox(key = KEY): SessionIn[] {
  try {
    const raw = localStorage.getItem(key)
    const v = raw ? JSON.parse(raw) : []
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}
/** True if the box was stored (or emptied). False when storage is unavailable or full. */
function writeBox(box: SessionIn[], key = KEY): boolean {
  try {
    if (box.length) localStorage.setItem(key, JSON.stringify(box))
    else localStorage.removeItem(key)
    return true
  } catch {
    return false
  }
}
function deadLetter(body: SessionIn) {
  writeBox([...readBox(DEAD), body], DEAD)
}

/** Saved live workouts. A save that fails is kept in localStorage and retried when the Workouts page loads. */
export const useSessionsStore = defineStore('sessions', () => {
  const pending = ref(readBox().length)

  /** 'ok', 'retry' (offline, server error, signed out) or 'rejected' (the server will never take this record). */
  async function post(body: SessionIn): Promise<'ok' | 'retry' | 'rejected'> {
    try {
      const { data, response } = await api.POST('/api/v1/sessions', { body })
      if (data) return 'ok'
      const st = response?.status ?? 0
      return st === 422 ? 'rejected' : 'retry'
    } catch {
      return 'retry'
    }
  }

  /** Sends the record. `'kept'` means it waits on this phone until it can sync. */
  async function save(body: SessionIn): Promise<'saved' | 'kept' | 'rejected' | 'unsaved'> {
    const out = await post(body)
    if (out === 'ok') return 'saved'
    if (out === 'rejected') {
      deadLetter(body)
      return 'rejected'
    }
    const box = readBox()
    box.push(body)
    const stored = writeBox(box)
    pending.value = box.length
    return stored ? 'kept' : 'unsaved'
  }

  /** Tries every kept record once; returns how many went through. */
  async function flush(): Promise<number> {
    const box = readBox()
    if (!box.length) return 0
    const left: SessionIn[] = []
    let sent = 0
    for (const body of box) {
      const r = await post(body)
      if (r === 'ok') sent++
      else if (r === 'retry') left.push(body)
      else deadLetter(body)
    }
    // Records added while this ran stay too.
    const added = readBox().slice(box.length)
    writeBox([...left, ...added])
    pending.value = left.length + added.length
    return sent
  }

  async function list(planId?: number, limit = 20): Promise<SessionOut[]> {
    try {
      const { data } = await api.GET('/api/v1/sessions', { params: { query: { plan_id: planId, limit } } })
      return data ?? []
    } catch {
      return []
    }
  }

  return { pending, save, flush, list }
})
