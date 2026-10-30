<script setup lang="ts">
import { computed } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import type { SplitOut } from '@/api/types'
import {
  NOT_AVAILABLE,
  distanceUnit,
  distanceValue,
  elevationUnit,
  formatClock,
  formatElevation,
  formatPace,
  paceUnit,
  type UnitSystem,
} from '@/lib/units'

const props = defineProps<{
  splitsKm: SplitOut[] | null
  splitsMi: SplitOut[] | null
  units: UnitSystem
}>()

// The API sends both sets of splits; the unit setting picks one.
const splits = computed(() => (props.units === 'imperial' ? props.splitsMi : props.splitsKm))
const du = computed(() => distanceUnit(props.units))
const rows = computed(() =>
  (splits.value ?? []).map((s) => ({
    key: s.index,
    label: s.partial ? `${s.index + 1} (${distanceValue(s.distance_m, props.units).toFixed(2)} ${du.value})` : String(s.index + 1),
    pace: formatPace(s.speed_mps, props.units),
    // Grade adjusted pace: only on splits with real climb or descent, "flat" otherwise.
    gap: s.gap_speed_mps == null ? 'flat' : formatPace(s.gap_speed_mps, props.units),
    time: formatClock(s.duration_s),
    hr: s.avg_hr == null ? NOT_AVAILABLE : String(Math.round(s.avg_hr)),
    elev: s.elevation_change_m == null ? NOT_AVAILABLE : (s.elevation_change_m > 0 ? '+' : '') + formatElevation(s.elevation_change_m, props.units),
  })),
)
</script>

<template>
  <GlassPanel class="splits" role="group" aria-label="Splits">
    <h3 class="chart-title">Splits</h3>
    <p v-if="!splits || !splits.length" class="na" data-testid="splits-na">Splits are not available for this workout.</p>
    <div v-else class="scroll">
      <table class="chart-table mono" data-testid="splits-table">
        <caption class="sr-only">Splits per {{ du }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ du === 'mi' ? 'Mile' : 'Km' }}</th>
            <th scope="col">Pace ({{ paceUnit(units) }})</th>
            <th scope="col"><abbr title="Grade adjusted pace: the flat-ground pace of the same effort (estimate)">GAP</abbr></th>
            <th scope="col">Time</th>
            <th scope="col">HR (bpm)</th>
            <th scope="col">Elev ({{ elevationUnit(units) }})</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.key">
            <th scope="row">{{ r.label }}</th>
            <td>{{ r.pace }}</td>
            <td :class="{ muted: r.gap === 'flat' }">{{ r.gap }}</td>
            <td>{{ r.time }}</td>
            <td>{{ r.hr }}</td>
            <td>{{ r.elev }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </GlassPanel>
</template>

<style scoped>
.splits { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.splits h3 { margin: 0; }
.scroll { overflow-x: auto; }
.mono, .mono th, .mono td { font-family: var(--font-display); font-variant-numeric: tabular-nums; }
.mono th[scope='row'] { text-transform: none; letter-spacing: 0; font-size: 13px; color: var(--ink-secondary); font-weight: 400; white-space: nowrap; }
.na { margin: 0; color: var(--ink-muted); }
.muted { color: var(--ink-muted); }
abbr { text-decoration: none; cursor: help; }
</style>
