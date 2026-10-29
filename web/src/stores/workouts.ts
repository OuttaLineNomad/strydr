import { ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { NoteOut, WorkoutShoeResult, WorkoutDetail, WorkoutOut, WorkoutType } from '@/api/types'

export const PAGE_SIZE = 20

export const useWorkoutsStore = defineStore('workouts', () => {
  const items = ref<WorkoutOut[]>([])
  const type = ref<WorkoutType | null>(null)
  const page = ref(0)
  const hasNext = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const detail = shallowRef<WorkoutDetail | null>(null)
  const detailLoading = ref(false)
  const detailError = ref<string | null>(null)
  const noteBusy = ref(false)
  const noteError = ref<string | null>(null)

  const shoeBusy = ref(false)
  const shoeError = ref<string | null>(null)

  async function setShoe(id: string, call: () => Promise<{ data?: WorkoutShoeResult; response: { ok: boolean } }>, fail: string): Promise<boolean> {
    shoeBusy.value = true
    shoeError.value = null
    try {
      const { data, response } = await call()
      if (!response.ok) {
        shoeError.value = fail
        return false
      }
      if (!data) {
        shoeError.value = fail
        return false
      }
      if (detail.value && detail.value.workout.workout_id === id) detail.value = { ...detail.value, shoe: data.shoe, shoe_chosen: data.chosen }
      return true
    } catch {
      shoeError.value = `${fail} Check your connection.`
      return false
    } finally {
      shoeBusy.value = false
    }
  }
  const saveShoe = (id: string, shoe_id: number | null) =>
    setShoe(id, () => api.PUT('/api/v1/workouts/{workout_id}/shoe', { params: { path: { workout_id: id } }, body: { shoe_id } }), 'The shoe was not saved. Try again.')
  const clearShoe = (id: string) =>
    setShoe(id, () => api.DELETE('/api/v1/workouts/{workout_id}/shoe', { params: { path: { workout_id: id } } }), 'The shoe was not reset. Try again.')

  async function loadList(opts: { type?: WorkoutType | null; page?: number } = {}) {
    if (opts.type !== undefined) type.value = opts.type
    if (opts.page !== undefined) page.value = opts.page
    loading.value = true
    error.value = null
    try {
      // Ask for one extra row to know whether another page exists.
      const { data } = await api.GET('/api/v1/workouts', {
        params: { query: { ...(type.value ? { type: type.value } : {}), limit: PAGE_SIZE + 1, offset: page.value * PAGE_SIZE } },
      })
      if (!data) {
        error.value = 'Your runs could not load. Try again in a moment.'
        return
      }
      hasNext.value = data.length > PAGE_SIZE
      items.value = data.slice(0, PAGE_SIZE)
    } catch {
      error.value = 'Your runs could not load. Check your connection and try again.'
    } finally {
      loading.value = false
    }
  }

  async function loadDetail(id: string) {
    detailLoading.value = true
    detailError.value = null
    shoeError.value = null
    detail.value = null
    try {
      const { data, response } = await api.GET('/api/v1/workouts/{workout_id}', { params: { path: { workout_id: id } } })
      // openapi-fetch widens the schema's coordinate tuples to number[]; the shape is otherwise identical.
      if (data) detail.value = data as WorkoutDetail
      else detailError.value = response.status === 404 ? 'You have no workout with that ID.' : 'This workout could not load. Try again in a moment.'
    } catch {
      detailError.value = 'This workout could not load. Check your connection and try again.'
    } finally {
      detailLoading.value = false
    }
  }

  async function saveNote(id: string, note: { text: string | null; rpe: number | null }): Promise<NoteOut | null> {
    noteBusy.value = true
    noteError.value = null
    try {
      const { data } = await api.PUT('/api/v1/workouts/{workout_id}/note', { params: { path: { workout_id: id } }, body: note })
      if (!data) {
        noteError.value = 'Your note was not saved. Try again.'
        return null
      }
      if (detail.value) detail.value = { ...detail.value, note: data }
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
      const { response } = await api.DELETE('/api/v1/workouts/{workout_id}/note', { params: { path: { workout_id: id } } })
      if (!response.ok) {
        noteError.value = 'Your note was not deleted. Try again.'
        return false
      }
      if (detail.value) detail.value = { ...detail.value, note: null }
      return true
    } catch {
      noteError.value = 'Your note was not deleted. Check your connection and try again.'
      return false
    } finally {
      noteBusy.value = false
    }
  }

  return { items, type, page, hasNext, loading, error, detail, detailLoading, detailError, noteBusy, noteError, shoeBusy, shoeError, saveShoe, clearShoe, loadList, loadDetail, saveNote, deleteNote }
})
