<script setup lang="ts">
import { computed, watch } from 'vue'
import { RouterLink } from 'vue-router'
import StatTile from '@/components/ui/StatTile.vue'
import BarChart from '@/components/ui/BarChart.vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import Icons from '@/components/ui/Icons.vue'
import { vPress } from '@/directives/press'
import InsightList from '@/components/app/InsightList.vue'
import WeekNoteEditor from '@/components/app/WeekNoteEditor.vue'
import { useSettingsStore } from '@/stores/settings'
import { useWeeksStore } from '@/stores/weeks'
import { distanceUnit, elevationUnit, formatDistance, formatDuration, formatElevation, formatPace, paceUnit } from '@/lib/units'
import { formatLocalDate, formatShortDate, formatWeekRange, typeLabel } from '@/lib/format'

const props = defineProps<{ id: string }>()
const s = useSettingsStore()
const store = useWeeksStore()
watch(() => props.id, (id) => store.loadDetail(id), { immediate: true })

const wk = computed(() => store.detail)
const du = computed(() => distanceUnit(s.units))

const zoneLabels = ['Zone 1', 'Zone 2', 'Zone 3', 'Zone 4', 'Zone 5']
const zoneMinutes = computed(() => wk.value?.intensity.zone_seconds?.map((sec) => Math.round(sec / 60)) ?? null)
const easyShare = computed(() => wk.value?.intensity.easy_share_pct ?? null)
const days = computed(() => wk.value?.days ?? [])
</script>

<template>
  <Button class="back" small :to="{ name: 'weeks' }">Back to weeks</Button>

  <p v-if="store.detailLoading" class="page-sub" role="status">Loading your week…</p>
  <template v-else-if="store.detailError">
    <h1 class="page-title">Week not found</h1>
    <p class="page-sub" role="alert">{{ store.detailError }}</p>
  </template>

  <template v-else-if="wk">
    <header class="title-row">
      <div>
        <h1 class="page-title">{{ formatWeekRange(wk.week_start, wk.week_end) }}</h1>
        <p class="page-sub">{{ wk.run_count }} {{ wk.run_count === 1 ? 'run' : 'runs' }}<template v-if="wk.long_run_count"> including {{ wk.long_run_count }} long {{ wk.long_run_count === 1 ? 'run' : 'runs' }}</template>.</p>
      </div>
    </header>

    <div class="canvas">
    <div class="s4 stats">
    <StatTile hero label="Volume" :value="formatDistance(wk.distance_m, s.units)" :unit="du" />
    <div class="grid-2">
      <StatTile label="Time" :value="formatDuration(wk.duration_s)" />
      <StatTile label="Elevation gain" :value="wk.elevation_gain_m == null ? null : formatElevation(wk.elevation_gain_m, s.units)" :unit="elevationUnit(s.units)" />
      <StatTile label="Training load" :value="String(Math.round(wk.load.total))" :unit="wk.load.estimated ? 'estimated' : undefined" />
      <StatTile label="Easy share" :value="easyShare == null ? null : String(Math.round(easyShare))" unit="% of time" />
    </div>
    </div>

    <BarChart
      v-if="zoneMinutes"
      class="s8 stretch"
      title="Intensity mix"
      caption="Minutes spent in each heart-rate zone this week"
      first-column="Zone"
      :labels="zoneLabels"
      :values="zoneMinutes"
      :format="(v) => `${Math.round(v)} min`"
      series-label="Time in zone"
    />
    <GlassPanel v-else class="missing s8" data-testid="intensity-na"><h3 class="chart-title">Intensity mix</h3><p>Intensity mix is not available for this week.</p></GlassPanel>

    <GlassPanel class="runs s5" role="group" aria-label="Load by day">
      <h3 class="chart-title">Load by day</h3>
      <table class="chart-table" data-testid="week-days">
        <thead><tr><th scope="col">Day</th><th scope="col">Load</th><th scope="col">Type</th></tr></thead>
        <tbody>
          <tr v-for="d in days" :key="d.local_date">
            <th scope="row">{{ formatShortDate(d.local_date) }}</th>
            <td>{{ Math.round(d.load) }}<template v-if="d.estimated"> (estimated)</template></td>
            <td>{{ d.is_rest ? 'Rest day' : d.is_hard ? 'Hard day' : '–' }}</td>
          </tr>
        </tbody>
      </table>
    </GlassPanel>

    <section class="stack s7" aria-labelledby="wk-runs-h">
      <h2 id="wk-runs-h" class="section-title">Runs this week</h2>
      <p v-if="!wk.runs.length" class="page-sub" data-testid="week-no-runs">You have no runs this week.</p>
      <GlassPanel v-for="r in wk.runs" :key="r.workout_id" as="div">
        <RouterLink v-press class="row-link" :to="{ name: 'run-detail', params: { id: r.workout_id } }">
          <span>
            <span class="row-title">{{ typeLabel(r.type) }}{{ r.is_indoor ? ', indoor' : '' }}</span><br />
            <span class="row-meta">
              {{ formatLocalDate(r.local_date) }} · {{ formatDistance(r.distance_m, s.units) }} {{ du }} · {{ formatDuration(r.duration_s) }} ·
              {{ formatPace(r.avg_speed_mps, s.units) }}{{ r.avg_speed_mps ? paceUnit(s.units) : '' }}
            </span>
          </span>
          <Icons name="chevron" :size="20" />
        </RouterLink>
      </GlassPanel>
    </section>

    <InsightList class="s7" :week="wk.week_id" title="Insights for this week" empty-text="No insights for this week." />

    <WeekNoteEditor class="s5" :week-id="wk.week_id" :note="wk.note" />
    </div>
  </template>
</template>

<style scoped>
.head { margin: 0; }
.stats { display: flex; flex-direction: column; gap: var(--space-4); }
@media (min-width: 1080px) { .stats { gap: var(--space-6); } }
.runs, .missing { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-2); }
.runs h3, .missing h3 { margin: 0; }
.missing p { margin: 0; color: var(--ink-secondary); }
</style>
