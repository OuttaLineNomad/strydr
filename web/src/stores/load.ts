import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { LoadOut } from '@/api/types'

export const LOAD_RANGES = [42, 90, 180, 365] as const

export const useLoadStore = defineStore('load', () => {
  const days = ref<number>(90)
  const data = ref<LoadOut | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(n?: number) {
    if (n !== undefined) days.value = n
    loading.value = true
    error.value = null
    try {
      const { data: d } = await api.GET('/api/v1/load', { params: { query: { days: days.value } } })
      if (!d) error.value = 'Your training load could not load. Try again in a moment.'
      else data.value = d
    } catch {
      error.value = 'Your training load could not load. Check your connection and try again.'
    } finally {
      loading.value = false
    }
  }

  return { days, data, loading, error, load }
})
