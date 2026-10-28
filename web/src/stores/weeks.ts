import { ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { WeekDetail, WeekNote, WeekSummary } from '@/api/types'

export const useWeeksStore = defineStore('weeks', () => {
  const items = ref<WeekSummary[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const detail = shallowRef<WeekDetail | null>(null)
  const detailLoading = ref(false)
  const detailError = ref<string | null>(null)
  const noteBusy = ref(false)
  const noteError = ref<string | null>(null)

  async function loadList() {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.GET('/api/v1/weeks', { params: { query: {} } })
      if (!data) error.value = 'Your weeks could not load. Try again in a moment.'
      else items.value = [...data].sort((a, b) => b.week_start.localeCompare(a.week_start))
    } catch {
      error.value = 'Your weeks could not load. Check your connection and try again.'
    } finally {
      loading.value = false
    }
  }

  /** ISO week id (YYYY-Www) of a YYYY-MM-DD date. */
  function isoWeekId(date: string): string {
    const d = new Date(`${date}T00:00:00Z`)
    const day = d.getUTCDay() || 7
    d.setUTCDate(d.getUTCDate() + 4 - day)
    const year = d.getUTCFullYear()
    const week = Math.ceil(((d.getTime() - Date.UTC(year, 0, 1)) / 86_400_000 + 1) / 7)
    return `${year}-W${String(week).padStart(2, '0')}`
  }
  const addDays = (date: string, n: number) => new Date(Date.parse(`${date}T00:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10)

  /** Appends the 12 weeks before the oldest one shown. */
  async function loadEarlier() {
    const oldest = items.value[items.value.length - 1]
    if (!oldest) return
    loading.value = true
    error.value = null
    try {
      const { data } = await api.GET('/api/v1/weeks', {
        params: { query: { from: isoWeekId(addDays(oldest.week_start, -84)), to: isoWeekId(addDays(oldest.week_start, -7)) } },
      })
      if (!data) error.value = 'Earlier weeks could not load. Try again in a moment.'
      else items.value = [...items.value, ...[...data].sort((a, b) => b.week_start.localeCompare(a.week_start))]
    } catch {
      error.value = 'Earlier weeks could not load. Check your connection and try again.'
    } finally {
      loading.value = false
    }
  }

  async function loadDetail(id: string) {
    detailLoading.value = true
    detailError.value = null
    detail.value = null
    try {
      const { data, response } = await api.GET('/api/v1/weeks/{week_id}', { params: { path: { week_id: id } } })
      if (data) detail.value = data
      else detailError.value = response?.status === 404 ? 'That week does not exist.' : 'This week could not load. Try again in a moment.'
    } catch {
      detailError.value = 'This week could not load. Check your connection and try again.'
    } finally {
      detailLoading.value = false
    }
  }

  async function saveNote(id: string, text: string): Promise<WeekNote | null> {
    noteBusy.value = true
    noteError.value = null
    try {
      const { data } = await api.PUT('/api/v1/weeks/{week_id}/note', { params: { path: { week_id: id } }, body: { text } })
      if (!data) {
        noteError.value = 'Your note was not saved. Try again.'
        return null
      }
      if (detail.value) detail.value = { ...detail.value, note: data, has_note: true }
      return data
    } catch {
      noteError.value = 'Your note was not saved. Check your connection and try again.'
      return null
    } finally {
      noteBusy.value = false
    }
  }

  async function deleteNote(id: string): Promise<boolean> {
    noteBusy.value = true
    noteError.value = null
    try {
      const { response } = await api.DELETE('/api/v1/weeks/{week_id}/note', { params: { path: { week_id: id } } })
      if (!response.ok) {
        noteError.value = 'Your note was not deleted. Try again.'
        return false
      }
      if (detail.value) detail.value = { ...detail.value, note: null, has_note: false }
      return true
    } catch {
      noteError.value = 'Your note was not deleted. Check your connection and try again.'
      return false
    } finally {
      noteBusy.value = false
    }
  }

  return { items, loading, error, detail, detailLoading, detailError, noteBusy, noteError, loadList, loadEarlier, loadDetail, saveNote, deleteNote }
})
