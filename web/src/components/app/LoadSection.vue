<script setup lang="ts">
import { computed, onMounted } from 'vue'
import LineChart from '@/components/ui/LineChart.vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Icons from '@/components/ui/Icons.vue'
import TrainingStateChip from './TrainingStateChip.vue'
import Segmented from '@/components/ui/Segmented.vue'
import { LOAD_RANGES, useLoadStore } from '@/stores/load'
import { formatShortDate, sampleIndices } from '@/lib/format'
import { NOT_AVAILABLE } from '@/lib/units'
import type { LoadDay } from '@/api/types'

const store = useLoadStore()
const rangeOptions = LOAD_RANGES.map((r) => ({ label: `${r}d`, value: r as number, testid: `load-range-${r}` }))
const pickRange = (r: number) => store.load(r as (typeof LOAD_RANGES)[number])
onMounted(() => store.load())

const MAX_POINTS = 60
const series = computed(() => store.data?.series ?? [])
const idx = computed(() => sampleIndices(series.value.length, MAX_POINTS))
function pick<T>(f: (d: LoadDay) => T): T[] {
  return idx.value.map((i) => f(series.value[i]!))
}

const labels = computed(() => pick((d) => formatShortDate(d.local_date)))
const round = (v: number) => String(Math.round(v))
const warmup = computed(() => series.value.some((d) => d.warmup))

// ACWR and ramp live in the tooltip and the table twin only (FR-24c). No colour, no wording around them.
const extras = computed(() => [
  { label: 'Day load', values: pick((d) => `${round(d.load)}${d.estimated ? ' (estimated)' : ''}`) },
  { label: 'ACWR', values: pick((d) => (d.tooltip.acwr == null ? NOT_AVAILABLE : d.tooltip.acwr.toFixed(2))) },
  { label: 'Ramp', values: pick((d) => (d.tooltip.ramp_pct == null ? NOT_AVAILABLE : `${d.tooltip.ramp_pct > 0 ? '+' : ''}${d.tooltip.ramp_pct.toFixed(0)}%`)) },
])
</script>

<template>
  <section class="load canvas" aria-labelledby="load-h" data-testid="load-section">
    <h2 id="load-h" class="section-title">Training load</h2>

    <p v-if="store.error" class="err" role="alert" data-testid="load-error">{{ store.error }}</p>
    <template v-else-if="series.length">
      <LineChart
        class="s8"
        title="Fitness, fatigue and form"
        caption="Training load units per day. Form is fitness minus fatigue. Hover or open the table for ACWR and ramp."
        first-column="Day"
        :labels="labels"
        :label-every="Math.max(1, Math.ceil(labels.length / 6))"
        :series="[
          { label: 'Fitness', role: 'emphasis', color: 'chart-elevation', icon: 'elevation', values: pick((d) => d.fitness) },
          { label: 'Fatigue', role: 'emphasis', color: 'chart-pace', icon: 'pace', values: pick((d) => d.fatigue) },
          { label: 'Form', role: 'emphasis', color: 'chart-power', icon: 'power', values: pick((d) => d.form) },
        ]"
        :format="round"
        :extras="extras"
      >
        <template #controls>
          <Segmented :model-value="store.days" :options="rangeOptions" label="Load range" @update:model-value="pickRange" />
        </template>
      </LineChart>
      <div class="s4 side">
        <GlassPanel class="state-card">
          <h3 class="chart-title">Training state</h3>
          <TrainingStateChip :state="store.data?.training_state?.state ?? null" :since="store.data?.training_state?.since" />
        </GlassPanel>
        <GlassPanel v-if="warmup" class="warm" role="note" data-testid="load-warmup">
          <Icons name="info" :size="16" />
          <span>Your first 42 days are a warm-up. Fitness and fatigue settle as more days of training come in, so read these lines loosely until then.</span>
        </GlassPanel>
      </div>
    </template>
    <GlassPanel v-else-if="!store.loading" class="warm"><span>Your training load appears once your first workouts sync.</span></GlassPanel>
  </section>
</template>

<style scoped>
.load { margin: 0; }
.side { display: flex; flex-direction: column; gap: var(--space-4); }
.state-card { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.state-card h3 { margin: 0; }
.warm { padding: var(--space-4) var(--space-5); display: flex; gap: var(--space-2); align-items: flex-start; font-size: var(--body-sm-size); color: var(--ink-secondary); }
.err { margin: 0; color: var(--danger); }
</style>
