<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import StatTile from '@/components/ui/StatTile.vue'
import LineChart from '@/components/ui/LineChart.vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Icons from '@/components/ui/Icons.vue'
import Button from '@/components/ui/Button.vue'
import SplitsTable from '@/components/app/SplitsTable.vue'
import NoteEditor from '@/components/app/NoteEditor.vue'
import InsightList from '@/components/app/InsightList.vue'
import WorkoutDetails from '@/components/app/WorkoutDetails.vue'
import RunSummary from '@/components/app/RunSummary.vue'
import RunHero from '@/components/app/RunHero.vue'
import ConditionsCard from '@/components/app/ConditionsCard.vue'
import SleepCard from '@/components/app/SleepCard.vue'
import RunWalkCard from '@/components/app/RunWalkCard.vue'
import { useRoute } from 'vue-router'
import { sleepLine } from '@/lib/sleep'
import { conditionsLine } from '@/lib/conditions'
import { useSettingsStore } from '@/stores/settings'
import { useWorkoutsStore } from '@/stores/workouts'
import { useRoutesStore } from '@/stores/routes'
import {
  distanceUnit,
  distanceValue,
  elevationUnit,
  formatClock,
  formatDistance,
  formatDuration,
  formatElevation,
  formatPace,
  formatWeightValue,
  weightUnit,
  metersToFeet,
  paceSeconds,
  paceUnit,
} from '@/lib/units'
import { formatLocalDate, sampleIndices, typeLabel } from '@/lib/format'
import { qualityNotes } from '@/lib/quality'

const props = defineProps<{ id: string }>()
const s = useSettingsStore()
const w = useWorkoutsStore()
const routes = useRoutesStore()
const routeKey = ref<string | null>(null)
watch(
  () => w.detail,
  async (d) => {
    routeKey.value = null
    if (d?.workout.has_route) routeKey.value = await routes.routeKeyFor(d.workout.workout_id)
  },
)
watch(() => props.id, (id) => w.loadDetail(id), { immediate: true })

const MAX_POINTS = 40
const LABEL_EVERY = 8
const du = computed(() => distanceUnit(s.units))
const detail = computed(() => w.detail)
const run = computed(() => detail.value?.workout ?? null)
// A strength workout has heart rate and effort but no distance, pace, map or shoe.
const isStrength = computed(() => run.value?.type === 'strength')
const zones = computed(() => {
  const z = detail.value?.zone_seconds
  return z?.length && z.some((sec) => sec > 0) ? z.map((sec, i) => ({ label: `Zone ${i + 1}`, value: formatDuration(sec) })) : null
})
// Back goes to the list the workout is on: runs on Runs, walks and hikes on Other activities.
const route = useRoute()
const fromActivities = computed(() => route?.query?.from === 'activities')
const backName = computed(() => ((run.value ? run.value.type !== 'run' : fromActivities.value) ? 'activities' : 'runs'))
const backLabel = computed(() => (backName.value === 'runs' ? 'Back to runs' : 'Back to other activities'))
const notes = computed(() => (detail.value ? qualityNotes(detail.value.quality_flags, detail.value.data_quality_issues) : []))

// Stopped or near-stopped samples are gaps, not infinite pace.
const MIN_SPEED_MPS = 0.5
const MAX_PACE_S = 30 * 60
const SMOOTH_WINDOW_S = 45
function medianOf(xs: number[]): number {
  const a = [...xs].sort((x, y) => x - y)
  const m = a.length >> 1
  return a.length % 2 ? a[m]! : (a[m - 1]! + a[m]!) / 2
}
const pace = computed(() => {
  const series = detail.value?.pace_series
  if (!series?.length) return null
  const raw = series.map((p) => paceSeconds(p.speed_mps, s.units))
  const valid = series.map((p, i) => (p.speed_mps ?? 0) >= MIN_SPEED_MPS && raw[i] != null && raw[i]! <= MAX_PACE_S)
  // Rolling median over a time window; gaps stay gaps.
  const smoothAt = (i: number): number | null => {
    const p = series[i]!
    if (!valid[i]) return null
    const win: number[] = []
    for (let j = 0; j < series.length; j++) {
      if (valid[j] && Math.abs(series[j]!.t_s - p.t_s) <= SMOOTH_WINDOW_S / 2) win.push(raw[j]!)
    }
    return win.length ? medianOf(win) : raw[i]!
  }
  const idx = sampleIndices(series.length, MAX_POINTS)
  return {
    labels: idx.map((i) => distanceValue(series[i]!.distance_m, s.units).toFixed(2)),
    values: idx.map(smoothAt),
    raw: idx.map((i) => raw[i] ?? null),
  }
})
const hr = computed(() => {
  const series = detail.value?.hr_series
  if (!series?.length) return null
  const idx = sampleIndices(series.length, MAX_POINTS)
  return { labels: idx.map((i) => formatClock(series[i]!.t_s)), values: idx.map((i) => series[i]!.avg) }
})
const elev = computed(() => {
  const series = detail.value?.elevation_series
  if (!series?.length) return null
  const idx = sampleIndices(series.length, MAX_POINTS)
  return {
    labels: idx.map((i) => distanceValue(series[i]!.distance_m, s.units).toFixed(2)),
    values: idx.map((i) => (s.units === 'imperial' ? metersToFeet(series[i]!.altitude_m) : series[i]!.altitude_m)),
  }
})
</script>

