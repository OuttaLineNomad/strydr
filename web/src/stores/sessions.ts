import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { LadderPoint, SessionIn, SessionOut, SessionSummary } from '@/api/types'

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
  async function post(body: SessionIn): Promise<{ out: 'ok' | 'retry' | 'rejected'; id: number | null }> {
    try {
      const { data, response } = await api.POST('/api/v1/sessions', { body })
      if (data) return { out: 'ok', id: typeof data.id === 'number' ? data.id : null }
      const st = response?.status ?? 0
      return { out: st === 422 ? 'rejected' : 'retry', id: null }
    } catch {
      return { out: 'retry', id: null }
    }
  }

  /** Sends the record. `'kept'` means it waits on this phone until it can sync. */
  async function save(body: SessionIn): Promise<{ result: 'saved' | 'kept' | 'rejected' | 'unsaved'; id: number | null }> {
    const { out, id } = await post(body)
    if (out === 'ok') return { result: 'saved', id }
    if (out === 'rejected') {
      deadLetter(body)
      return { result: 'rejected', id: null }
    }
    const box = readBox()
    box.push(body)
    const stored = writeBox(box)
    pending.value = box.length
    return { result: stored ? 'kept' : 'unsaved', id: null }
  }

  /** Tries every kept record once; returns how many went through. */
  async function flush(): Promise<number> {
    const box = readBox()
    if (!box.length) return 0
    const left: SessionIn[] = []
    let sent = 0
    for (const body of box) {
      const { out: r } = await post(body)
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

  /** The summary built on read; 'missing' when the session does not exist (404); null when it could not load. */
  async function summary(id: number): Promise<SessionSummary | 'missing' | null> {
    try {
      const { data, response } = await api.GET('/api/v1/sessions/{session_id}/summary', { params: { path: { session_id: id } } })
      if (data) return data
      return response?.status === 404 ? 'missing' : null
    } catch {
      return null
    }
  }

  /** Saves a 1-10 effort. True when the server took it. */
  async function setEffort(id: number, effort: number): Promise<boolean> {
    try {
      const { data } = await api.PUT('/api/v1/sessions/{session_id}/effort', { params: { path: { session_id: id } }, body: { effort } })
      return !!data
    } catch {
      return false
    }
  }

  /** Saves the reps done in a minute that fell short (null takes the answer back). True when the server took it. */
  async function setShort(id: number, minute: number, reps: number | null): Promise<boolean> {
    try {
      const { data } = await api.PUT('/api/v1/sessions/{session_id}/short', {
        params: { path: { session_id: id } },
        body: { [String(minute)]: reps },
      })
      return !!data
    } catch {
      return false
    }
  }

  /** Records the lower rung done for one set ("move:instance"); null restores the planned one. True when the server took it. */
  async function setRung(id: number, key: string, rung: number | null): Promise<boolean> {
    try {
      const { data } = await api.PUT('/api/v1/sessions/{session_id}/rungs', { params: { path: { session_id: id } }, body: { [key]: rung } })
      return !!data
    } catch {
      return false
    }
  }

  /** Deletes a saved session. True when it is gone (a 404 means it already was). */
  async function remove(id: number): Promise<boolean> {
    try {
      const { response } = await api.DELETE('/api/v1/sessions/{session_id}', { params: { path: { session_id: id } } })
      return response.ok || response.status === 404
    } catch {
      return false
    }
  }

  /** The staircase of a ladder: the best set of each session, oldest first. Empty when it could not load. */
  async function ladderHistory(ladder: 'push-up' | 'pull-up'): Promise<LadderPoint[]> {
    try {
      const { data } = await api.GET('/api/v1/ladders/{ladder}/history', { params: { path: { ladder } } })
      return data ?? []
    } catch {
      return []
    }
  }

  return { pending, save, flush, list, summary, setEffort, setShort, setRung, remove, ladderHistory }
})
