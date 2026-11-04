<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import { usePlansStore } from '@/stores/plans'
import { useSettingsStore } from '@/stores/settings'
import { planSummary } from '@/lib/plans'
import { unlockAudio } from '@/lib/useTone'
import { formatClock } from '@/lib/units'
import { bellText, better, measureComparable, effortText, gainLine, headline, roundsFigure, sessionLine, shortDate, type Field } from '@/lib/progress'
import type { PlanProgress } from '@/api/types'

const props = defineProps<{ id: string }>()
const store = usePlansStore()
const settings = useSettingsStore()

const data = ref<PlanProgress | null>(null)
const loading = ref(true)
const failed = ref(false)
const missing = ref(false)
let seq = 0

async function load() {
  const mine = ++seq
  loading.value = true
  failed.value = false
  missing.value = false
  const n = Number(props.id)
  const got = Number.isInteger(n) && n > 0 ? await store.progress(n) : 'missing'
  if (mine !== seq) return
  missing.value = got === 'missing'
  data.value = typeof got === 'object' && got ? got : null
  failed.value = !data.value && !missing.value
  loading.value = false
}
onMounted(load)
watch(() => props.id, load)

const plan = computed(() => data.value?.plan ?? null)
const summary = computed(() => (plan.value ? planSummary(plan.value, settings.units) : ''))
const units = computed(() => settings.units)
const then = computed(() => data.value?.then ?? null)
const now = computed(() => data.value?.now ?? null)
const head = computed(() => (then.value && now.value ? headline(then.value, now.value, units.value) : ''))
const gain = computed(() => (plan.value && then.value && now.value ? gainLine(plan.value, then.value, now.value) : ''))

interface CompareRow { key: string; label: string; a: string | null; b: string | null; win: 'a' | 'b' | null }
const rows = computed<CompareRow[]>(() => {
  const t = then.value
  const n = now.value
  const p = plan.value
  if (!t || !n || !p) return []
  const win = (f: Field) => better(f, t, n)
  const same = measureComparable(p, t, n)
  const hr = (x: number | null) => (x == null ? null : `${Math.round(x)} bpm`)
  const out: CompareRow[] = [
    { key: 'date', label: 'Date', a: shortDate(t.date), b: shortDate(n.date), win: null },
    { key: 'bell', label: 'Bell', a: bellText(t.weight_kg, units.value), b: bellText(n.weight_kg, units.value), win: win('bell') },
  ]
  if (p.format === 'amrap') out.push({ key: 'rounds', label: 'Rounds', a: roundsFigure(t), b: roundsFigure(n), win: same ? win('rounds') : null })
  else if (p.format === 'complex') out.push({ key: 'time', label: 'Time', a: formatClock(t.active_s), b: formatClock(n.active_s), win: same ? win('time') : null })
  else out.push({ key: 'missed', label: 'Missed reps', a: t.missed_reps == null ? null : String(t.missed_reps), b: n.missed_reps == null ? null : String(n.missed_reps), win: win('missed') })
  out.push(
    { key: 'effort', label: 'Effort', a: t.effort == null ? null : effortText(t.effort), b: n.effort == null ? null : effortText(n.effort), win: win('effort') },
    { key: 'hr', label: 'Avg HR', a: hr(t.avg_hr), b: hr(n.avg_hr), win: null },
  )
  return out
})
</script>

