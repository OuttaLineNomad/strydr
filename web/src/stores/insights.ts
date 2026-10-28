import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import type { InsightDetail, InsightFeed, InsightOut, Thumb } from '@/api/types'

export interface InsightQuery {
  run?: string
  week?: string
  limit?: number
  offset?: number
}

export const useInsightsStore = defineStore('insights', () => {
  // Optimistic thumb overlay, keyed by insight_key. Wins over the value the feed returned.
  const thumbs = reactive<Record<string, Thumb | null>>({})
  const feedbackError = reactive<Record<string, string | null>>({})
  const details = reactive<Record<string, InsightDetail>>({})
  const detailError = reactive<Record<string, string | null>>({})

  function thumbOf(i: Pick<InsightOut, 'insight_key' | 'thumb'>): Thumb | null {
    return i.insight_key in thumbs ? thumbs[i.insight_key]! : i.thumb
  }

  /** Tapping the active thumb clears it. The UI updates first and rolls back if the call fails. */
  async function setThumb(i: Pick<InsightOut, 'insight_key' | 'thumb'>, pressed: Thumb): Promise<boolean> {
    const key = i.insight_key
    const prev = thumbOf(i)
    const next = prev === pressed ? null : pressed
    thumbs[key] = next
    feedbackError[key] = null
    try {
      let ok: boolean
      if (next === null) {
        const { response } = await api.DELETE('/api/v1/insights/{insight_key}/feedback', { params: { path: { insight_key: key } } })
        ok = response.ok
      } else {
        const { data } = await api.PUT('/api/v1/insights/{insight_key}/feedback', {
          params: { path: { insight_key: key } },
          body: { thumb: next },
        })
        ok = !!data
      }
      if (!ok) throw new Error('rejected')
      return true
    } catch {
      thumbs[key] = prev
      feedbackError[key] = 'Your feedback was not saved. Try again.'
      return false
    }
  }

  async function loadDetail(key: string): Promise<InsightDetail | null> {
    if (details[key]) return details[key]!
    detailError[key] = null
    try {
      const { data } = await api.GET('/api/v1/insights/{insight_key}', { params: { path: { insight_key: key } } })
      if (!data) {
        detailError[key] = 'The reasoning could not load. Try again in a moment.'
        return null
      }
      details[key] = data
      return data
    } catch {
      detailError[key] = 'The reasoning could not load. Check your connection and try again.'
      return null
    }
  }

  const feedBusy = ref(false)
  async function fetchFeed(q: InsightQuery = {}): Promise<InsightFeed | null> {
    feedBusy.value = true
    try {
      const { data } = await api.GET('/api/v1/insights', {
        params: { query: { ...(q.run ? { run: q.run } : {}), ...(q.week ? { week: q.week } : {}), limit: q.limit ?? 10, offset: q.offset ?? 0 } },
      })
      return data ?? null
    } catch {
      return null
    } finally {
      feedBusy.value = false
    }
  }

  return { thumbs, feedbackError, details, detailError, feedBusy, thumbOf, setThumb, loadDetail, fetchFeed }
})
