<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import Icons from './Icons.vue'
import { NAV_ITEMS, isActive, useNavWorkoutType } from './nav'
import { useLens } from '@/lib/useLens'
import { vPress } from '@/directives/press'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const navType = useNavWorkoutType()
const router = useRouter()
const auth = useAuthStore()
const list = ref<HTMLElement | null>(null)
const { style: lens } = useLens(list, '.item.active', () => `${route.path}|${navType.value}`)

async function signOut() {
  await auth.logout()
  void router.push({ name: 'login' })
}
</script>

<template>
  <aside class="side glass glass--lg glass--refract" aria-label="Strydr">
    <RouterLink to="/" class="brand" aria-label="Strydr, dashboard">
      <svg class="mark" viewBox="0 0 64 64" aria-hidden="true"><path d="M14 50C14 38 24 36 32 32C40 28 50 26 50 14" fill="none" stroke="var(--accent)" stroke-width="9" stroke-linecap="round" /></svg>
      <span class="word">Strydr</span>
    </RouterLink>

    <nav ref="list" class="list" aria-label="Main">
      <span class="lens" :style="lens" aria-hidden="true" />
      <RouterLink
        v-for="t in NAV_ITEMS"
        :key="t.to"
        v-press
        :to="t.to"
        class="item"
        :class="{ active: isActive(t.to, route.path, navType) }"
        :aria-current="isActive(t.to, route.path, navType) ? 'page' : undefined"
      >
        <Icons :name="t.icon" :size="20" />
        <span>{{ t.label }}</span>
      </RouterLink>
    </nav>

    <div class="foot">
      <p class="note">Your data stays on this server.</p>
      <button v-press type="button" class="item out" @click="signOut">
        <Icons name="profile" :size="20" />
        <span>Sign out</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.side {
  position: fixed; z-index: 10;
  top: var(--space-4); bottom: var(--space-4); left: var(--space-4);
  width: var(--sidebar-w);
  display: none; flex-direction: column; gap: var(--space-6);
  padding: var(--space-5) var(--space-3);
}
@media (min-width: 1080px) { .side { display: flex; } }
.brand { display: flex; align-items: center; gap: var(--space-2); padding: 0 var(--space-3); text-decoration: none; color: var(--ink); }
.mark { width: 30px; height: 30px; transition: transform var(--dur-morph) var(--ease-glass); }
.brand:hover .mark { transform: rotate(-8deg) scale(1.06); }
.word { font-family: var(--font-display); font-weight: 700; font-size: 24px; letter-spacing: -.02em; }
.list { position: relative; display: flex; flex-direction: column; gap: 4px; }
.lens {
  position: absolute; top: 0; left: 0; border-radius: var(--radius-full); pointer-events: none;
  background:
    radial-gradient(30% 80% at 14% 12%, var(--glass-specular) 0%, transparent 70%),
    color-mix(in srgb, var(--accent) 14%, transparent);
  box-shadow: inset 0 1px 0 var(--glass-specular), inset 0 -1px 0 var(--glass-lens-dark);
  transition: transform var(--dur-morph) var(--ease-glass), height var(--dur-morph) var(--ease-glass), opacity .2s ease;
}
.item {
  position: relative; overflow: hidden;
  display: flex; align-items: center; gap: var(--space-3);
  height: 44px; padding: 0 var(--space-4); border-radius: var(--radius-full);
  color: var(--ink-secondary); text-decoration: none; font-weight: 600; font-size: 15px;
  background: none; border: 0; font-family: inherit; width: 100%; cursor: pointer;
  transition: color var(--dur-release) var(--ease-settle), transform var(--dur-release) var(--ease-glass);
}
.item > * { position: relative; z-index: 1; }
.item:hover { color: var(--ink); }
.item.active { color: var(--accent-text); }
.item:active { transform: scale(.96); }
.foot { margin-top: auto; display: flex; flex-direction: column; gap: var(--space-2); }
.note { margin: 0; padding: 0 var(--space-4); font-size: 12px; color: var(--ink-secondary); }
</style>
