import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api'
import { useSettingsStore } from './settings'

export const useAuthStore = defineStore('auth', () => {
  /** null until the first check has run. */
  const signedIn = ref<boolean | null>(null)
  const error = ref<string | null>(null)
  const busy = ref(false)

  async function check(): Promise<boolean> {
    const ok = await useSettingsStore().load()
    signedIn.value = ok
    return ok
  }

  async function login(username: string, password: string): Promise<boolean> {
    busy.value = true
    error.value = null
    try {
      const { response } = await api.POST('/api/v1/auth/login', { body: { username, password } })
      if (!response.ok) {
        error.value = response.status === 401 ? 'That username and password did not match.' : 'Sign in did not work. Try again in a moment.'
        return false
      }
      return await check()
    } catch {
      error.value = 'Sign in did not work. Check your connection and try again.'
      return false
    } finally {
      busy.value = false
    }
  }

  function markSignedOut() {
    signedIn.value = false
    useSettingsStore().reset()
  }

  async function logout() {
    try {
      await api.POST('/api/v1/auth/logout')
    } finally {
      markSignedOut()
    }
  }

  return { signedIn, error, busy, check, login, logout, markSignedOut }
})
