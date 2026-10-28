<script setup lang="ts">
import { toRef } from 'vue'
import { useCountUp } from '@/lib/countUp'

const props = defineProps<{ label: string; value: string | null; unit?: string }>()
const shown = useCountUp(toRef(props, 'value'))
</script>

<template>
  <div class="hs">
    <dt class="hs-label">{{ label }}</dt>
    <dd class="hs-value">
      <template v-if="value !== null">
        <span class="hs-num" :aria-label="value" data-testid="stat-value">{{ shown }}</span>
        <span v-if="unit" class="hs-unit">{{ unit }}</span>
      </template>
      <span v-else class="hs-na" data-testid="stat-value">not available</span>
    </dd>
  </div>
</template>

<style scoped>
.hs { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.hs-label { font-size: 15px; font-weight: 500; color: rgba(255, 255, 255, 0.86); }
.hs-value { margin: 0; display: flex; align-items: baseline; gap: 6px; white-space: nowrap; }
.hs-num { font-family: var(--font-display); font-weight: 700; font-size: 38px; line-height: 42px; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; color: #fff; }
.hs-unit { font-size: 18px; font-weight: 600; color: rgba(255, 255, 255, 0.86); }
.hs-na { font-size: 17px; color: rgba(255, 255, 255, 0.86); line-height: 42px; }
@media (min-width: 1080px) { .hs-num { font-size: 52px; line-height: 56px; } .hs-na { line-height: 56px; } }
</style>
