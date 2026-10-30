<script setup lang="ts">
import { computed } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import type { Sleep } from '@/api/types'
import { formatHours, QUALITY_LABEL } from '@/lib/sleep'

// The night before this run, from Apple's sleep stages: how long, how it split into stages,
// how it compares with the runner's usual, and the next morning's resting HR and HRV.
const props = defineProps<{ sleep: Sleep | null }>()

const z = computed(() => props.sleep)
const stages = computed(() => {
  const x = z.value
  if (!x) return []
  const all = [
    { key: 'deep', label: 'Deep', h: x.deep_h },
    { key: 'core', label: 'Core', h: x.core_h },
    { key: 'rem', label: 'REM', h: x.rem_h },
    { key: 'awake', label: 'Awake', h: x.awake_h },
  ].filter((s): s is { key: string; label: string; h: number } => s.h != null && s.h > 0)
  const sum = all.reduce((a, s) => a + s.h, 0) || 1
  return all.map((s) => ({ ...s, pct: (s.h / sum) * 100 }))
})
const vsUsual = computed(() => {
  const d = z.value?.vs_usual_h
  if (d == null) return null
  if (Math.abs(d) < 0.25) return { text: 'About your usual', tone: 'neutral' }
  return { text: `${formatHours(Math.abs(d))} ${d < 0 ? 'under' : 'over'} your usual ${formatHours(z.value!.usual_h!)}`, tone: d < 0 ? 'low' : 'neutral' }
})
function delta(v: number | null | undefined, usual: number | null | undefined, unit: string, higherIsWorse: boolean) {
  if (v == null) return null
  const base = `${Math.round(v)} ${unit}`
  if (usual == null) return { value: base, note: null }
  const d = Math.round(v - usual)
  if (d === 0) return { value: base, note: 'your usual' }
  const worse = higherIsWorse ? d > 0 : d < 0
  return { value: base, note: `${d > 0 ? '+' : ''}${d} vs usual`, worse }
}
const rhr = computed(() => delta(z.value?.rhr_bpm, z.value?.rhr_usual_bpm, 'bpm', true))
const hrv = computed(() => delta(z.value?.hrv_ms, z.value?.hrv_usual_ms, 'ms', false))
</script>

<template>
  <GlassPanel class="sleep" role="group" aria-label="Sleep the night before" data-testid="sleep">
    <div class="head">
      <h3 class="chart-title">Sleep the night before</h3>
      <span v-if="z" class="pill" :class="z.quality === 'good' ? 'pill--success' : 'pill--neutral'" data-testid="sleep-quality">{{ QUALITY_LABEL[z.quality] }}</span>
    </div>

    <template v-if="z">
      <div class="total">
        <span class="big mono" data-testid="sleep-total">{{ formatHours(z.total_h) }}</span>
        <span v-if="z.bedtime && z.wake" class="times">{{ z.bedtime }} to {{ z.wake }}<template v-if="z.hours_before_run != null"> · woke {{ formatHours(z.hours_before_run) }} before the run</template></span>
      </div>
      <p v-if="vsUsual" class="usual" :class="`usual--${vsUsual.tone}`">{{ vsUsual.text }}</p>

      <div v-if="stages.length" class="bar" role="img" :aria-label="stages.map((s) => `${s.label} ${formatHours(s.h)}`).join(', ')">
        <span v-for="s in stages" :key="s.key" class="seg" :class="`seg--${s.key}`" :style="{ width: `${s.pct}%` }" />
      </div>
      <ul v-if="stages.length" class="stages">
        <li v-for="s in stages" :key="s.key"><i class="sw" :class="`seg--${s.key}`" /> {{ s.label }} <b class="mono">{{ formatHours(s.h) }}</b></li>
      </ul>

      <dl class="morning">
        <div v-if="z.efficiency_pct != null"><dt>Asleep while in bed</dt><dd class="mono">{{ z.efficiency_pct }}%</dd></div>
        <div v-if="z.deep_rem_pct != null"><dt>Deep and REM</dt><dd class="mono">{{ z.deep_rem_pct }}%</dd></div>
        <div v-if="rhr"><dt>Resting heart rate</dt><dd class="mono">{{ rhr.value }}<small v-if="rhr.note" :class="{ worse: rhr.worse }">{{ rhr.note }}</small></dd></div>
        <div v-if="hrv"><dt>HRV</dt><dd class="mono">{{ hrv.value }}<small v-if="hrv.note" :class="{ worse: hrv.worse }">{{ hrv.note }}</small></dd></div>
      </dl>
      <p class="src">From your watch's sleep tracking. "Usual" is your median over the previous 30 nights.</p>
    </template>
    <p v-else class="na" data-testid="sleep-na">No sleep was recorded the night before this run. Wear your watch to bed to see it here.</p>
  </GlassPanel>
</template>

<style scoped>
.sleep {
  --deep: color-mix(in srgb, var(--chart-elevation) 55%, #1e1b5c);
  --core: var(--chart-elevation);
  --rem: color-mix(in srgb, var(--chart-elevation) 45%, #9fe3ff);
  --awake: var(--chart-cadence);
  padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3);
}
.head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
.head h3 { margin: 0; }
.total { display: flex; align-items: baseline; gap: var(--space-3); flex-wrap: wrap; }
.big { font-size: 34px; line-height: 38px; font-weight: 700; color: var(--ink); }
.times { font-size: var(--body-sm-size); color: var(--ink-secondary); }
.usual { margin: 0; font-size: var(--body-sm-size); font-weight: 600; color: var(--ink-secondary); }
.usual--low { color: var(--accent-text); }
.bar { display: flex; height: 14px; border-radius: 7px; overflow: hidden; gap: 2px; background: var(--divider); }
.seg { display: block; height: 100%; transform-origin: left; animation: grow-x .8s var(--ease-settle) both; }
.seg--deep { background: var(--deep); }
.seg--core { background: var(--core); }
.seg--rem { background: var(--rem); }
.seg--awake { background: var(--awake); }
.stages { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); font-size: var(--body-sm-size); color: var(--ink-secondary); }
.stages li { display: inline-flex; align-items: center; gap: 6px; }
.stages b { color: var(--ink); font-weight: 600; }
.sw { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.morning { margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: var(--space-3) var(--space-4); padding-top: var(--space-3); border-top: 1px solid var(--divider); }
.morning dt { font-size: var(--body-sm-size); color: var(--ink-secondary); }
.morning dd { margin: 2px 0 0; font-size: 20px; font-weight: 600; color: var(--ink); white-space: nowrap; }
.morning small { display: block; font-family: var(--font-body, inherit); font-size: 12px; font-weight: 500; color: var(--ink-secondary); }
.morning small.worse { color: var(--accent-text); }
.mono { font-family: var(--font-display); font-variant-numeric: tabular-nums; }
.na, .src { margin: 0; font-size: var(--body-sm-size); color: var(--ink-secondary); }
.src { color: var(--ink-muted); }
@keyframes grow-x { from { transform: scaleX(0); } }
@media (prefers-reduced-motion: reduce) { .seg { animation: none; } }
</style>
