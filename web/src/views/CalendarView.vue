<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import StatTile, { type Trend } from '@/components/ui/StatTile.vue'
import Icons from '@/components/ui/Icons.vue'
import Button from '@/components/ui/Button.vue'
import { vPress } from '@/directives/press'
import { api } from '@/api'
import type { CalendarDay, CalendarOut } from '@/api/types'
import { useSettingsStore } from '@/stores/settings'
import { distanceUnit, distanceValue, formatDistance, formatDuration } from '@/lib/units'
import { typeLabel } from '@/lib/format'

// The training log: one month as whole weeks. Each day shows a dot sized by distance
// (runs in the accent, walks and hikes quieter), a ring on hard days, and a week total
// at the end of each row. The month is compared with the one before, as context only.
const s = useSettingsStore()
const route = useRoute()
const router = useRouter()
const data = ref<CalendarOut | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const month = computed(() => (typeof route.query.month === 'string' && /^\d{4}-\d{2}$/.test(route.query.month) ? route.query.month : null))
async function load(m: string | null) {
  loading.value = true
  error.value = null
  try {
    const { data: d } = await api.GET('/api/v1/calendar', { params: { query: m ? { month: m } : {} } })
    if (d) data.value = d
    else error.value = 'Your calendar could not load. Try again in a moment.'
  } catch {
    error.value = 'Your calendar could not load. Check your connection and try again.'
  } finally {
    loading.value = false
  }
}
watch(month, load, { immediate: true })

function shift(m: string, by: number): string {
  const [y, mo] = m.split('-').map(Number) as [number, number]
  const d = new Date(Date.UTC(y, mo - 1 + by, 1))
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
}
const go = (by: number) => data.value && router.push({ name: 'calendar', query: { month: shift(data.value.month, by) } })
const monthLabel = (m: string) => {
  const [y, mo] = m.split('-').map(Number) as [number, number]
  return new Date(Date.UTC(y, mo - 1, 1)).toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}
const isCurrent = computed(() => !!data.value?.as_of && data.value.as_of.startsWith(data.value.month))
const canGoForward = computed(() => !!data.value?.as_of && data.value.month < data.value.as_of.slice(0, 7))

const du = computed(() => distanceUnit(s.units))
const weeks = computed(() => {
  const days = data.value?.days ?? []
  const out: { days: CalendarDay[]; runM: number }[] = []
  for (let i = 0; i < days.length; i += 7) {
    const w = days.slice(i, i + 7)
    out.push({ days: w, runM: w.flatMap((d) => d.workouts).filter((x) => x.type === 'run').reduce((a, x) => a + (x.distance_m ?? 0), 0) })
  }
  return out
})
const maxM = computed(() => Math.max(1, ...(data.value?.days ?? []).map((d) => d.workouts.reduce((a, x) => a + (x.distance_m ?? 0), 0))))

function dot(d: CalendarDay) {
  const m = d.workouts.reduce((a, x) => a + (x.distance_m ?? 0), 0)
  if (!d.workouts.length) return null
  const run = d.workouts.some((x) => x.type === 'run')
  // Area tracks distance, with a floor so a short walk still reads.
  return { size: Math.round(14 + 26 * Math.sqrt(m / maxM.value)), run }
}
function dayLabel(d: CalendarDay): string {
  const date = new Date(`${d.local_date}T00:00:00Z`).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' })
  if (!d.workouts.length) return `${date}: ${d.kind === 'rest' ? 'rest day' : 'nothing logged'}`
  const parts = d.workouts.map((x) => `${typeLabel(x.type).toLowerCase()} ${x.distance_m ? `${formatDistance(x.distance_m, s.units, 1)} ${du.value}` : ''}`.trim())
  return `${date}: ${parts.join(', ')}${d.is_hard ? ', hard day' : ''}`
}
function dayTo(d: CalendarDay) {
  if (d.workouts.length === 1) return { name: 'run-detail', params: { id: d.workouts[0]!.workout_id } }
  return null
}
const dayNum = (d: CalendarDay) => Number(d.local_date.slice(8))
const dayDist = (d: CalendarDay) => {
  const m = d.workouts.reduce((a, x) => a + (x.distance_m ?? 0), 0)
  return m ? formatDistance(m, s.units) : null
}

