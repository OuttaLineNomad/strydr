import { ref } from 'vue'

export type HistoryPage = 'weeks' | 'calendar' | 'recap'
export const HISTORY_PATHS: Record<HistoryPage, string> = { weeks: '/weeks', calendar: '/calendar', recap: '/recap' }

const last = ref<Record<HistoryPage, string>>({ ...HISTORY_PATHS })
/** The most recent history page (path + query) the runner was on; the History tab opens it. */
export const lastHistory = ref(HISTORY_PATHS.weeks)

/** Remember a history route by its full path. Week details (/weeks/:id) and other pages are ignored. */
export function rememberHistoryRoute(fullPath: string) {
  const path = fullPath.split(/[?#]/)[0]
  const page = (Object.keys(HISTORY_PATHS) as HistoryPage[]).find((p) => HISTORY_PATHS[p] === path)
  if (!page) return
  last.value[page] = fullPath
  lastHistory.value = fullPath
}

export const historyRoute = (page: HistoryPage) => last.value[page]

export function resetHistoryNav() {
  last.value = { ...HISTORY_PATHS }
  lastHistory.value = HISTORY_PATHS.weeks
}
