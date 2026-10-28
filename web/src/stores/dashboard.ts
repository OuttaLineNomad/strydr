import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { DashboardOut, SyncStatus } from '@/api/types'

export const RANGES = [4, 12, 26, 52] as const

export const useDashboardStore = defineStore('dashboard', () => {
  const data = ref<DashboardOut | null>(null)
  const sync = ref<SyncStatus | null>(null)
  const weeks = ref<number>(12)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(w?: number) {
    if (w !== undefined) weeks.value = w
    loading.value = true
    error.value = null
    try {
      const [d, s] = await Promise.all([
        api.GET('/api/v1/dashboard', { params: { query: { weeks: weeks.value } } }),
        api.GET('/api/v1/sync-status'),
      ])
      if (d.data) data.value = d.data
      else error.value = 'Your dashboard could not load. Try again in a moment.'
      sync.value = s.data ?? null
    } catch {
      error.value = 'Your dashboard could not load. Check your connection and try again.'
    } finally {
      loading.value = false
    }
  }

  return { data, sync, weeks, loading, error, load }
})
