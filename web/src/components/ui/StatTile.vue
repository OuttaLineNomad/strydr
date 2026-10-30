<script setup lang="ts">
import { computed, toRef } from 'vue'
import GlassPanel from './GlassPanel.vue'
import Icons from './Icons.vue'
import { useCountUp } from '@/lib/countUp'

export interface Trend {
  /** 'flat' is a zero change or no prior period: a neutral pill with no arrow. */
  direction: 'up' | 'down' | 'flat'
  /** Comparison text including its period, e.g. "+0.8 mi vs last week". Required: no trend without a comparison. */
  text: string
  /** Whether the change is good for this metric (not whether the number rose). Ignored when flat. */
  good: boolean
}

const props = defineProps<{
  label: string
  /** Pre-formatted value; null renders "not available". */
  value: string | null
  unit?: string
  hero?: boolean
  trend?: Trend
  /** A short line under the figure: a date, a source. */
  sub?: string | null
}>()

const shown = useCountUp(toRef(props, 'value'))
const pillClass = computed(() => {
  const t = props.trend
  if (!t) return ''
  return t.direction === 'flat' ? 'pill--neutral' : t.good ? 'pill--success' : 'pill--danger'
})
</script>

<template>
  <GlassPanel class="tile" :class="{ 'tile--hero': hero }">
    <span class="tile-label">{{ label }}</span>
    <div class="value-row">
      <template v-if="value !== null">
        <span class="num" :class="hero ? 'num--hero' : 'num--sm'" :aria-label="value" data-testid="stat-value">{{ shown }}</span>
        <span v-if="unit" class="unit" data-testid="stat-unit">{{ unit }}</span>
      </template>
      <span v-else class="na" data-testid="stat-value">not available</span>
    </div>
    <span v-if="trend" class="pill" :class="pillClass" data-testid="stat-trend">
      <Icons v-if="trend.direction !== 'flat'" :name="trend.direction === 'up' ? 'arrow-up' : 'arrow-down'" :size="12" />
      {{ trend.text }}
    </span>
    <span v-if="sub" class="sub">{{ sub }}</span>
  </GlassPanel>
</template>

<style scoped>
.tile { padding: var(--space-4) var(--space-5); display: flex; flex-direction: column; align-items: flex-start; gap: var(--space-2); min-width: 0; }
.tile--hero { padding: var(--space-5) var(--space-6); gap: var(--space-3); }
.tile-label { font-size: 13px; font-weight: 600; color: var(--ink-secondary); }
.value-row { display: flex; align-items: baseline; gap: var(--space-2); min-width: 0; }
.num { font-family: var(--font-display); font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.num--hero { font-size: var(--metric-hero-size); line-height: var(--metric-hero-leading); }
.num--sm { font-size: 28px; line-height: 32px; }
.unit { font-size: 14px; font-weight: 500; color: var(--ink-secondary); }
.tile--hero .unit { font-size: 17px; font-weight: 600; }
.na { font-size: var(--body-size); color: var(--ink-secondary); }
.sub { font-size: 12px; color: var(--ink-secondary); }
</style>
