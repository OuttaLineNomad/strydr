<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import HistorySwitch from '@/components/app/HistorySwitch.vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import StatTile, { type Trend } from '@/components/ui/StatTile.vue'
import LineChart from '@/components/ui/LineChart.vue'
import Icons from '@/components/ui/Icons.vue'
import Button from '@/components/ui/Button.vue'
import { vPress } from '@/directives/press'
import { api } from '@/api'
import type { Recap } from '@/api/types'
import { useSettingsStore } from '@/stores/settings'
import { distanceUnit, distanceValue, elevationUnit, formatDistance, formatDuration, formatElevation } from '@/lib/units'
import { formatLocalDate, formatShortDate, formatWeekRange } from '@/lib/format'

// A look back over one month or one year, assembled by the server from existing data. Runs only.
const s = useSettingsStore()
const route = useRoute()
const router = useRouter()
const data = ref<Recap | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const PERIOD = /^\d{4}(-\d{2})?$/
const thisMonth = () => {
  const n = new Date()
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}`
}
const period = computed(() => (typeof route.query.period === 'string' && PERIOD.test(route.query.period) ? route.query.period : thisMonth()))
const isYear = computed(() => period.value.length === 4)

let seq = 0
async function load(p: string) {
  const mine = ++seq
  if (data.value?.period !== p) data.value = null  // never show another period's numbers under this heading
  loading.value = true
  error.value = null
  try {
    const { data: d } = await api.GET('/api/v1/recap/{period}', { params: { path: { period: p } } })
    if (mine !== seq) return
    if (d) data.value = d
    else error.value = 'Your recap could not load. Try again in a moment.'
  } catch {
    if (mine === seq) error.value = 'Your recap could not load. Check your connection and try again.'
  } finally {
    if (mine === seq) loading.value = false
  }
}
watch(period, load, { immediate: true })

function shift(p: string, by: number): string {
  if (p.length === 4) return String(Number(p) + by)
  const [y, mo] = p.split('-').map(Number) as [number, number]
  const d = new Date(Date.UTC(y, mo - 1 + by, 1))
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
}
const go = (to: string) => router.push({ name: 'recap', query: { period: to } })
const label = (p: string) => {
  if (p.length === 4) return p
  const [y, mo] = p.split('-').map(Number) as [number, number]
  return new Date(Date.UTC(y, mo - 1, 1)).toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}
function setKind(kind: 'month' | 'year') {
  if ((kind === 'year') === isYear.value) return
  if (kind === 'year') return go(period.value.slice(0, 4))
  go(data.value?.is_current || period.value === thisMonth().slice(0, 4) ? thisMonth() : `${period.value}-12`)
}
const nextDisabled = computed(() => (data.value ? data.value.is_current : period.value >= (isYear.value ? thisMonth().slice(0, 4) : thisMonth())))
const noun = computed(() => (isYear.value ? 'year' : 'month'))

const du = computed(() => distanceUnit(s.units))
const eu = computed(() => elevationUnit(s.units))
const trend = computed<Trend | undefined>(() => {
  const d = data.value
  if (!d || d.is_current || !d.previous.run_count) return undefined  // a partial period is not comparable with a whole one
  const diff = distanceValue(d.totals.distance_m - d.previous.distance_m, s.units)
  const dir = Math.abs(diff) < 0.05 ? 'flat' : diff > 0 ? 'up' : 'down'
  return { direction: dir, text: `${diff > 0 ? '+' : ''}${diff.toFixed(1)} ${du.value} vs ${label(d.previous.period)}`, good: diff >= 0 }
})
const empty = computed(() => !!data.value && data.value.totals.run_count === 0)
const fitnessLabels = computed(() => (data.value?.fitness?.series ?? []).map((p) => formatShortDate(p.local_date)))
const fitnessSeries = computed(() => [{ label: 'Fitness', role: 'emphasis' as const, values: (data.value?.fitness?.series ?? []).map((p) => p.fitness) }])
</script>

<template>
  <HistorySwitch current="recap" />
  <header class="title-row">
    <div>
      <h1 class="page-title">Recap</h1>
      <p class="page-sub">A look back over a {{ noun }} of running.</p>
    </div>
    <div class="controls">
      <div class="switch" role="group" aria-label="Period">
        <Button small :aria-pressed="!isYear" data-testid="recap-month" @click="setKind('month')">Month</Button>
        <Button small :aria-pressed="isYear" data-testid="recap-year" @click="setKind('year')">Year</Button>
      </div>
      <nav class="month-nav" :aria-label="isYear ? 'Year' : 'Month'">
        <Button small icon :label="`Previous ${noun}`" data-testid="recap-prev" @click="go(shift(period, -1))"><Icons name="chevron" :size="16" class="flip" /></Button>
        <span class="month" aria-live="polite" data-testid="recap-period">{{ label(period) }}<template v-if="data?.is_current"> so far</template></span>
        <Button small icon :label="`Next ${noun}`" :disabled="nextDisabled" data-testid="recap-next" @click="go(shift(period, 1))"><Icons name="chevron" :size="16" /></Button>
      </nav>
    </div>
  </header>

  <p v-if="error" class="err" role="alert">{{ error }}</p>

  <template v-if="data">
    <p v-if="empty" class="page-sub" data-testid="recap-empty">No runs in {{ label(data.period) }}.</p>
    <template v-else>
      <div class="canvas tiles" :aria-busy="loading" data-testid="recap-totals">
        <StatTile class="s3" :label="data.is_current ? 'Distance so far' : 'Distance'" :value="formatDistance(data.totals.distance_m, s.units)" :unit="du" :trend="trend" />
        <StatTile class="s3" label="Runs" :value="String(data.totals.run_count)" :sub="`${formatDuration(data.totals.duration_s)} running`" />
        <StatTile class="s3" label="Active days" :value="String(data.totals.active_days)" :sub="data.totals.long_run_count ? `${data.totals.long_run_count} long ${data.totals.long_run_count === 1 ? 'run' : 'runs'}` : null" />
        <StatTile class="s3" label="Elevation" :value="data.totals.elevation_gain_m == null ? null : formatElevation(data.totals.elevation_gain_m, s.units)" :unit="eu" />
      </div>

      <template v-if="data.longest_runs.length">
        <h2 class="section-title">Longest runs</h2>
        <div class="cards" data-testid="recap-longest">
          <GlassPanel v-for="w in data.longest_runs" :key="w.workout_id" as="div">
            <RouterLink v-press class="row-link" :to="{ name: 'run-detail', params: { id: w.workout_id } }" data-testid="recap-run">
              <span>
                <span class="row-title">{{ formatDistance(w.distance_m, s.units) + (w.distance_m == null ? '' : ` ${du}`) }}</span><br />
                <span class="row-meta">{{ formatLocalDate(w.local_date) }} · {{ formatDuration(w.duration_s) }}</span>
              </span>
              <Icons name="chevron" :size="20" />
            </RouterLink>
          </GlassPanel>
        </div>
      </template>

      <template v-if="data.top_routes.length">
        <h2 class="section-title">Top routes</h2>
        <div class="cards" data-testid="recap-routes">
          <GlassPanel v-for="r in data.top_routes" :key="r.route_key" as="div">
            <RouterLink v-press class="row-link" :to="{ name: 'route-detail', params: { routeKey: r.route_key } }" data-testid="recap-route">
              <span>
                <span class="row-title">{{ formatDistance(r.distance_m, s.units) }} {{ du }} route</span><br />
                <span class="row-meta">{{ r.runs }} {{ r.runs === 1 ? 'run' : 'runs' }} this {{ noun }}</span>
              </span>
              <Icons name="chevron" :size="20" />
            </RouterLink>
          </GlassPanel>
        </div>
      </template>

      <template v-if="data.shoes.length">
        <h2 class="section-title">Shoes</h2>
        <GlassPanel class="list" data-testid="recap-shoes">
          <ul>
            <li v-for="sh in data.shoes" :key="sh.id" data-testid="recap-shoe">
              <span class="row-title">{{ sh.name }}<small v-if="sh.retired" class="tag" data-testid="recap-retired"> Retired</small></span>
              <span class="row-meta">{{ formatDistance(sh.distance_m, s.units) }} {{ du }} · {{ sh.runs }} {{ sh.runs === 1 ? 'run' : 'runs' }}</span>
            </li>
          </ul>
        </GlassPanel>
      </template>

      <template v-if="data.fitness && data.fitness.series.length > 1">
        <h2 class="section-title">Fitness</h2>
        <GlassPanel class="chart" data-testid="recap-fitness">
          <p class="row-meta">{{ Math.round(data.fitness.start) }} to {{ Math.round(data.fitness.end) }}</p>
          <LineChart
            title="Fitness trend"
            :caption="isYear ? 'Fitness at the end of each week.' : 'Fitness each day.'"
            :labels="fitnessLabels"
            :series="fitnessSeries"
            :format="(v: number) => String(Math.round(v))"
            :label-every="Math.max(1, Math.ceil(fitnessLabels.length / 6))"
            first-column="Date"
          />
        </GlassPanel>
      </template>

      <template v-if="data.best_weeks.length">
        <h2 class="section-title">Best weeks</h2>
        <div class="cards" data-testid="recap-weeks">
          <GlassPanel v-for="wk in data.best_weeks" :key="wk.week_id" as="div">
            <RouterLink v-press class="row-link" :to="{ name: 'week-detail', params: { id: wk.week_id } }" data-testid="recap-week">
              <span>
                <span class="row-title">{{ formatWeekRange(wk.week_start, wk.week_end) }}</span><br />
                <span class="row-meta">{{ formatDistance(wk.distance_m, s.units) }} {{ du }} · {{ wk.run_count }} {{ wk.run_count === 1 ? 'run' : 'runs' }}</span>
              </span>
              <Icons name="chevron" :size="20" />
            </RouterLink>
          </GlassPanel>
        </div>
      </template>
    </template>
  </template>
</template>

<style scoped>
.controls { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
.switch { display: flex; gap: var(--space-1); }
.switch :deep([aria-pressed='true']) { color: var(--accent-text); background: color-mix(in srgb, var(--accent) 16%, transparent); }
.month-nav { display: flex; align-items: center; gap: var(--space-2); }
.month { min-width: 150px; text-align: center; font-family: var(--font-display); font-weight: 700; font-size: 17px; }
.flip { transform: rotate(180deg); }
.err { margin: 0; color: var(--danger); }
.tiles { margin-bottom: var(--space-2); }
@media (max-width: 1079px) { .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.section-title { margin-top: var(--space-6); margin-bottom: var(--space-2); }
.list { padding: var(--space-4); }
.list ul { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
.list li { display: flex; justify-content: space-between; gap: var(--space-4); }
.tag { font-weight: 500; font-size: 12px; color: var(--ink-secondary); }
.chart { padding: var(--space-4); }
</style>
