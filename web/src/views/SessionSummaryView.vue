<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import { useSessionsStore } from '@/stores/sessions'
import { useSettingsStore } from '@/stores/settings'
import { planWeight } from '@/lib/plans'
import { formatClock, weightUnit } from '@/lib/units'
import { roundsText } from '@/lib/workoutEngine'
import type { SessionSummary } from '@/api/types'

const props = defineProps<{ id: string }>()
const store = useSessionsStore()
const settings = useSettingsStore()

const sm = ref<SessionSummary | null>(null)
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
  const got = Number.isInteger(n) && n > 0 ? await store.summary(n) : 'missing'
  if (mine !== seq) return // a newer load (another id, or Retry) owns the page now
  missing.value = got === 'missing'
  sm.value = typeof got === 'object' && got ? got : null
  failed.value = !sm.value
  loading.value = false
}
onMounted(load)
watch(() => props.id, load)

const session = computed(() => sm.value?.session ?? null)
const title = computed(() => session.value?.plan.name ?? '')
const sub = computed(() => {
  const s = session.value
  if (!s) return ''
  const date = new Date(s.start_utc).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
  const p = s.plan
  const fmt = p.format === 'amrap' ? `AMRAP · ${p.cap_min} min` : p.format === 'emom' ? `EMOM · ${p.emom_min} min` : `Complex · ${p.rounds} ${p.rounds === 1 ? 'round' : 'rounds'}`
  return `${date} · ${fmt}`
})
const rounds = computed(() => (session.value ? roundsText(session.value.rounds_done, session.value.partial_moves) : ''))
const bell = computed(() => {
  const kg = session.value?.weight_kg
  return kg == null ? 'Bodyweight' : `${planWeight(kg, settings.units)} ${weightUnit(settings.units)}`
})
const overtime = computed(() => (session.value && session.value.plan.format === 'amrap' && session.value.overtime_s > 0 ? formatClock(session.value.overtime_s) : null))
const avgHr = computed(() => (sm.value?.avg_hr != null ? `${Math.round(sm.value.avg_hr)} bpm` : null))
const effortText = computed(() => {
  const e = sm.value?.effort
  return e == null ? null : `${Number(e.toFixed(1))} / 10`
})
const fromWatch = computed(() => sm.value?.effort_source === 'watch' && !sm.value.effort_estimated)
const estimated = computed(() => sm.value?.effort_source === 'watch' && sm.value.effort_estimated)

// --- Effort picker (only when the watch gave none) ---
const effortError = ref(false)
async function chooseEffort(n: number) {
  if (!sm.value || fromWatch.value) return
  effortError.value = false
  const prev = { effort: sm.value.effort, source: sm.value.effort_source, estimated: sm.value.effort_estimated }
  sm.value = { ...sm.value, effort: n, effort_source: 'manual', effort_estimated: false }
  if (!(await store.setEffort(sm.value.session.id, n))) {
    effortError.value = true
    if (sm.value) sm.value = { ...sm.value, effort: prev.effort, effort_source: prev.source, effort_estimated: prev.estimated }
  }
}

// --- Heart rate per move ---
const maxMoveHr = computed(() => Math.max(1, ...(sm.value?.moves ?? []).map((m) => m.avg_hr)))

// --- Zones ---
const zones = computed(() => {
  const z = sm.value?.zone_seconds
  if (!z) return null
  const total = z.reduce((a, b) => a + b, 0)
  if (total <= 0) return null
  const b = sm.value?.zone_bounds_bpm ?? []
  const range = (i: number): string | null => {
    const lo = i > 0 ? b[i - 1] : undefined
    const hi = b[i]
    if (lo != null && hi != null) return `${Math.round(lo)}–${Math.round(hi)} bpm`
    if (hi != null) return `up to ${Math.round(hi)} bpm`
    if (lo != null) return `over ${Math.round(lo)} bpm`
    return null
  }
  return z.map((sec, i) => ({ zone: i + 1, sec, pct: (sec / total) * 100, range: range(i) }))
})

