import { ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import { useSettingsStore } from '@/stores/settings'
import type { NoteOut, WorkoutShoeResult, WorkoutDetail, WorkoutOut, WorkoutType } from '@/api/types'

export const PAGE_SIZE = 20

export const useWorkoutsStore = defineStore('workouts', () => {
  const items = ref<WorkoutOut[]>([])
  const type = ref<string | null>(null) // 'run', 'walk,hike', ...
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

  const typeBusy = ref(false)
  const typeError = ref<string | null>(null)
  const carryBusy = ref(false)
  const carryError = ref<string | null>(null)

  const updating = ref(false)
  // A type change queues a recompute; the long-run flag, zones and summary are stale until it finishes.
  async function refreshAfterRecompute(id: string) {
    updating.value = true
    try {
      const settings = useSettingsStore()
      await settings.load()
      if (settings.recalculating) await settings.pollUntilFresh()
      if (detail.value?.workout.workout_id === id) await loadDetail(id, true)
    } finally {
      updating.value = false
    }
  }

  async function setType(id: string, next: WorkoutType): Promise<boolean> {
    typeBusy.value = true
    typeError.value = null
    try {
      const { data, response } = await api.PUT('/api/v1/workouts/{workout_id}/type', { params: { path: { workout_id: id } }, body: { type: next } })
      if (!response.ok || !data) {
        typeError.value = 'The type was not changed. Try again.'
        return false
      }
      if (detail.value && detail.value.workout.workout_id === id) detail.value = { ...detail.value, workout: { ...detail.value.workout, type: data.type } }
      void refreshAfterRecompute(id)
      return true
    } catch {
      typeError.value = 'The type was not changed. Check your connection and try again.'
      return false
    } finally {
      typeBusy.value = false
    }
  }

  async function setCarry(id: string, kg: number | null): Promise<boolean> {
    carryBusy.value = true
    carryError.value = null
    const fail = kg == null ? 'The weight was not cleared.' : 'The weight was not saved.'
    try {
      const { data, response } = kg == null
        ? await api.DELETE('/api/v1/workouts/{workout_id}/carry', { params: { path: { workout_id: id } } })
        : await api.PUT('/api/v1/workouts/{workout_id}/carry', { params: { path: { workout_id: id } }, body: { weight_kg: kg } })
      if (!response.ok || !data) {
        carryError.value = `${fail} Try again.`
        return false
      }
      if (detail.value && detail.value.workout.workout_id === id)
        detail.value = { ...detail.value, carry_kg: data.carry_kg, workout: { ...detail.value.workout, carry_kg: data.carry_kg } }
      return true
    } catch {
      carryError.value = `${fail} Check your connection and try again.`
      return false
    } finally {
      carryBusy.value = false
    }
  }

  let listSeq = 0
  async function loadList(opts: { type?: string | null; page?: number } = {}) {
    if (opts.type !== undefined) {
      if (opts.type !== type.value) items.value = [] // never show another tab's cards while this one loads
      type.value = opts.type
    }
    const seq = ++listSeq
    if (opts.page !== undefined) page.value = opts.page
    loading.value = true
    error.value = null
    try {
      // Ask for one extra row to know whether another page exists.
      const { data } = await api.GET('/api/v1/workouts', {
        params: { query: { ...(type.value ? { type: type.value } : {}), limit: PAGE_SIZE + 1, offset: page.value * PAGE_SIZE } },
      })
      if (seq !== listSeq) return // a newer request owns the list
      if (!data) {
        error.value = 'Your runs could not load. Try again in a moment.'
        return
      }
      hasNext.value = data.length > PAGE_SIZE
      items.value = data.slice(0, PAGE_SIZE)
    } catch {
      if (seq === listSeq) error.value = 'Your runs could not load. Check your connection and try again.'
    } finally {
      if (seq === listSeq) loading.value = false
    }
  }

  async function loadDetail(id: string, quiet = false) {
    if (!quiet) {
      detailLoading.value = true
      detail.value = null
    }
    detailError.value = null
    shoeError.value = null
    typeError.value = null
    carryError.value = null
    try {
      const { data, response } = await api.GET('/api/v1/workouts/{workout_id}', { params: { path: { workout_id: id } } })
      // openapi-fetch widens the schema's coordinate tuples to number[]; the shape is otherwise identical.
      if (data) detail.value = data as WorkoutDetail
      else if (!quiet) detailError.value = response.status === 404 ? 'You have no workout with that ID.' : 'This workout could not load. Try again in a moment.'
    } catch {
      if (!quiet) detailError.value = 'This workout could not load. Check your connection and try again.'
    } finally {
      if (!quiet) detailLoading.value = false
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

  return { items, type, page, hasNext, loading, error, detail, detailLoading, detailError, noteBusy, noteError, shoeBusy, shoeError, typeBusy, typeError, updating, carryBusy, carryError, setType, setCarry, saveShoe, clearShoe, loadList, loadDetail, saveNote, deleteNote }
})