<template>
  <Button small to="/workouts" class="back" data-testid="plan-back">Workouts</Button>

  <p v-if="loading" class="body" role="status" data-testid="plan-loading">Loading the workout.</p>

  <GlassPanel v-else-if="missing" class="block" data-testid="plan-missing">
    <h1 class="page-title">This workout no longer exists.</h1>
    <Button variant="primary" to="/workouts" data-testid="plan-missing-back">Back to Workouts</Button>
  </GlassPanel>

  <GlassPanel v-else-if="failed" class="block" role="alert" data-testid="plan-error">
    <h1 class="page-title">The workout did not load</h1>
    <p class="body">Check your connection, then try again.</p>
    <Button @click="load">Retry</Button>
  </GlassPanel>

  <template v-else-if="data && plan">
    <header class="title-row">
      <div class="titles">
        <h1 class="page-title" data-testid="plan-title">{{ plan.name }}</h1>
        <p class="page-sub" data-testid="plan-summary">{{ summary }}</p>
      </div>
      <div class="title-actions">
        <RouterLink :to="`/workouts/${plan.id}/edit`" class="link" data-testid="plan-edit">Edit</RouterLink>
        <Button variant="primary" :to="`/workouts/${plan.id}/run`" data-testid="plan-start" @click="unlockAudio()">Start</Button>
      </div>
    </header>

    <template v-if="then && now">
      <section class="lead" data-testid="progress-lead">
        <p class="headline" data-testid="progress-headline">{{ head }}</p>
        <p class="body" data-testid="progress-gain">{{ gain }}</p>
      </section>

      <GlassPanel class="compare" data-testid="compare">
        <table class="tbl">
          <thead>
            <tr><th scope="col"><span class="sr">Measure</span></th><th scope="col" class="num-col">Then</th><th scope="col" class="num-col">Now</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.key" :data-testid="`cmp-${r.key}`">
              <th scope="row">{{ r.label }}</th>
              <td class="num-col" :class="{ win: r.win === 'a' }" data-col="then"><template v-if="r.a != null">{{ r.a }}</template><span v-else class="dash" role="img" aria-label="not available">—</span><span v-if="r.win === 'a'" class="sr"> (better)</span></td>
              <td class="num-col" :class="{ win: r.win === 'b' }" data-col="now"><template v-if="r.b != null">{{ r.b }}</template><span v-else class="dash" role="img" aria-label="not available">—</span><span v-if="r.win === 'b'" class="sr"> (better)</span></td>
            </tr>
          </tbody>
        </table>
      </GlassPanel>
      <p v-if="then.changed" class="body changed" data-testid="progress-changed">This workout has changed since then.</p>
    </template>

    <GlassPanel v-else class="block" data-testid="progress-empty">
      <p class="body">Do it once more to see progress.</p>
    </GlassPanel>

    <section v-if="data.sessions.length" class="sessions" aria-labelledby="sessions-h">
      <h2 id="sessions-h" class="section-title">Sessions</h2>
      <GlassPanel class="list-panel">
        <ul class="rows">
          <li v-for="x in data.sessions" :key="x.id" class="srow">
            <RouterLink :to="`/workouts/sessions/${x.id}`" class="srow-link" data-testid="session-row">
              <span class="srow-title">{{ new Date(x.date).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }) }}</span>
              <span class="body">{{ sessionLine(x, plan, units) }}</span>
            </RouterLink>
          </li>
        </ul>
      </GlassPanel>
    </section>
  </template>
</template>

<style scoped>
.back { margin-bottom: var(--space-3); min-height: 44px; }
.body { margin: 0; color: var(--ink); font-size: var(--body-md-size, 16px); }
.block { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); margin-bottom: var(--space-4); }
.block h1, .block p { margin: 0; }
.titles { min-width: 0; }
.title-actions { display: flex; align-items: center; gap: var(--space-4); flex-shrink: 0; }
.link { color: var(--accent-text); font-weight: 600; min-height: 44px; display: inline-flex; align-items: center; }
.link:focus-visible, .srow-link:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.lead { margin: var(--space-4) 0; display: flex; flex-direction: column; gap: var(--space-2); }
.headline { margin: 0; font-family: var(--font-display); font-weight: 700; font-size: 22px; line-height: 30px; overflow-wrap: anywhere; }
.compare { padding: var(--space-4) var(--space-5); margin-bottom: var(--space-3); }
.tbl { width: 100%; border-collapse: collapse; font-size: var(--body-md-size, 16px); }
.tbl th, .tbl td { padding: var(--space-2) 0; text-align: left; font-weight: 400; border-top: 1px solid var(--divider); }
.tbl thead th { border-top: 0; font-weight: 600; }
.tbl .num-col { text-align: right; font-variant-numeric: tabular-nums; font-family: var(--font-display); }
.tbl td.win { font-weight: 600; }
.dash { color: var(--ink-secondary); }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.changed { margin-bottom: var(--space-3); }
.sessions { margin-top: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.section-title { margin: 0; font-family: var(--font-display); font-size: 20px; line-height: 26px; font-weight: 700; }
.list-panel { padding: 0; overflow: hidden; }
.rows { list-style: none; margin: 0; padding: 0; }
.srow + .srow { border-top: 1px solid var(--divider); }
.srow-link { display: flex; flex-direction: column; gap: 4px; padding: var(--space-4) var(--space-5); min-height: 44px; color: var(--ink); text-decoration: none; }
.srow-title { font-family: var(--font-display); font-size: 18px; line-height: 24px; font-weight: 700; }
</style>