// --- EMOM fell short ---
const otherText = ref<Record<number, string | number>>({})
const shortError = ref(false)
function choices(target: number | null): number[] {
  if (target == null) return []
  return [1, 2, 3, 4, 5].map((d) => target - d).filter((v) => v >= 0)
}
const otherError = ref<Record<number, boolean>>({})
/** Saves the answer; the chosen answer tapped again takes it back (null). */
async function answer(minute: number, reps: number | null): Promise<boolean> {
  if (!sm.value) return false
  shortError.value = false
  const ok = await store.setShort(sm.value.session.id, minute, reps)
  if (!ok) {
    shortError.value = true
    return false
  }
  if (sm.value) sm.value = { ...sm.value, fell_short: sm.value.fell_short.map((r) => (r.minute === minute ? { ...r, short_reps: reps } : r)) }
  return true
}
function choose(minute: number, v: number, current: number | null) {
  void answer(minute, current === v ? null : v)
}
async function saveOther(minute: number) {
  const raw = String(otherText.value[minute] ?? '').trim()
  const n = Number(raw)
  if (raw === '' || !Number.isInteger(n) || n < 0 || n > 500) {
    otherError.value = { ...otherError.value, [minute]: true }
    return
  }
  otherError.value = { ...otherError.value, [minute]: false }
  if (await answer(minute, n)) otherText.value = { ...otherText.value, [minute]: '' }
}

const again = computed(() => {
  const s = session.value
  if (!s || s.plan_id == null) return null
  return { path: `/workouts/${s.plan_id}/run`, query: s.weight_kg != null ? { weight: String(s.weight_kg) } : {} }
})
</script>

