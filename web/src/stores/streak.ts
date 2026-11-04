import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { StreakOut } from '@/api/types'

/** The weekly home-workout streak (CAP-10). Computed by the server on read. */
export const useStreakStore = defineStore('streak', () => {
  const data = ref<StreakOut | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    try {
      const { data: d } = await api.GET('/api/v1/streak')
      if (d && Array.isArray((d as StreakOut).recent)) data.value = d
      else error.value = 'Your streak could not load.'
    } catch {
      error.value = 'Your streak could not load. Check your connection.'
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, load }
})