const trend = computed<Trend | undefined>(() => {
  const c = data.value
  if (!c || !c.previous.run_count) return undefined
  const diff = distanceValue(c.totals.distance_m - c.previous.distance_m, s.units)
  const dir = Math.abs(diff) < 0.05 ? 'flat' : diff > 0 ? 'up' : 'down'
  return { direction: dir, text: `${diff > 0 ? '+' : ''}${diff.toFixed(1)} ${du.value} vs ${monthLabel(c.previous.month).split(' ')[0]}${isCurrent.value ? ' so far' : ''}`, good: diff >= 0 }
})
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
</script>

<template>
  <header class="title-row">
    <div>
      <h1 class="page-title">Calendar</h1>
      <p class="page-sub">Every day of the month at a glance. Bigger dots are longer days.</p>
    </div>
    <nav v-if="data" class="month-nav" aria-label="Month">
      <Button small icon label="Previous month" data-testid="cal-prev" @click="go(-1)"><Icons name="chevron" :size="16" class="flip" /></Button>
      <span class="month" aria-live="polite" data-testid="cal-month">{{ monthLabel(data.month) }}</span>
      <Button small icon label="Next month" :disabled="!canGoForward" data-testid="cal-next" @click="go(1)"><Icons name="chevron" :size="16" /></Button>
    </nav>
  </header>

  <p v-if="error" class="err" role="alert">{{ error }}</p>

  <template v-if="data">
    <div class="canvas tiles" :aria-busy="loading">
      <StatTile class="s3" :label="isCurrent ? 'Distance so far' : 'Distance'" :value="formatDistance(data.totals.distance_m, s.units)" :unit="du" :trend="trend" />
      <StatTile class="s3" label="Runs" :value="String(data.totals.run_count)" :sub="data.totals.duration_s ? formatDuration(data.totals.duration_s) + ' running' : null" />
      <StatTile class="s3" label="Active days" :value="String(data.active_days)" :sub="data.rest_days ? `${data.rest_days} rest days` : null" />
      <StatTile class="s3" label="Longest run" :value="data.longest_run_m == null ? null : formatDistance(data.longest_run_m, s.units)" :unit="du" />
    </div>

    <GlassPanel class="cal" role="group" :aria-label="`Calendar for ${monthLabel(data.month)}`" data-testid="calendar">
      <div class="grid head-row" aria-hidden="true">
        <span v-for="w in WEEKDAYS" :key="w" class="wd">{{ w }}</span>
        <span class="wd wk">Week</span>
      </div>
      <ol class="weeks">
        <li v-for="(wk, i) in weeks" :key="i" class="grid">
          <template v-for="d in wk.days" :key="d.local_date">
            <component
              :is="dayTo(d) ? RouterLink : 'div'"
              v-press="!!dayTo(d)"
              :to="dayTo(d) ?? undefined"
              class="day"
              :class="{ out: !d.in_month, today: d.local_date === data.as_of, rest: d.kind === 'rest', link: !!dayTo(d) }"
              :aria-label="dayLabel(d)"
              :data-testid="`cal-day-${d.local_date}`"
            >
              <span class="num">{{ dayNum(d) }}</span>
              <span v-if="dot(d)" class="dot-wrap">
                <span class="dot" :class="{ 'dot--run': dot(d)!.run, hard: d.is_hard }" :style="{ width: `${dot(d)!.size}px`, height: `${dot(d)!.size}px` }" />
              </span>
              <span v-if="d.workouts.length > 1" class="multi">{{ d.workouts.length }}</span>
              <span v-if="dayDist(d)" class="dist mono" aria-hidden="true">{{ dayDist(d) }}</span>
            </component>
          </template>
          <span class="wk-total mono" :aria-label="`Week total ${formatDistance(wk.runM, s.units)} ${du} of running`">
            <template v-if="wk.runM">{{ formatDistance(wk.runM, s.units) }}<small>{{ du }}</small></template>
            <template v-else>–</template>
          </span>
        </li>
      </ol>
      <ul class="legend" aria-label="Legend">
        <li><i class="dot dot--run" /> Run</li>
        <li><i class="dot" /> Walk or hike</li>
        <li><i class="dot dot--run hard" /> Hard day</li>
      </ul>
    </GlassPanel>
  </template>
