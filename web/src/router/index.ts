import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
    { path: '/runs', name: 'runs', component: () => import('@/views/RunsView.vue') },
    { path: '/runs/routes', name: 'routes', component: () => import('@/views/RoutesView.vue') },
    { path: '/runs/routes/:routeKey', name: 'route-detail', component: () => import('@/views/RouteDetailView.vue'), props: true },
    { path: '/runs/:id', name: 'run-detail', component: () => import('@/views/RunDetailView.vue'), props: true },
    { path: '/weeks', name: 'weeks', component: () => import('@/views/WeeksView.vue') },
    { path: '/calendar', name: 'calendar', component: () => import('@/views/CalendarView.vue') },
    { path: '/weeks/:id', name: 'week-detail', component: () => import('@/views/WeekDetailView.vue'), props: true },
    { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { bare: true, public: true } },
  ],
})

// Auth guard: everything except /login needs a session cookie the API accepts.
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (auth.signedIn === null) await auth.check()
  if (to.meta.public) {
    return auth.signedIn && to.name === 'login' ? { name: 'dashboard' } : true
  }
  if (!auth.signedIn) return { name: 'login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } }
  return true
})

export default router
