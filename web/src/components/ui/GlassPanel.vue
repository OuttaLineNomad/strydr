<script setup lang="ts">
withDefaults(defineProps<{ weight?: 'sm' | 'md' | 'lg'; as?: string }>(), { weight: 'md', as: 'div' })
</script>

<template>
  <component :is="as" class="glass" :class="{ 'glass--sm': weight === 'sm', 'glass--lg': weight === 'lg' }">
    <slot />
  </component>
</template>
