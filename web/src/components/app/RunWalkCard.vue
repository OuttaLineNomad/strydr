<script setup lang="ts">
import { computed } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import type { RunWalk } from '@/api/types'
import { NOT_AVAILABLE, formatPace, paceUnit, type UnitSystem } from '@/lib/units'

// How much of the run was running and how much was walking. Cadence is compared with a cutoff learned from your
// own runs; pace stands in when a run has no steps. Standing still counts as neither.
const props = defineProps<{ runwalk: RunWalk | null; units: UnitSystem }>()

const pct = (v: number) => `${Math.round(v)}%`
const line = computed(() => {
  const r = props.runwalk
  if (!r) return ''
  const parts = [`Running ${pct(r.run_pct)}`, `Walking ${pct(r.walk_pct)}`]
  if (r.stopped_pct > 0) parts.push(`Stopped ${pct(r.stopped_pct)}`)
  return parts.join(' · ')
})
const how = computed(() => {
  const r = props.runwalk
  if (!r) return ''
  const cutoff = r.source === 'cadence' ? `${Math.round(r.cutoff)} steps per minute` : `${formatPace(r.cutoff, props.units)} ${paceUnit(props.units)}`
  const kind = r.cutoff_learned ? 'learned from your runs' : 'the default'
  return `From ${r.source}. Walking is slower than ${cutoff}, ${kind}.`
})
</script>

<template>
  <GlassPanel class="rw" role="group" aria-label="Run and walk split" data-testid="runwalk">
    <h3 class="chart-title">Run and walk</h3>
    <template v-if="runwalk">
      <p class="big mono" data-testid="runwalk-line">{{ line }}</p>
      <p class="how" data-testid="runwalk-how">{{ how }}</p>
      <p v-if="runwalk.walk_pct > 0" class="how"><span class="swatch" aria-hidden="true" /> Walking sections are blue on the map.</p>
    </template>
    <p v-else class="how" data-testid="runwalk-na">{{ NOT_AVAILABLE }}: this run has no steps or pace.</p>
  </GlassPanel>
</template>

<style scoped>
.rw { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-2); }
.rw h3 { margin: 0; }
.big { margin: 0; font-size: 22px; line-height: 28px; font-weight: 700; color: var(--ink); }
.how { margin: 0; font-size: var(--body-sm-size); color: var(--ink-secondary); }
.swatch { display: inline-block; width: 18px; height: 4px; border-radius: 2px; background: var(--chart-elevation); vertical-align: middle; }
</style>