<template>
  <Button small to="/workouts" class="back" data-testid="summary-back">Workouts</Button>

  <p v-if="loading" class="body" role="status" data-testid="summary-loading">Loading the summary.</p>

  <GlassPanel v-else-if="missing" class="block" data-testid="summary-missing">
    <h1 class="page-title">This session no longer exists.</h1>
    <Button variant="primary" to="/workouts" data-testid="summary-missing-back">Back to Workouts</Button>
  </GlassPanel>

  <GlassPanel v-else-if="failed" class="block" role="alert" data-testid="summary-error">
    <h1 class="page-title">The summary did not load</h1>
    <p class="body">Check your connection, then try again.</p>
    <Button @click="load">Retry</Button>
  </GlassPanel>

  <template v-else-if="sm && session">
    <header class="head">
      <h1 class="page-title" data-testid="summary-title">{{ title }}</h1>
      <p class="page-sub" data-testid="summary-sub">{{ sub }}</p>
    </header>

    <dl class="figures" data-testid="summary-figures">
      <div><dt>Rounds</dt><dd data-testid="fig-rounds">{{ rounds }}</dd></div>
      <div><dt>Active time</dt><dd data-testid="fig-time">{{ formatClock(session.active_s) }}</dd></div>
      <div v-if="overtime"><dt>Overtime</dt><dd data-testid="fig-overtime">+{{ overtime }}</dd></div>
      <div><dt>Bell</dt><dd data-testid="fig-bell">{{ bell }}</dd></div>
      <div>
        <dt>Avg HR</dt>
        <dd data-testid="fig-hr"><template v-if="avgHr">{{ avgHr }}</template><span v-else class="dash" role="img" aria-label="not available">—</span></dd>
      </div>
      <div>
        <dt>Effort</dt>
        <dd data-testid="fig-effort">
          <template v-if="effortText">{{ effortText }}</template>
          <span v-else class="dash" role="img" aria-label="not available">—</span>
        </dd>
        <dd v-if="fromWatch" class="note" data-testid="effort-source">from your watch</dd>
        <dd v-else-if="estimated" class="note" data-testid="effort-source">estimated by your watch</dd>
      </div>
    </dl>

    <GlassPanel v-if="!fromWatch" class="block" data-testid="effort-picker">
      <h2 class="section-title" id="effort-h">How hard did it feel?</h2>
      <p class="body">One tap, 1 is easy and 10 is all out. Pick again to change it.</p>
      <div class="effort" role="group" aria-labelledby="effort-h">
        <button
          v-for="n in 10" :key="n" type="button" class="num" :class="{ on: sm.effort === n }" :aria-pressed="sm.effort === n"
          :data-testid="`effort-${n}`" @click="chooseEffort(n)"
        >{{ n }}</button>
      </div>
      <p v-if="effortError" class="err" role="alert" data-testid="effort-error">Effort was not saved. Try again.</p>
    </GlassPanel>

    <GlassPanel v-if="sm.fell_short.length" class="block" data-testid="short-block">
      <h2 class="section-title">Minutes that fell short</h2>
      <p class="body">Optional. Tap how many you got, or skip it.</p>
      <ul class="shorts">
        <li v-for="r in sm.fell_short" :key="r.minute" class="short" data-testid="short-row">
          <p class="short-head">
            <span>Minute {{ r.minute }} · {{ r.move }}<template v-if="r.target_reps != null"> × {{ r.target_reps }}</template></span>
            <span class="short-state" :data-testid="`short-state-${r.minute}`">{{ r.short_reps != null ? `Did ${r.short_reps}` : 'fell short' }}</span>
          </p>
          <div class="choices">
            <button
              v-for="v in choices(r.target_reps)" :key="v" type="button" class="num" :class="{ on: r.short_reps === v }"
              :aria-pressed="r.short_reps === v" :aria-label="`${v} reps in minute ${r.minute}`" :data-testid="`short-${r.minute}-${v}`"
              @click="choose(r.minute, v, r.short_reps)"
            >{{ v }}</button>
          </div>
          <div class="other">
            <label :for="`other-${r.minute}`" class="other-label">Other</label>
            <input
              :id="`other-${r.minute}`" v-model="otherText[r.minute]" type="number" inputmode="numeric" min="0" max="500" class="field"
              :data-testid="`short-other-${r.minute}`" @keydown.enter="saveOther(r.minute)"
            />
            <Button :data-testid="`short-other-save-${r.minute}`" @click="saveOther(r.minute)">Save</Button>
          </div>
          <p v-if="otherError[r.minute]" class="err" role="alert" :data-testid="`short-other-error-${r.minute}`">Enter a whole number from 0 to 500.</p>
        </li>
      </ul>
      <p v-if="shortError" class="err" role="alert" data-testid="short-error">That answer was not saved. Try again.</p>
    </GlassPanel>

    <GlassPanel v-if="sm.moves.length" class="block" data-testid="hr-moves">
      <h2 class="section-title">Heart rate per move</h2>
      <ul class="bars">
        <li v-for="m in sm.moves" :key="m.name" class="bar-row" data-testid="move-bar">
          <span class="bar-name">{{ m.name }}</span>
          <span class="bar-track"><span class="bar-fill" :style="{ width: `${(m.avg_hr / maxMoveHr) * 100}%` }" /></span>
          <span class="bar-value">{{ Math.round(m.avg_hr) }} bpm</span>
        </li>
      </ul>
    </GlassPanel>

    <GlassPanel v-if="zones" class="block" data-testid="zones">
      <h2 class="section-title">Time in zones</h2>
      <div class="stack" role="img" :aria-label="`Time in heart rate zones: ${zones.map((z) => `zone ${z.zone} ${Math.round(z.pct)} percent`).join(', ')}`">
        <span v-for="z in zones" :key="z.zone" class="seg" :class="`z${z.zone}`" :style="{ width: `${z.pct}%` }" />
      </div>
      <table class="tbl">
        <thead><tr><th scope="col">Zone</th><th scope="col" class="num-col">Time</th><th scope="col" class="num-col">Share</th></tr></thead>
        <tbody>
          <tr v-for="z in zones" :key="z.zone" data-testid="zone-row">
            <th scope="row"><span class="key" :class="`z${z.zone}`" />Zone {{ z.zone }}<template v-if="z.range"> · {{ z.range }}</template></th>
            <td class="num-col">{{ formatClock(z.sec) }}</td>
            <td class="num-col">{{ Math.round(z.pct) }}%</td>
          </tr>
        </tbody>
      </table>
    </GlassPanel>

    <GlassPanel v-if="sm.rounds.length" class="block" data-testid="rounds">
      <h2 class="section-title">Rounds</h2>
      <table class="tbl">
        <thead><tr><th scope="col">Round</th><th scope="col" class="num-col">Time</th><th scope="col" class="num-col">Avg HR</th></tr></thead>
        <tbody>
          <tr v-for="r in sm.rounds" :key="r.round" data-testid="round-row">
            <th scope="row">{{ r.round }}</th>
            <td class="num-col">{{ formatClock(r.time_s) }}</td>
            <td class="num-col"><template v-if="r.avg_hr != null">{{ Math.round(r.avg_hr) }}</template><span v-else class="dash" role="img" aria-label="not available">—</span></td>
          </tr>
        </tbody>
      </table>
    </GlassPanel>

    <div v-if="again" class="again">
      <Button variant="primary" :to="again" data-testid="do-again">Do it again</Button>
    </div>
  </template>
