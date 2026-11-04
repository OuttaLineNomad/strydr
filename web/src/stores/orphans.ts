import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import { usePlansStore } from '@/stores/plans'
import { useStreakStore } from '@/stores/streak'
import type { Orphan, OrphanLogIn } from '@/api/types'

/** Watch strength workouts no session overlaps, asked about one at a time. The server decides what is an orphan. */
export const useOrphansStore = defineStore('orphans', () => {
  const items = ref<Orphan[]>([])
  const loaded = ref(false)
  const busy = ref(false)
  const error = ref<string | null>(null)
  /** The session just logged from the prompt, so it can link to its summary. */
  const logged = ref<{ id: number; plan: string } | null>(null)
  const current = computed(() => items.value[0] ?? null)

  async function load() {
    logged.value = null
    try {
      const { data } = await api.GET('/api/v1/orphans')
      if (Array.isArray(data)) items.value = data
    } catch {
      // The prompt is optional: with no answer there is nothing to ask.
    } finally {
      loaded.value = true
    }
  }

  function drop(workoutId: string) {
    items.value = items.value.filter((o) => o.workout_id !== workoutId)
  }

  async function log(workoutId: string, body: OrphanLogIn, planName: string): Promise<boolean> {
    busy.value = true
    error.value = null
    try {
      const { data, response } = await api.POST('/api/v1/orphans/{workout_id}/log', { params: { path: { workout_id: workoutId } }, body })
      if (data && typeof data.id === 'number') {
        logged.value = { id: data.id, plan: planName }
        drop(workoutId)
        // The new session changes Recent sessions, the Last: lines and the streak.
        const plans = usePlansStore()
        const streak = useStreakStore()
        if (plans.loaded) void plans.load()
        if (streak.data) void streak.load()
        return true
      }
      if (response?.status === 404) {
        drop(workoutId) // the workout is gone
        return false
      }
      error.value = 'That did not save. Try again.'
    } catch {
      error.value = 'That did not save. Check your connection.'
    } finally {
      busy.value = false
    }
    return false
  }

  async function dismiss(workoutId: string): Promise<boolean> {
    busy.value = true
    error.value = null
    try {
      const { response } = await api.POST('/api/v1/orphans/{workout_id}/dismiss', { params: { path: { workout_id: workoutId } } })
      if (response.ok || response.status === 404) {
        drop(workoutId)
        return true
      }
      error.value = 'That did not save. Try again.'
    } catch {
      error.value = 'That did not save. Check your connection.'
    } finally {
      busy.value = false
    }
    return false
  }

  return { items, loaded, busy, error, logged, current, load, log, dismiss }
})
