import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { ProfileOut, ProfileSettings } from '@/api/types'
import type { UnitSystem } from '@/lib/units'

const POLL_MS = 2000
const POLL_MAX = 30

export const useSettingsStore = defineStore('settings', () => {
  const profile = ref<ProfileOut | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)
  const recalculating = ref(false)

  const units = computed<UnitSystem>(() => profile.value?.settings.units ?? 'imperial')
  const homeTz = computed(() => profile.value?.settings.home_tz)
  const resolved = computed(() => profile.value?.resolved ?? null)

  function apply(p: ProfileOut) {
    profile.value = p
    recalculating.value = p.recompute_pending
  }

  async function load(): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const { data, response } = await api.GET('/api/v1/profile')
      if (data) {
        apply(data)
        return true
      }
      if (response.status !== 401) error.value = 'Your settings could not load. Try again in a moment.'
      return false
    } catch {
      error.value = 'Your settings could not load. Check your connection and try again.'
      return false
    } finally {
      loading.value = false
    }
  }

  async function save(settings: ProfileSettings): Promise<boolean> {
    saving.value = true
    error.value = null
    try {
      const { data } = await api.PUT('/api/v1/profile', { body: settings })
      if (!data) {
        error.value = 'Your settings were not saved. Check the values and try again.'
        return false
      }
      apply(data)
      if (data.recompute_pending) void pollUntilFresh()
      return true
    } catch {
      error.value = 'Your settings were not saved. Check your connection and try again.'
      return false
    } finally {
      saving.value = false
    }
  }

  async function pollUntilFresh(intervalMs = POLL_MS) {
    for (let i = 0; i < POLL_MAX && recalculating.value; i++) {
      await new Promise((r) => setTimeout(r, intervalMs))
      try {
        const { data } = await api.GET('/api/v1/profile')
        if (data) apply(data)
      } catch {
        /* keep waiting; the next tick retries */
      }
    }
    recalculating.value = false
  }

  function reset() {
    profile.value = null
    recalculating.value = false
  }

  return { profile, loading, saving, error, recalculating, units, homeTz, resolved, load, save, pollUntilFresh, reset }
})
