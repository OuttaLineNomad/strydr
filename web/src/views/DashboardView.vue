<script setup lang="ts">
import { computed, onMounted } from 'vue'
import StatTile, { type Trend } from '@/components/ui/StatTile.vue'
import BarChart from '@/components/ui/BarChart.vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import Icons from '@/components/ui/Icons.vue'
import Segmented from '@/components/ui/Segmented.vue'
import InsightList from '@/components/app/InsightList.vue'
import SyncStatusLine from '@/components/app/SyncStatusLine.vue'
import { useSettingsStore } from '@/stores/settings'
import { RANGES, useDashboardStore } from '@/stores/dashboard'
import { distanceUnit, distanceValue, formatClock, formatPace, paceSeconds, paceUnit } from '@/lib/units'
import { formatLocalDate, formatShortDate } from '@/lib/format'
import type { Tile } from '@/api/types'

const s = useSettingsStore()
const d = useDashboardStore()
onMounted(() => d.load())

const du = computed(() => distanceUnit(s.units))
const weeks = computed(() => d.data?.weeks ?? [])
const hasRuns = computed(() => weeks.value.some((w) => w.run_count > 0))
const rangeOptions = RANGES.map((r) => ({ label: `${r}w`, value: r as number }))
const pickRange = (r: number) => d.load(r as (typeof RANGES)[number])

/** Latest vs PR for one tile. The trend only appears when both values exist. */
function tiles(t: Tile | undefined, label: string) {
  const latestPace = paceSeconds(t?.latest_speed_mps, s.units)
  const prPace = paceSeconds(t?.pr_speed_mps, s.units)
  let trend: Trend | undefined
  if (latestPace != null && prPace != null) {
    const diff = latestPace - prPace
    const same = Math.abs(diff) <= 0.5
    const slower = diff > 0.5
    trend = {
      direction: same ? 'flat' : slower ? 'up' : 'down',
      text: same ? 'Matches your PR' : `${formatClock(Math.abs(diff))} ${slower ? 'slower' : 'faster'} than your PR`,
      good: !slower,
    }
  }
  return {
    latest: { label: `${label}, latest`, value: t?.latest_speed_mps == null ? null : formatPace(t.latest_speed_mps, s.units), sub: t?.latest_local_date ? formatLocalDate(t.latest_local_date) : null, trend },
    pr: { label: `${label}, PR`, value: t?.pr_speed_mps == null ? null : formatPace(t.pr_speed_mps, s.units), sub: t?.pr_local_date ? `Set ${formatLocalDate(t.pr_local_date)}` : null },
  }
}
const mile = computed(() => tiles(d.data?.one_mile_pace, '1-mile pace'))
const avg = computed(() => tiles(d.data?.avg_pace, 'Average pace'))

const labels = computed(() => weeks.value.map((w) => formatShortDate(w.week_start)))
const values = computed(() => weeks.value.map((w) => distanceValue(w.distance_m, s.units)))
const labelEvery = computed(() => Math.max(1, Math.ceil(weeks.value.length / 8)))

// This week against last week, from the same series the chart draws.
const thisWeek = computed(() => values.value[values.value.length - 1] ?? null)
const lastWeek = computed(() => values.value[values.value.length - 2] ?? null)
const weekTrend = computed<Trend | undefined>(() => {
  if (thisWeek.value == null || lastWeek.value == null) return undefined
  const diff = Number(thisWeek.value.toFixed(1)) - Number(lastWeek.value.toFixed(1))
  if (Math.abs(diff) < 0.05) return { direction: 'flat', text: 'Same as last week', good: true }
  return { direction: diff > 0 ? 'up' : 'down', text: `${diff > 0 ? '+' : '−'}${Math.abs(diff).toFixed(1)} ${du.value} vs last week`, good: diff > 0 }
})
const runsThisWeek = computed(() => weeks.value[weeks.value.length - 1]?.run_count ?? null)
const rangeTotal = computed(() => values.value.reduce((a, b) => a + b, 0))
const runsInRange = computed(() => weeks.value.reduce((a, w) => a + w.run_count, 0))

// The caption states a finding: the biggest week in range.
const caption = computed(() => {
  const unitWord = du.value === 'mi' ? 'Miles' : 'Kilometres'
  if (!hasRuns.value) return `${unitWord} per week. No runs in the last ${d.weeks} weeks.`
  let best = 0
  values.value.forEach((v, i) => v > values.value[best]! && (best = i))
  return `${unitWord} per week. Biggest: ${values.value[best]!.toFixed(1)} ${du.value}, week of ${labels.value[best]}.`
})
</script>

<template>
  <header class="title-row">
    <div>
      <h1 class="page-title">Dashboard</h1>
      <SyncStatusLine :sync="d.sync" :tz="s.homeTz" />
    </div>
    <Button icon variant="glass" to="/settings" label="Settings" data-testid="settings-gear"><Icons name="settings" :size="22" /></Button>
  </header>

  <p v-if="d.error" class="err" role="alert" data-testid="dash-error">{{ d.error }}</p>

  <div class="canvas">
    <BarChart
      v-if="weeks.length"
      class="s8 stretch"
      title="Weekly distance"
      :caption="caption"
      first-column="Week of"
      :labels="labels"
      :values="values"
      :label-every="labelEvery"
      :format="(v) => v.toFixed(1)"
      series-label="Distance"
    >
      <template #controls>
        <Segmented :model-value="d.weeks" :options="rangeOptions" label="Range in weeks" @update:model-value="pickRange" />
      </template>
    </BarChart>
    <GlassPanel v-else-if="!d.loading" class="s8 empty">
      <h2 class="chart-title">Weekly distance</h2>
      <p class="page-sub">Your weekly totals appear once your first workouts sync.</p>
    </GlassPanel>

    <div class="s4 week-col">
      <StatTile hero label="This week" :value="thisWeek == null ? null : thisWeek.toFixed(1)" :unit="du" :trend="weekTrend" />
      <div class="grid-2">
        <StatTile label="Runs this week" :value="runsThisWeek == null ? null : String(runsThisWeek)" />
        <StatTile :label="`Last ${d.weeks} weeks`" :value="weeks.length ? rangeTotal.toFixed(1) : null" :unit="du" :sub="weeks.length ? `${runsInRange} ${runsInRange === 1 ? 'run' : 'runs'}` : null" />
      </div>
    </div>

    <InsightList class="s7" title="Insights" />

    <section class="s5 stack" aria-labelledby="pr-h">
      <h2 id="pr-h" class="section-title">Latest vs your PR</h2>
      <div class="grid-2">
        <StatTile :label="mile.latest.label" :value="mile.latest.value" :unit="paceUnit(s.units)" :trend="mile.latest.trend" :sub="mile.latest.sub" />
        <StatTile :label="mile.pr.label" :value="mile.pr.value" :unit="paceUnit(s.units)" :sub="mile.pr.sub" />
        <StatTile :label="avg.latest.label" :value="avg.latest.value" :unit="paceUnit(s.units)" :trend="avg.latest.trend" :sub="avg.latest.sub" />
        <StatTile :label="avg.pr.label" :value="avg.pr.value" :unit="paceUnit(s.units)" :sub="avg.pr.sub" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.week-col { display: flex; flex-direction: column; gap: var(--space-4); }
@media (min-width: 1080px) { .week-col { gap: var(--space-6); align-self: stretch; } .week-col > :first-child { flex: 1; justify-content: center; } }
.empty { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-2); }
.empty h2 { margin: 0; }
.err { margin: 0; color: var(--danger); }
</style>
