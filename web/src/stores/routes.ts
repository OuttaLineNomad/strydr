import { ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { RouteDetail, RouteOut } from '@/api/types'

export const useRoutesStore = defineStore('routes', () => {
  const items = ref<RouteOut[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const detail = shallowRef<RouteDetail | null>(null)
  const detailLoading = ref(false)
  const detailError = ref<string | null>(null)
  const overrideBusy = ref(false)
  const overrideError = ref<string | null>(null)

  async function loadList() {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.GET('/api/v1/routes')
      if (!data) error.value = 'Your routes could not load. Try again in a moment.'
      else items.value = data as RouteOut[]
    } catch {
      error.value = 'Your routes could not load. Check your connection and try again.'
    } finally {
      loading.value = false
    }
  }

  async function loadDetail(key: string) {
    detailLoading.value = true
    detailError.value = null
    detail.value = null
    try {
      const { data, response } = await api.GET('/api/v1/routes/{route_key}', { params: { path: { route_key: key } } })
      // openapi-fetch widens coordinate tuples to number[]; the shape is otherwise identical.
      if (data) detail.value = data as RouteDetail
      else detailError.value = response?.status === 404 ? 'That route does not exist.' : 'This route could not load. Try again in a moment.'
    } catch {
      detailError.value = 'This route could not load. Check your connection and try again.'
    } finally {
      detailLoading.value = false
    }
  }

  /** Join or split two runs. The API recomputes routes afterwards, so the caller reloads. */
  async function addOverride(action: 'join' | 'split', a: string, b: string): Promise<boolean> {
    overrideBusy.value = true
    overrideError.value = null
    try {
      const { data } = await api.POST('/api/v1/routes/overrides', { body: { action, workout_a: a, workout_b: b } })
      if (!data) {
        overrideError.value = 'That change was not saved. Try again.'
        return false
      }
      return true
    } catch {
      overrideError.value = 'That change was not saved. Check your connection and try again.'
      return false
    } finally {
      overrideBusy.value = false
    }
  }

  async function removeOverride(a: string, b: string): Promise<boolean> {
    overrideBusy.value = true
    overrideError.value = null
    try {
      const { response } = await api.DELETE('/api/v1/routes/overrides', { params: { query: { workout_a: a, workout_b: b } } })
      if (!response.ok) {
        overrideError.value = 'That change was not undone. Try again.'
        return false
      }
      return true
    } catch {
      overrideError.value = 'That change was not undone. Check your connection and try again.'
      return false
    } finally {
      overrideBusy.value = false
    }
  }

  /**
   * API gap: the run detail carries no route_key. Until it does, look the run up in the
   * route details (newest routes first, capped) and cache the answer.
   */
  const keyByRun = ref<Record<string, string | null>>({})
  async function routeKeyFor(workoutId: string): Promise<string | null> {
    if (workoutId in keyByRun.value) return keyByRun.value[workoutId]!
    try {
      const { data: list } = await api.GET('/api/v1/routes')
      for (const r of (list ?? []).slice(0, 25)) {
        const { data } = await api.GET('/api/v1/routes/{route_key}', { params: { path: { route_key: r.route_key } } })
        if (data?.runs.some((w) => w.workout_id === workoutId)) {
          keyByRun.value[workoutId] = r.route_key
          return r.route_key
        }
      }
      keyByRun.value[workoutId] = null
    } catch {
      /* no link is better than an error on the run page */
    }
    return null
  }

  return { removeOverride, routeKeyFor, items, loading, error, detail, detailLoading, detailError, overrideBusy, overrideError, loadList, loadDetail, addOverride }
})
