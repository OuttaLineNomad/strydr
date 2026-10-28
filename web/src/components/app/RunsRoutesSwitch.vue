<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useLens } from '@/lib/useLens'

const props = defineProps<{ current: 'runs' | 'routes' }>()
const track = ref<HTMLElement | null>(null)
const { style } = useLens(track, '.on', () => props.current)
</script>

<template>
  <nav ref="track" class="seg glass glass--sm" aria-label="Runs or routes">
    <span class="lens" :style="style" aria-hidden="true" />
    <RouterLink :to="{ name: 'runs' }" class="seg-btn" :class="{ on: current === 'runs' }" :aria-current="current === 'runs' ? 'page' : undefined" data-testid="seg-runs">Runs</RouterLink>
    <RouterLink :to="{ name: 'routes' }" class="seg-btn" :class="{ on: current === 'routes' }" :aria-current="current === 'routes' ? 'page' : undefined" data-testid="seg-routes">Routes</RouterLink>
  </nav>
</template>

<style scoped>
.seg { display: inline-flex; position: relative; align-self: flex-start; padding: 4px; gap: 2px; border-radius: var(--radius-full); }
.lens {
  position: absolute; top: 0; left: 0; border-radius: var(--radius-full); pointer-events: none;
  background: radial-gradient(40% 70% at 20% 15%, var(--glass-specular) 0%, transparent 70%), color-mix(in srgb, var(--accent) 16%, var(--surface-2));
  box-shadow: var(--shadow-glass);
  transition: transform var(--dur-morph) var(--ease-glass), width var(--dur-morph) var(--ease-glass), opacity .2s ease;
}
.seg-btn { position: relative; z-index: 1; min-width: 84px; height: 36px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-full); text-decoration: none; color: var(--ink-secondary); font-weight: 600; font-size: var(--body-sm-size); transition: color var(--dur-release) var(--ease-settle), transform var(--dur-release) var(--ease-glass); }
.seg-btn:hover { color: var(--ink); }
.seg-btn.on { color: var(--accent-text); }
.seg-btn:active { transform: scale(.94); }
.seg-btn:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
</style>
