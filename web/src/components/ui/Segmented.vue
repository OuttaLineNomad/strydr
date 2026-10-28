<script setup lang="ts" generic="T extends string | number | null">
import { computed, ref } from 'vue'
import { useLens } from '@/lib/useLens'
import { vPress } from '@/directives/press'

// A glass segmented control. The selected segment is a lens that glides
// between options on the bouncy glass curve.
const props = defineProps<{
  options: { label: string; value: T; testid?: string }[]
  modelValue: T
  label: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: T] }>()

const track = ref<HTMLElement | null>(null)
const { style } = useLens(track, '[aria-pressed="true"]', () => props.modelValue)
const sel = computed(() => props.modelValue)
</script>

<template>
  <div ref="track" class="seg glass glass--sm" role="group" :aria-label="label">
    <span class="lens" :style="style" aria-hidden="true" />
    <button
      v-for="o in options"
      :key="String(o.value)"
      v-press
      type="button"
      class="seg-btn"
      :class="{ on: sel === o.value }"
      :aria-pressed="sel === o.value"
      :data-testid="o.testid"
      @click="emit('update:modelValue', o.value)"
    >{{ o.label }}</button>
  </div>
</template>

<style scoped>
.seg { display: inline-flex; position: relative; padding: 4px; gap: 2px; border-radius: var(--radius-full); max-width: 100%; overflow-x: auto; scrollbar-width: none; }
.lens {
  position: absolute; top: 0; left: 0; border-radius: var(--radius-full); pointer-events: none; z-index: 0;
  background:
    radial-gradient(40% 70% at 20% 15%, var(--glass-specular) 0%, transparent 70%),
    color-mix(in srgb, var(--accent) 16%, var(--surface-2));
  box-shadow: var(--shadow-glass);
  transition: transform var(--dur-morph) var(--ease-glass), width var(--dur-morph) var(--ease-glass), opacity .2s ease;
}
.seg-btn {
  position: relative; z-index: 1; flex-shrink: 0; overflow: hidden;
  height: 36px; padding: 0 var(--space-4); border: 0; border-radius: var(--radius-full); background: transparent;
  color: var(--ink-secondary); font: inherit; font-size: var(--body-sm-size); font-weight: 600; cursor: pointer; white-space: nowrap;
  transition: color var(--dur-release) var(--ease-settle), transform var(--dur-release) var(--ease-glass);
}
.seg-btn:hover { color: var(--ink); }
.seg-btn.on { color: var(--accent-text); }
.seg-btn:active { transform: scale(.94); }
.seg-btn:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
</style>
