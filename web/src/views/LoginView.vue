<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')

async function submit() {
  if (await auth.login(username.value, password.value)) {
    const to = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/'
    await router.replace(to)
  }
}
</script>

<template>
  <GlassPanel weight="lg" class="panel">
    <picture>
      <source srcset="/brand/strydr-lockup-dark.svg" media="(prefers-color-scheme: dark)" />
      <img src="/brand/strydr-lockup.svg" alt="Strydr" height="40" />
    </picture>
    <h1 class="title">Sign in</h1>
    <p class="page-sub">Enter your details to see your runs.</p>
    <form class="stack" @submit.prevent="submit">
      <label class="field">
        <span class="row-meta">Username</span>
        <input v-model="username" type="text" autocomplete="username" required class="input" data-testid="login-username" />
      </label>
      <label class="field">
        <span class="row-meta">Password</span>
        <input v-model="password" type="password" autocomplete="current-password" required class="input" data-testid="login-password" />
      </label>
      <p v-if="auth.error" class="err" role="alert" data-testid="login-error">{{ auth.error }}</p>
      <Button variant="primary" type="submit" :disabled="auth.busy">{{ auth.busy ? 'Signing in…' : 'Sign in' }}</Button>
    </form>
  </GlassPanel>
</template>

<style scoped>
.panel { padding: var(--space-8) var(--space-6); display: flex; flex-direction: column; gap: var(--space-4); max-width: 420px; width: 100%; margin: 0 auto; }
.title { font-family: var(--font-display); font-size: var(--display-md-size); line-height: var(--display-md-leading); margin: 0; }
.field { display: flex; flex-direction: column; gap: var(--space-1); }
.input { height: 48px; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink); padding: 0 var(--space-4); font: inherit; }
.input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.err { margin: 0; color: var(--danger); font-size: var(--body-sm-size); }
</style>
