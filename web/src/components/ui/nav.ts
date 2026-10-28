import type { IconName } from './Icons.vue'

export interface TabItem {
  label: string
  to: string
  icon: IconName
}

export const NAV_ITEMS: TabItem[] = [
  { label: 'Dashboard', to: '/', icon: 'dashboard' },
  { label: 'Runs', to: '/runs', icon: 'runs' },
  { label: 'Weeks', to: '/weeks', icon: 'weeks' },
  { label: 'Calendar', to: '/calendar', icon: 'calendar' },
  { label: 'Settings', to: '/settings', icon: 'settings' },
]

/** '/' is active only on the dashboard; the others own their sub-paths. */
export function isActive(to: string, path: string): boolean {
  return to === '/' ? path === '/' : path === to || path.startsWith(`${to}/`)
}
