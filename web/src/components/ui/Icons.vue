<script lang="ts">
// Glyph markup is static, hand-authored in this file (design-system/components/Icons/README.md).
// 24x24 viewBox, 1.8px stroke, round caps/joins, no fill (except the speed pivot dot).
// runs, weeks, settings, chevron, check, warning, arrow-up, arrow-down are additions in the same language,
// because the app's four destinations (Dashboard, Runs, Weeks, Settings) are not the design system's four.
export const GLYPHS = {
  dashboard: '<line x1="6" y1="18" x2="6" y2="13"/><line x1="12" y1="18" x2="12" y2="7"/><line x1="18" y1="18" x2="18" y2="4"/>',
  routes: '<path d="M9 3 4 5v16l5-2 6 2 5-2V3l-5 2-6-2Z"/><path d="M9 3v16M15 5v16"/>',
  coach: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8A2.5 2.5 0 0 1 17.5 16H9l-4 4v-4H6.5A2.5 2.5 0 0 1 4 13.5v-8Z"/>',
  profile: '<circle cx="12" cy="8" r="3.4"/><path d="M5 20c0-3.9 3.1-6 7-6s7 2.1 7 6"/>',
  sync: '<path d="M20 11a8 8 0 0 0-14.9-3.5M4 13a8 8 0 0 0 14.9 3.5"/><path d="M20 4v4h-4M4 20v-4h4"/>',
  share: '<path d="M12 15V4M8 8l4-4 4 4"/><path d="M5 13v5.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V13"/>',
  pr: '<path d="M8 4h8v3a4 4 0 0 1-8 0V4Z"/><path d="M8 5H5.5A1.2 1.2 0 0 0 4.3 6.2 3 3 0 0 0 7 9M16 5h2.5a1.2 1.2 0 0 1 1.2 1.2A3 3 0 0 1 17 9"/><path d="M12 11v3"/><path d="M9 20h6"/><path d="M10.2 20v-1.5a1.8 1.8 0 0 1 3.6 0V20"/>',
  pace: '<circle cx="12" cy="13" r="7.5"/><path d="M12 9v4l3 2"/><path d="M9.5 2.5h5M12 2.5V5"/>',
  'heart-rate': '<path d="M12 19.5s-7.5-4.6-9.3-9.4C1.6 6.9 3.4 4 6.5 4c2 0 3.4 1.2 4 2.3.6-1.1 2-2.3 4-2.3 3.1 0 4.9 2.9 3.8 6.1C19.5 14.9 12 19.5 12 19.5Z"/>',
  elevation: '<path d="M3 18 9 8l4 6 2-3 6 7H3Z"/>',
  cadence: '<ellipse cx="9" cy="7" rx="2.3" ry="3.2" transform="rotate(-15 9 7)"/><ellipse cx="15" cy="17" rx="2.3" ry="3.2" transform="rotate(15 15 17)"/>',
  power: '<path d="M13 3 5 14h5l-1 7 8-11h-5l1-7Z"/>',
  speed: '<path d="M4 16a8 8 0 0 1 16 0"/><path d="M12 16 16 9"/><circle cx="12" cy="16" r="1.3" fill="currentColor" stroke="none"/>',
  // additions
  runs: '<path d="M4 7h16M4 12h16M4 17h10"/>',
  weeks: '<rect x="4" y="5" width="16" height="15" rx="3"/><path d="M4 10h16M9 3v4M15 3v4"/>',
  settings: '<path d="M4 8h9M17 8h3M4 16h3M11 16h9"/><circle cx="15" cy="8" r="2.2"/><circle cx="9" cy="16" r="2.2"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  warning: '<path d="M12 4 3 19.5h18L12 4Z"/><path d="M12 10v4.5M12 17.5v.2"/>',
  'arrow-up': '<path d="M6 15l6-6 6 6"/>',
  'arrow-down': '<path d="M6 9l6 6 6-6"/>',
  'thumb-up': '<path d="M8 11v9H4.5a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1H8Z"/><path d="M8 11l3.5-7a2 2 0 0 1 2 2.2L13 9h5.6a1.6 1.6 0 0 1 1.6 1.9l-1.2 6.4A2.5 2.5 0 0 1 16.600 19.300L8 20"/>',
  'thumb-down': '<path d="M8 13V4H4.500a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1H8Z"/><path d="M8 13l3.500 7a2 2 0 0 0 2-2.200L13 15h5.600a1.600 1.600 0 0 0 1.600-1.900l-1.200-6.400A2.500 2.500 0 0 0 16.600 4.700L8 4"/>',
  star: '<path d="M12 3.500l2.600 5.400 5.900.8-4.300 4.100 1 5.800L12 16.800 6.800 19.600l1-5.800L3.500 9.700l5.900-.8L12 3.500Z"/>',
  eye: '<path d="M2.500 12S6 5.500 12 5.500 21.500 12 21.500 12 18 18.500 12 18.500 2.500 12 2.500 12Z"/><circle cx="12" cy="12" r="2.800"/>',
  minus: '<path d="M5 12h14"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M9 7V4.500h6V7M6.500 7l1 13h9l1-13"/>',
  sparkle: '<path d="M12 3l1.800 5.200L19 10l-5.200 1.800L12 17l-1.800-5.200L5 10l5.200-1.800L12 3Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.300 5.300l1.400 1.400M17.300 17.300l1.400 1.400M5.300 18.700l1.400-1.400M17.300 6.700l1.400-1.400"/>',
  moon: '<path d="M19.500 14.500A8 8 0 0 1 9.500 4.500a8 8 0 1 0 10 10Z"/>',
  calendar: '<rect x="4" y="5" width="16" height="15" rx="3"/><path d="M4 10h16M9 3v4M15 3v4"/><path d="M8.500 14h.01M12 14h.01M15.500 14h.01M8.500 17h.01M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="8.500"/><path d="M12 11v5M12 7.800v.2"/>',
} as const

export type IconName = keyof typeof GLYPHS
</script>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ name: IconName; size?: number; label?: string }>(), { size: 24 })
const markup = computed(() => GLYPHS[props.name])
const strokeWidth = computed(() => (props.name === 'dashboard' ? 2.4 : 1.8))
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -->
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    :width="size"
    :height="size"
    :role="label ? 'img' : undefined"
    :aria-label="label"
    :aria-hidden="label ? undefined : 'true'"
    focusable="false"
    v-html="markup"
  />
</template>