<template>
  <Button v-if="!(run && detail) || w.detailLoading || w.detailError" class="back" small :to="{ name: backName }">{{ backLabel }}</Button>

  <p v-if="w.detailLoading" class="page-sub" role="status">Loading your workout…</p>
  <template v-else-if="w.detailError">
    <h1 class="page-title">Workout not found</h1>
    <p class="page-sub" role="alert">{{ w.detailError }}</p>
  </template>

  <template v-else-if="run && detail">
    <RunHero
      :key="run.workout_id"
      :geometry="detail.display_geometry"
      :title="`${typeLabel(run.type)}${run.is_indoor ? ', indoor' : ''}`"
      :date="formatLocalDate(run.local_date)"
      :conditions="conditionsLine(detail.conditions, s.units)"
      :sleep="sleepLine(detail.sleep)"
      :carry="detail.carry_kg == null ? null : `Carrying ${formatWeightValue(detail.carry_kg, s.units)} ${weightUnit(s.units)}`"
      :stats="isStrength ? [] : [
        { label: 'Distance', value: run.distance_m == null ? null : formatDistance(run.distance_m, s.units, 2), unit: du },
        { label: 'Time', value: run.duration_s == null ? null : formatDuration(run.duration_s) },
        { label: 'Avg pace', value: run.avg_speed_mps == null ? null : formatPace(run.avg_speed_mps, s.units), unit: paceUnit(s.units) },
        { label: 'Elev gain', value: run.elevation_gain_m == null ? null : formatElevation(run.elevation_gain_m, s.units), unit: elevationUnit(s.units) },
      ]"
    >
      <template #start>
        <Button small :to="{ name: backName }" data-testid="back-link"><Icons name="chevron" :size="16" class="flip" /> {{ run.type === 'run' ? 'Runs' : 'Other activities' }}</Button>
      </template>
      <template #end>
        <Button v-if="routeKey" small :to="{ name: 'route-detail', params: { routeKey } }" data-testid="route-link">Other runs on this route</Button>
      </template>
    </RunHero>

    <div class="canvas over">
      <StatTile class="s3" label="Avg heart rate" :value="run.avg_hr == null ? null : String(Math.round(run.avg_hr))" unit="bpm" />
      <StatTile class="s3" label="Max heart rate" :value="run.max_hr == null ? null : String(Math.round(run.max_hr))" unit="bpm" />
      <StatTile
        v-if="isStrength"
        class="s3"
        label="Effort"
        :value="detail.effort_score == null ? null : String(Math.round(detail.effort_score))"
        unit="/ 10"
        :sub="detail.effort_score != null && detail.effort_estimated ? 'Estimated by Apple' : null"
        data-testid="effort"
      />
      <StatTile v-else class="s3" label="Cadence" :value="detail.avg_cadence == null ? null : String(Math.round(detail.avg_cadence))" unit="spm" />
      <StatTile
        v-if="isStrength"
        class="s3"
        label="Time"
        :value="run.duration_s == null ? null : formatDuration(run.duration_s)"
      />
      <StatTile
        v-else
        class="s3"
        label="Training load"
        :value="detail.training_load == null ? null : String(Math.round(detail.training_load))"
        :sub="detail.training_load == null ? null : detail.training_load_estimated ? 'Estimated: heart rate was patchy' : 'Heart rate × time'"
        data-testid="training-load"
      />

      <RunSummary class="wide" :summary="detail.summary" />

      <WorkoutDetails
        v-if="!isStrength"
        class="wide"
        :workout-id="run.workout_id"
        :type="run.type"
        :shoe="detail.shoe ?? null"
        :shoe-chosen="detail.shoe_chosen"
        :carry-kg="detail.carry_kg ?? null"
      />

      <GlassPanel v-if="notes.length" class="notes" role="group" aria-label="Data quality notes">
        <h3 class="chart-title"><Icons name="warning" :size="16" /> Data notes</h3>
        <ul data-testid="quality-notes">
          <li v-for="n in notes" :key="n">{{ n }}</li>
        </ul>
      </GlassPanel>

      <GlassPanel v-if="isStrength && zones" class="s6" data-testid="zones">
        <h3 class="chart-title">Time in heart rate zones</h3>
        <dl class="zones"><div v-for="z in zones" :key="z.label"><dt>{{ z.label }}</dt><dd>{{ z.value }}</dd></div></dl>
      </GlassPanel>

      <LineChart
        v-if="pace"
        class="s6"
        title="Pace"
        :caption="`min${paceUnit(s.units)} by distance (${du}), faster reads toward the top`"
        :first-column="`Distance (${du})`"
        :labels="pace.labels"
        :label-every="LABEL_EVERY"
        :series="[{ label: 'Pace', role: 'emphasis', color: 'chart-pace', icon: 'pace', values: pace.values, tableValues: pace.raw }]"
        :format="formatClock"
        lower-is-up
      />
      <GlassPanel v-else-if="!isStrength" class="missing s6" data-testid="pace-na"><h3 class="chart-title">Pace</h3><p>Pace is not available for this workout.</p></GlassPanel>

      <LineChart
        v-if="hr"
        class="s6"
        title="Heart rate"
        caption="Beats per minute over time"
        first-column="Time"
        :labels="hr.labels"
        :label-every="LABEL_EVERY"
        :series="[{ label: 'Heart rate', role: 'emphasis', color: 'chart-heart-rate', icon: 'heart-rate', values: hr.values }]"
        :format="(v) => String(Math.round(v))"
      />
      <GlassPanel v-else class="missing s6" data-testid="hr-na"><h3 class="chart-title">Heart rate</h3><p>Heart rate is not available for this workout.</p></GlassPanel>

      <LineChart
        v-if="elev && !isStrength"
        class="s6"
        title="Elevation"
        :caption="`${elevationUnit(s.units) === 'ft' ? 'Feet' : 'Metres'} above sea level by distance (${du})`"
        :first-column="`Distance (${du})`"
        :labels="elev.labels"
        :label-every="LABEL_EVERY"
        :series="[{ label: 'Elevation', role: 'emphasis', color: 'chart-elevation', icon: 'elevation', values: elev.values }]"
        :format="(v) => String(Math.round(v))"
      />
      <GlassPanel v-else-if="!isStrength" class="missing s6" data-testid="elev-na"><h3 class="chart-title">Elevation</h3><p>Elevation is not available for this workout.</p></GlassPanel>

      <SplitsTable v-if="!isStrength" class="s6" :splits-km="detail.splits_km" :splits-mi="detail.splits_mi" :units="s.units" />

      <ConditionsCard v-if="!run.is_indoor && !isStrength" class="s6" :conditions="detail.conditions ?? null" :gap="detail.gap ?? null" :speed-mps="run.avg_speed_mps" :units="s.units" />

      <RunWalkCard v-if="run.type === 'run'" class="s6" :runwalk="detail.runwalk ?? null" :units="s.units" />

      <SleepCard v-if="!isStrength" class="s6" :sleep="detail.sleep ?? null" :workout-id="run.workout_id" />

      <InsightList v-if="!isStrength" class="s7" :run="run.workout_id" title="Insights for this run" empty-text="No insights for this run." />

      <NoteEditor class="s5" :workout-id="run.workout_id" :note="detail.note" />
    </div>
  </template>
</template>

<style scoped>
.notes, .missing { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-2); }
.notes h3, .missing h3 { margin: 0; display: flex; align-items: center; gap: var(--space-2); }
.notes ul { margin: 0; padding-left: var(--space-5); color: var(--ink-secondary); font-size: var(--body-sm-size); }
.missing p { margin: 0; color: var(--ink-secondary); }
.over { position: relative; z-index: 2; margin-top: -56px; }
.over > :nth-child(-n+4) { min-height: 112px; align-self: stretch; }
.over > .wide { grid-column: 1 / -1; }
/* Below desktop the four figures sit two by two, so none is squeezed. */
@media (max-width: 1079px) { .over { grid-template-columns: repeat(2, minmax(0, 1fr)); } .over > :nth-child(n+5) { grid-column: 1 / -1; } }
@media (max-width: 1079px) { .over > :nth-child(-n+4) { padding: var(--space-3) var(--space-4); } .over > :nth-child(-n+4) :deep(.num--sm) { font-size: 24px; line-height: 28px; } }

.zones { margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); gap: var(--space-3); }
.zones dt { color: var(--ink-secondary); font-size: var(--body-sm-size); }
.zones dd { margin: 0; font-weight: 600; }
.flip { transform: rotate(180deg); }
</style>
