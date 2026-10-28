import './styles/tokens.css'
import './styles/ui.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { api } from './api'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// A 401 anywhere else means the session ended: go to sign in.
api.use({
  onResponse({ response }) {
    if (response.status === 401 && !response.url.includes('/auth/login')) {
      const auth = useAuthStore(pinia)
      if (auth.signedIn !== false) {
        auth.markSignedOut()
        void router.push({ name: 'login' })
      }
    }
    return undefined
  },
})

app.mount('#app')
