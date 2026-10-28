import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { AiSettings, AiSettingsIn, PrivacyZone, Thresholds } from '@/api/types'

/** Privacy zones, AI phrasing and threshold overrides (CAP-9, CAP-10, FR-23b). */
export const usePrefsStore = defineStore('prefs', () => {
  const zones = ref<PrivacyZone[]>([])
  const zonesError = ref<string | null>(null)
  const zonesBusy = ref(false)

  const ai = ref<AiSettings | null>(null)
  const aiError = ref<string | null>(null)
  const aiBusy = ref(false)

  const thresholds = ref<Thresholds | null>(null)
  const thresholdsError = ref<string | null>(null)
  const thresholdsBusy = ref(false)

  async function loadZones() {
    zonesError.value = null
    try {
      const { data } = await api.GET('/api/v1/privacy-zones')
      if (data) zones.value = data
      else zonesError.value = 'Your privacy zones could not load.'
    } catch {
      zonesError.value = 'Your privacy zones could not load. Check your connection.'
    }
  }
  async function addZone(lat: number, lon: number, radius_m: number): Promise<boolean> {
    zonesBusy.value = true
    zonesError.value = null
    try {
      const { data } = await api.POST('/api/v1/privacy-zones', { body: { lat, lon, radius_m } })
      if (!data) {
        zonesError.value = 'The zone was not added. Try again.'
        return false
      }
      zones.value = [...zones.value, data]
      return true
    } catch {
      zonesError.value = 'The zone was not added. Check your connection and try again.'
      return false
    } finally {
      zonesBusy.value = false
    }
  }
  async function deleteZone(id: number): Promise<boolean> {
    zonesBusy.value = true
    zonesError.value = null
    try {
      const { response } = await api.DELETE('/api/v1/privacy-zones/{zone_id}', { params: { path: { zone_id: id } } })
      if (!response.ok) {
        zonesError.value = 'The zone was not deleted. Try again.'
        return false
      }
      zones.value = zones.value.filter((z) => z.id !== id)
      return true
    } catch {
      zonesError.value = 'The zone was not deleted. Check your connection and try again.'
      return false
    } finally {
      zonesBusy.value = false
    }
  }

  async function loadAi() {
    aiError.value = null
    try {
      const { data } = await api.GET('/api/v1/settings/ai')
      if (data) ai.value = data
      else aiError.value = 'Your AI settings could not load.'
    } catch {
      aiError.value = 'Your AI settings could not load. Check your connection.'
    }
  }
  /** The key is write-only. It is sent once and never kept in page state. */
  async function saveAi(body: AiSettingsIn): Promise<boolean> {
    aiBusy.value = true
    aiError.value = null
    try {
      const { data } = await api.PUT('/api/v1/settings/ai', { body })
      if (!data) {
        aiError.value = 'Your AI settings were not saved. Check the values and try again.'
        return false
      }
      ai.value = data
      return true
    } catch {
      aiError.value = 'Your AI settings were not saved. Check your connection and try again.'
      return false
    } finally {
      aiBusy.value = false
    }
  }

  async function loadThresholds() {
    thresholdsError.value = null
    try {
      const { data } = await api.GET('/api/v1/settings/thresholds')
      if (data) thresholds.value = data
      else thresholdsError.value = 'Your thresholds could not load.'
    } catch {
      thresholdsError.value = 'Your thresholds could not load. Check your connection.'
    }
  }
  async function saveThresholds(overrides: Thresholds['overrides']): Promise<boolean> {
    thresholdsBusy.value = true
    thresholdsError.value = null
    try {
      const { data } = await api.PUT('/api/v1/settings/thresholds', { body: { overrides } })
      if (!data) {
        thresholdsError.value = 'Your thresholds were not saved. Check the values and try again.'
        return false
      }
      thresholds.value = data
      return true
    } catch {
      thresholdsError.value = 'Your thresholds were not saved. Check your connection and try again.'
      return false
    } finally {
      thresholdsBusy.value = false
    }
  }

  return {
    zones, zonesError, zonesBusy, loadZones, addZone, deleteZone,
    ai, aiError, aiBusy, loadAi, saveAi,
    thresholds, thresholdsError, thresholdsBusy, loadThresholds, saveThresholds,
  }
})
