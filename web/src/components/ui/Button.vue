<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from 'vue-router'

withDefaults(
  defineProps<{
    variant?: 'primary' | 'glass' | 'secondary'
    small?: boolean
    icon?: boolean
    type?: 'button' | 'submit'
    disabled?: boolean
    /** Renders a link styled as a button. */
    to?: RouteLocationRaw
    /** Required when the button is icon-only. */
    label?: string
  }>(),
  { variant: 'glass', type: 'button' },
)
</script>

<template>
  <RouterLink v-if="to" :to="to" class="btn" :class="[`btn-${variant}`, { 'btn-sm': small, 'btn-icon': icon }]" :aria-label="icon ? label : undefined" style="text-decoration: none">
    <slot />
  </RouterLink>
  <button
    v-else
    :type="type"
    class="btn"
    :class="[`btn-${variant}`, { 'btn-sm': small, 'btn-icon': icon }]"
    :disabled="disabled"
    :aria-label="icon ? label : undefined"
  >
    <slot />
  </button>
</template>