</template>

<style scoped>
.month-nav { display: flex; align-items: center; gap: var(--space-2); }
.month { min-width: 150px; text-align: center; font-family: var(--font-display); font-weight: 700; font-size: 17px; }
.flip { transform: rotate(180deg); }
.err { margin: 0; color: var(--danger); }
.tiles { margin-bottom: var(--space-2); }
@media (max-width: 1079px) { .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.cal { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-2); }
@media (min-width: 1080px) { .cal { padding: var(--space-6); } }
.grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)) minmax(52px, 0.9fr); gap: 4px; }
@media (min-width: 1080px) { .grid { gap: var(--space-2); } }
.weeks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
@media (min-width: 1080px) { .weeks { gap: var(--space-2); } }
.wd { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-muted); text-align: center; padding-bottom: var(--space-1); }
.wk { text-align: right; }
.day {
  position: relative; aspect-ratio: 1 / 1; min-height: 44px; border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--surface-2) 55%, transparent); color: var(--ink); text-decoration: none;
  display: grid; place-items: center;
  transition: transform var(--dur-release) var(--ease-glass), background var(--dur-release) var(--ease-settle);
}
@media (min-width: 1080px) { .day { aspect-ratio: auto; height: 92px; } }
.day.link:hover { background: color-mix(in srgb, var(--accent) 10%, var(--surface-2)); }
.day.link:active { transform: scale(.95); }
.day:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.day.out { opacity: .38; }
.day.today { box-shadow: inset 0 0 0 2px var(--accent); }
.num { position: absolute; top: 6px; left: 8px; font-size: 12px; font-weight: 600; color: var(--ink-secondary); font-variant-numeric: tabular-nums; }
.dot-wrap { display: grid; place-items: center; }
.dot { display: inline-block; border-radius: 50%; background: color-mix(in srgb, var(--chart-elevation) 70%, transparent); animation: pop .5s var(--ease-glass) both; }
.dot--run { background: var(--accent); }
.dot.hard { box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 30%, transparent); }
@media (max-width: 1079px) { .dot-wrap .dot { transform: scale(.72); animation: none; } }
.dist { display: none; position: absolute; bottom: 6px; right: 8px; font-size: 11px; font-weight: 600; color: var(--ink-secondary); }
@media (min-width: 1080px) { .dist { display: block; } .multi { bottom: auto; top: 6px; } }
.multi { position: absolute; bottom: 5px; right: 7px; font-size: 11px; font-weight: 700; color: var(--ink-secondary); }
.wk-total { align-self: center; text-align: right; font-size: 14px; font-weight: 600; color: var(--ink); white-space: nowrap; }
.wk-total small { font-size: 11px; margin-left: 2px; color: var(--ink-secondary); }
.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.legend { list-style: none; margin: var(--space-2) 0 0; padding: 0; display: flex; gap: var(--space-4); flex-wrap: wrap; font-size: var(--body-sm-size); color: var(--ink-secondary); }
.legend li { display: inline-flex; align-items: center; gap: 6px; }
.legend .dot { width: 12px; height: 12px; animation: none; }
@keyframes pop { from { transform: scale(0); } }
@media (prefers-reduced-motion: reduce) { .dot { animation: none; } }
</style>
