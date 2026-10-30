import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { ShoeDefault, ShoeOut, ShoesOut } from '@/api/types'

/** The shoe list with totals and the default shoe (Settings). Per-run choices live in the workouts store. */
export const useShoesStore = defineStore('shoes', () => {
  const shoes = ref<ShoeOut[]>([])
  const current = ref<ShoeDefault | null>(null)
  const history = ref<ShoeDefault[]>([])
  const error = ref<string | null>(null)
  const busy = ref(false)

  function apply(d: ShoesOut) {
    shoes.value = d.shoes
    current.value = d.default ?? null
    history.value = d.history
  }

  async function load() {
    error.value = null
    try {
      const { data } = await api.GET('/api/v1/shoes')
      if (data) apply(data)
      else error.value = 'Your shoes could not load.'
    } catch {
      error.value = 'Your shoes could not load. Check your connection.'
    }
  }

  /** Runs one write; on failure keeps the list as it was and shows `fail`. */
  async function write(
    call: () => Promise<{ data?: ShoesOut; error?: unknown; response?: { status: number } }>,
    fail: string | ((status?: number) => string),
  ): Promise<boolean> {
    const msg = (status?: number) => (typeof fail === 'string' ? fail : fail(status))
    busy.value = true
    error.value = null
    try {
      const { data, response } = await call()
      if (!data) {
        error.value = msg(response?.status)
        if (response?.status === 404 && typeof fail !== 'string') {
          await load() // the row is gone: refresh the list, then keep the message
          error.value = msg(404)
        }
        return false
      }
      apply(data)
      return true
    } catch {
      error.value = `${msg()} Check your connection.`
      return false
    } finally {
      busy.value = false
    }
  }

  const add = (name: string) =>
    write(() => api.POST('/api/v1/shoes', { body: { name } }), 'The shoe was not added. Use a name no other shoe has.')
  const rename = (id: number, name: string) =>
    write(() => api.PATCH('/api/v1/shoes/{shoe_id}', { params: { path: { shoe_id: id } }, body: { name } }), 'The shoe was not renamed. Use a name no other shoe has.')
  const setRetired = (id: number, retired: boolean) =>
    write(() => api.PATCH('/api/v1/shoes/{shoe_id}', { params: { path: { shoe_id: id } }, body: { retired } }), 'The shoe was not updated. Try again.')
  const setDefault = (shoe_id: number | null, from_date: string) =>
    write(() => api.PUT('/api/v1/shoes/default', { body: { shoe_id, from_date } }), 'The default was not saved. Try again.')
  function defaultFail(verb: string, status?: number): string {
    if (status === 409) return 'The change was not saved. Another change is already on that date.'
    if (status === 422) return 'The change was not saved. Pick another shoe.'
    if (status === 404) return 'That change is already gone. The list is refreshed.'
    return `The change was not ${verb}. Try again.`
  }
  const editDefault = (fromDate: string, body: { shoe_id: number | null; from_date: string }) =>
    write(() => api.PUT('/api/v1/shoes/default/{from_date}', { params: { path: { from_date: fromDate } }, body }), (st) => defaultFail('saved', st))
  const deleteDefault = (fromDate: string) =>
    write(() => api.DELETE('/api/v1/shoes/default/{from_date}', { params: { path: { from_date: fromDate } } }), (st) => defaultFail('deleted', st))

  return { shoes, current, history, error, busy, load, add, rename, setRetired, setDefault, editDefault, deleteDefault }
})
