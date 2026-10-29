<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import Icons from './Icons.vue'
import { NAV_ITEMS, isActive, useNavWorkoutType, type TabItem } from './nav'
import { useLens } from '@/lib/useLens'
import { vPress } from '@/directives/press'

export type { TabItem }

withDefaults(defineProps<{ items?: TabItem[] }>(), { items: () => NAV_ITEMS })

const route = useRoute()
const navType = useNavWorkoutType()
const bar = ref<HTMLElement | null>(null)
const { style: lens } = useLens(bar, '.tab.active', () => `${route.path}|${navType.value}`)

// Scroll-responsive chrome: shrink to icons on scroll down, expand on scroll up.
const minimized = ref(false)
let lastY = 0
function onScroll() {
  const y = window.scrollY
  if (Math.abs(y - lastY) < 6) return
  minimized.value = y > lastY && y > 80
  lastY = y
}
onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <nav ref="bar" class="bar glass glass--sm glass--refract" :class="{ minimized }" aria-label="Main">
    <span class="lens" :style="lens" aria-hidden="true" />
    <RouterLink v-for="t in items" :key="t.to" v-press :to="t.to" class="tab" :class="{ active: isActive(t.to, route.path, navType) }" :aria-current="isActive(t.to, route.path, navType) ? 'page' : undefined" :aria-label="t.label">
      <Icons :name="t.icon" :size="22" />
      <span class="tab-label">{{ t.shortLabel ?? t.label }}</span>
    </RouterLink>
  </nav>
</template>

<style scoped>
.bar {
  position: fixed;
  left: 50%;
  bottom: calc(var(--space-4) + env(safe-area-inset-bottom, 0px));
  transform: translateX(-50%);
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 4px;
  height: 64px;
  padding: 0 6px;
  width: min(380px, calc(100% - 2 * var(--space-4)));
  border-radius: var(--radius-full);
  transition: height var(--dur-morph) var(--ease-settle), width var(--dur-morph) var(--ease-settle), transform var(--dur-release) var(--ease-glass);
}
.bar.minimized { height: 52px; width: min(248px, calc(100% - 2 * var(--space-4))); }
.lens {
  position: absolute; top: 0; left: 0; border-radius: var(--radius-full); pointer-events: none;
  background:
    radial-gradient(40% 60% at 22% 14%, var(--glass-specular) 0%, transparent 70%),
    color-mix(in srgb, var(--accent) 14%, transparent);
  box-shadow: inset 0 1px 0 var(--glass-specular), inset 0 -1px 0 var(--glass-lens-dark);
  transition: transform var(--dur-morph) var(--ease-glass), width var(--dur-morph) var(--ease-glass), height var(--dur-morph) var(--ease-settle), opacity .2s ease;
}
.tab {
  position: relative; flex: 1; overflow: hidden;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 3px; height: calc(100% - 10px); border-radius: var(--radius-full);
  color: var(--ink-secondary); text-decoration: none;
  transition: color var(--dur-release) var(--ease-settle), transform var(--dur-release) var(--ease-glass);
}
.tab > * { position: relative; z-index: 1; }
.tab.active { color: var(--accent-text); }
.tab:active { transform: scale(.92); }
.tab-label { font-size: 10px; font-weight: 600; letter-spacing: 0.2px; transition: opacity .2s ease, max-height var(--dur-morph) var(--ease-settle); max-height: 14px; }
.minimized .tab-label { opacity: 0; max-height: 0; }
@media (max-width: 400px) {
  /* six tabs at 320px: tighter bar, no gaps, smaller labels */
  .bar { width: calc(100% - var(--space-4)); gap: 0; padding: 0 4px; }
  .tab { min-width: 0; }
  .tab-label { font-size: 9px; letter-spacing: 0; }
}
/* below 360px six labels cannot fit: icons only (each link keeps its aria-label) */
@media (max-width: 359px) { .tab-label { display: none; } }
@media (min-width: 1080px) { .bar { display: none; } }
</style>
