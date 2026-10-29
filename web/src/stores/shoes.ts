import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { ShoeDefault, ShoeOut, ShoesOut } from '@/api/types'

/** The shoe list with totals and the default shoe (Settings). Per-run choices live in the workouts store. */
export const useShoesStore = defineStore('shoes', () => {
  const shoes = ref<ShoeOut[]>([])
  const current = ref<ShoeDefault | null>(null)
  const error = ref<string | null>(null)
  const busy = ref(false)

  function apply(d: ShoesOut) {
    shoes.value = d.shoes
    current.value = d.default ?? null
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
  async function write(call: () => Promise<{ data?: ShoesOut; error?: unknown }>, fail: string): Promise<boolean> {
    busy.value = true
    error.value = null
    try {
      const { data } = await call()
      if (!data) {
        error.value = fail
        return false
      }
      apply(data)
      return true
    } catch {
      error.value = `${fail} Check your connection.`
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

  return { shoes, current, error, busy, load, add, rename, setRetired, setDefault }
})
