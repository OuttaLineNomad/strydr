import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { PlanIn, PlanOut } from '@/api/types'

const TAKEN = 'a workout with that name exists'

/** The saved home-workout plans. The library holds them all, so the edit page and the name suggestions read from here. */
export const usePlansStore = defineStore('plans', () => {
  const plans = ref<PlanOut[]>([])
  const loaded = ref(false)
  const error = ref<string | null>(null)
  /** An inline message for the name field (a 422 for a taken name). */
  const nameError = ref<string | null>(null)
  const busy = ref(false)

  async function load() {
    error.value = null
    try {
      const { data } = await api.GET('/api/v1/plans')
      if (data) {
        plans.value = data
        loaded.value = true
      } else error.value = 'Your workouts could not load.'
    } catch {
      error.value = 'Your workouts could not load. Check your connection.'
    }
  }

  /** Runs one write; on failure the list stays as it was and `error` says why. */
  async function write<T>(call: () => Promise<{ data?: T; error?: unknown; response?: { status: number } }>, fail: string): Promise<T | null> {
    busy.value = true
    error.value = null
    nameError.value = null
    try {
      const { data, error: body, response } = await call()
      if (data === undefined && response && response.status >= 200 && response.status < 300) return null // 204
      if (data === undefined) {
        if (response?.status === 422 && (body as { detail?: unknown } | undefined)?.detail === TAKEN) nameError.value = 'Another workout already has this name.'
        error.value = fail
        return null
      }
      return data
    } catch {
      error.value = `${fail} Check your connection.`
      return null
    } finally {
      busy.value = false
    }
  }

  async function create(body: PlanIn): Promise<PlanOut | null> {
    const p = await write(() => api.POST('/api/v1/plans', { body }), 'The workout was not saved.')
    if (p) plans.value = [...plans.value, p]
    return p
  }
  async function update(id: number, body: PlanIn): Promise<PlanOut | null> {
    const p = await write(() => api.PUT('/api/v1/plans/{plan_id}', { params: { path: { plan_id: id } }, body }), 'The workout was not saved.')
    if (p) plans.value = plans.value.map((x) => (x.id === id ? p : x))
    return p
  }
  async function duplicate(id: number): Promise<PlanOut | null> {
    const p = await write(() => api.POST('/api/v1/plans/{plan_id}/duplicate', { params: { path: { plan_id: id } } }), 'The workout was not duplicated.')
    if (p) plans.value = [...plans.value, p]
    return p
  }
  async function remove(id: number): Promise<boolean> {
    busy.value = true
    error.value = null
    try {
      const { response } = await api.DELETE('/api/v1/plans/{plan_id}', { params: { path: { plan_id: id } } })
      if (response.ok || response.status === 404) {
        plans.value = plans.value.filter((x) => x.id !== id)
        return true
      }
      error.value = 'The workout was not deleted. Try again.'
      return false
    } catch {
      error.value = 'The workout was not deleted. Check your connection.'
      return false
    } finally {
      busy.value = false
    }
  }

  /** Every move name used in any plan, once each, for the name suggestions. */
  function moveNames(): string[] {
    const seen = new Map<string, string>()
    for (const p of plans.value) for (const m of p.moves) if (!seen.has(m.name.toLowerCase())) seen.set(m.name.toLowerCase(), m.name)
    return [...seen.values()].sort((a, b) => a.localeCompare(b))
  }

  return { plans, loaded, error, nameError, busy, load, create, update, duplicate, remove, moveNames }
})
