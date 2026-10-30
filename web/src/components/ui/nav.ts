import { computed } from 'vue'
import { useRoute } from 'vue-router'
import type { IconName } from './Icons.vue'
import { useWorkoutsStore } from '@/stores/workouts'

export interface TabItem {
  label: string
  /** Shorter label for the phone tab bar. */
  shortLabel?: string
  to: string
  icon: IconName
  /** Path prefixes that light this item instead of `to` (the phone History tab covers three pages). */
  match?: string[]
}

export const NAV_ITEMS: TabItem[] = [
  { label: 'Dashboard', shortLabel: 'Home', to: '/', icon: 'dashboard' },
  { label: 'Runs', to: '/runs', icon: 'runs' },
  { label: 'Other activities', shortLabel: 'Activities', to: '/activities', icon: 'activities' },
  { label: 'Weeks', to: '/weeks', icon: 'weeks' },
  { label: 'Calendar', to: '/calendar', icon: 'calendar' },
  { label: 'Recap', to: '/recap', icon: 'recap' },
  { label: 'Settings', to: '/settings', icon: 'settings' },
]

/** The phone tab bar: five tabs. History opens Weeks and also owns Calendar and Recap. */
export const PHONE_NAV_ITEMS: TabItem[] = [
  { label: 'Dashboard', shortLabel: 'Home', to: '/', icon: 'dashboard' },
  { label: 'Runs', to: '/runs', icon: 'runs' },
  { label: 'Other activities', shortLabel: 'Activities', to: '/activities', icon: 'activities' },
  { label: 'History', to: '/weeks', icon: 'history', match: ['/weeks', '/calendar', '/recap'] },
  { label: 'Settings', to: '/settings', icon: 'settings' },
]

const WORKOUT_PAGE = /^\/runs\/(?!routes(?:\/|$))[^/]+$/

/**
 * '/' is active only on the dashboard; the others own their sub-paths.
 * A workout page lives at /runs/:id, so its tab follows the workout's type: walks and hikes belong to /activities.
 */
export function isActive(to: string, path: string, workoutType?: string | null, match?: string[]): boolean {
  if (match) return match.some((m) => path === m || path.startsWith(`${m}/`))
  if (WORKOUT_PAGE.test(path) && workoutType && (to === '/runs' || to === '/activities')) {
    return to === (workoutType === 'run' ? '/runs' : '/activities')
  }
  return to === '/' ? path === '/' : path === to || path.startsWith(`${to}/`)
}

/** The open workout's type while on a workout page: the loaded detail, else the list it was opened from. */
export function useNavWorkoutType() {
  const route = useRoute()
  const w = useWorkoutsStore()
  return computed(() => {
    const id = route?.params?.id
    if (w.detail && w.detail.workout.workout_id === id) return w.detail.workout.type
    return route?.query?.from === 'activities' ? 'walk' : null
  })
}