</template>

<style scoped>
.back { margin-bottom: var(--space-3); min-height: 44px; }
.body { margin: 0; color: var(--ink); font-size: var(--body-md-size, 16px); }
.head { margin-bottom: var(--space-4); }
.block { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); margin-bottom: var(--space-4); }
.block h1, .block h2, .block p { margin: 0; }
.section-title { font-family: var(--font-display); font-size: 20px; line-height: 26px; font-weight: 700; }
.err { color: var(--danger); }
.dash { color: var(--ink-secondary); }

.figures { margin: 0 0 var(--space-5); display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4) var(--space-5); }
.figures dt { color: var(--ink); font-size: var(--body-md-size, 16px); }
.figures dd { margin: 0; font-family: var(--font-display); font-weight: 700; font-variant-numeric: tabular-nums; font-size: 28px; line-height: 34px; overflow-wrap: anywhere; }
.figures dd.note { font-family: inherit; font-weight: 400; font-size: var(--body-md-size, 16px); line-height: 22px; color: var(--ink); }

.effort, .choices { display: grid; grid-template-columns: repeat(5, 1fr); gap: var(--space-2); }
.num {
  min-height: 48px; min-width: 44px; border: 1px solid var(--divider); border-radius: var(--radius-md, 12px); background: transparent; color: var(--ink);
  font-family: var(--font-display); font-weight: 700; font-size: 20px; font-variant-numeric: tabular-nums; cursor: pointer;
}
.num.on { background: var(--accent); border-color: var(--accent); color: var(--ink-on-accent); }
.num:focus-visible, .field:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }

.shorts { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.short { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3) 0; }
.short + .short { border-top: 1px solid var(--divider); }
.short-head { display: flex; justify-content: space-between; gap: var(--space-3); font-weight: 600; }
.short-state { font-variant-numeric: tabular-nums; white-space: nowrap; }
.other { display: flex; gap: var(--space-2); align-items: center; }
.other-label { font-size: var(--body-md-size, 16px); }
.field { height: 48px; width: 96px; padding: 0 var(--space-3); border: 1px solid var(--divider); border-radius: var(--radius-md, 12px); background: transparent; color: var(--ink); font: inherit; font-variant-numeric: tabular-nums; }

.bars { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-3); }
.bar-row { display: grid; grid-template-columns: minmax(80px, 1fr) 2fr auto; gap: var(--space-3); align-items: center; }
.bar-name { overflow-wrap: anywhere; }
.bar-track { height: 16px; border-radius: 8px; background: var(--chart-other); opacity: .35; position: relative; display: block; }
.bar-fill { position: absolute; inset: 0 auto 0 0; border-radius: 8px; background: var(--chart-heart-rate); display: block; }
.bar-value { font-family: var(--font-display); font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }

.stack { display: flex; height: 24px; border-radius: 12px; overflow: hidden; }
.seg, .key { background: var(--chart-heart-rate); }
.z1 { opacity: .2; } .z2 { opacity: .4; } .z3 { opacity: .6; } .z4 { opacity: .8; } .z5 { opacity: 1; }
.key { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: var(--space-2); vertical-align: middle; }

.tbl { width: 100%; border-collapse: collapse; font-size: var(--body-md-size, 16px); }
.tbl th, .tbl td { padding: var(--space-2) 0; text-align: left; font-weight: 400; border-top: 1px solid var(--divider); }
.tbl thead th { border-top: 0; font-weight: 600; }
.tbl .num-col { text-align: right; font-variant-numeric: tabular-nums; }
.tbl tbody td.num-col { font-family: var(--font-display); font-weight: 600; }

.again { margin: var(--space-5) 0 var(--space-6); }
.again :deep(.btn) { width: 100%; min-height: 52px; }
</style>
