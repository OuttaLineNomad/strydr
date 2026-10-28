<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import Icons from '@/components/ui/Icons.vue'
import StatTile from '@/components/ui/StatTile.vue'
import RouteMap from '@/components/app/RouteMap.vue'
import { useSettingsStore } from '@/stores/settings'
import { useRoutesStore } from '@/stores/routes'
import { distanceUnit, elevationUnit, formatDistance, formatDuration, formatElevation, NOT_AVAILABLE } from '@/lib/units'
import { formatLocalDate } from '@/lib/format'
import type { SectionResult } from '@/api/types'

const props = defineProps<{ routeKey: string }>()
const s = useSettingsStore()
const store = useRoutesStore()
const route = computed(() => store.detail)
const du = computed(() => distanceUnit(s.units))

watch(() => props.routeKey, (k) => store.loadDetail(k), { immediate: true })

const runs = computed(() => route.value?.runs ?? [])

// Comparisons: one run at a time against that run's own earlier, similar-effort runs.
const picked = ref<string>('')
watch(runs, (r) => { if (!picked.value || !r.some((x) => x.workout_id === picked.value)) picked.value = r[0]?.workout_id ?? '' }, { immediate: true })
const sectionsById = computed(() => new Map((route.value?.sections ?? []).map((x) => [x.section_id, x])))
const results = computed(() =>
  (route.value?.results ?? [])
    .filter((r) => r.workout_id === picked.value)
    .sort((a, b) => (sectionsById.value.get(a.section_id)?.index ?? 0) - (sectionsById.value.get(b.section_id)?.index ?? 0)),
)
function secLabel(id: string): string {
  const x = sectionsById.value.get(id)
  return x ? `${x.kind === 'c' ? 'Climb' : 'Split'} ${x.index + 1}` : id
}
function compare(r: SectionResult): string {
  if (r.time_s == null) return NOT_AVAILABLE
  if (!r.comparable || r.gap_s == null) return 'Not enough similar-effort runs yet'
  const g = Math.round(Math.abs(r.gap_s))
  if (g === 0) return 'Same as your usual'
  return `${g} s ${r.gap_s > 0 ? 'slower' : 'faster'} than your usual`
}

// Join / split with a confirmation step. Two runs are picked, then confirmed.
const a = ref('')
const b = ref('')
watch(runs, (r) => { a.value = r[0]?.workout_id ?? ''; b.value = r[1]?.workout_id ?? '' }, { immediate: true })
const pending = ref<'join' | 'split' | null>(null)
const done = ref<{ action: 'join' | 'split'; a: string; b: string } | null>(null)
const canAsk = computed(() => !!a.value && !!b.value && a.value !== b.value)
async function confirm() {
  const action = pending.value
  if (!action || !route.value) return
  pending.value = null
  if (await store.addOverride(action, a.value, b.value)) {
    done.value = { action, a: a.value, b: b.value }
    await store.loadDetail(props.routeKey)
  }
}
async function undo() {
  const d = done.value
  if (d && (await store.removeOverride(d.a, d.b))) {
    done.value = null
    await store.loadDetail(props.routeKey)
  }
}
const label = (id: string) => {
  const r = runs.value.find((x) => x.workout_id === id)
  return r ? `${formatLocalDate(r.local_date)}, ${formatDistance(r.distance_m, s.units)} ${du.value}` : id
}
</script>

<template>
  <Button class="back" small :to="{ name: 'routes' }">Back to routes</Button>

  <p v-if="store.detailLoading" class="page-sub" role="status">Loading your route…</p>
  <template v-else-if="store.detailError">
    <h1 class="page-title">Route not found</h1>
    <p class="page-sub" role="alert">{{ store.detailError }}</p>
  </template>

  <template v-else-if="route">
    <header class="title-row">
      <div>
        <h1 class="page-title">{{ formatDistance(route.distance_m, s.units) }} {{ du }} route</h1>
        <p class="page-sub">{{ route.run_count }} {{ route.run_count === 1 ? 'run' : 'runs' }}, from {{ formatLocalDate(route.first_date) }} to {{ formatLocalDate(route.last_date) }}.</p>
      </div>
    </header>

    <div class="canvas">
    <RouteMap :key="route.route_key" class="s7 stretch" :geometry="route.display_geometry" />

    <GlassPanel class="panel s5" role="group" aria-label="Sections">
      <h3 class="chart-title">Sections</h3>
      <p v-if="!route.sections.length" class="muted" data-testid="sections-na">Sections are not available for this route yet.</p>
      <table v-else class="chart-table" data-testid="sections-table">
        <thead><tr><th scope="col">Section</th><th scope="col">From</th><th scope="col">Length ({{ du }})</th><th scope="col">Gain ({{ elevationUnit(s.units) }})</th></tr></thead>
        <tbody>
          <tr v-for="x in route.sections" :key="x.section_id">
            <th scope="row">{{ x.kind === 'c' ? 'Climb' : 'Split' }} {{ x.index + 1 }}</th>
            <td>{{ formatDistance(x.start_m, s.units, 2) }} {{ du }}</td>
            <td>{{ formatDistance(x.length_m, s.units, 2) }}</td>
            <td>{{ x.gain_m == null ? NOT_AVAILABLE : formatElevation(x.gain_m, s.units) }}</td>
          </tr>
        </tbody>
      </table>
    </GlassPanel>

    <GlassPanel class="panel s6" role="group" aria-label="Section comparisons">
      <h3 class="chart-title">How a run compared</h3>
      <label class="field">
        <span class="row-meta">Run</span>
        <select v-model="picked" class="input" data-testid="compare-run">
          <option v-for="r in runs" :key="r.workout_id" :value="r.workout_id">{{ label(r.workout_id) }}</option>
        </select>
      </label>
      <p class="row-meta">Each section is compared with your earlier runs on this route at a similar heart rate.</p>
      <p v-if="!results.length" class="muted" data-testid="compare-na">No section times are available for this run.</p>
      <table v-else class="chart-table" data-testid="compare-table">
        <thead><tr><th scope="col">Section</th><th scope="col">Time</th><th scope="col">Compared with your usual</th></tr></thead>
        <tbody>
          <tr v-for="r in results" :key="r.section_id">
            <th scope="row">{{ secLabel(r.section_id) }}</th>
            <td>{{ r.time_s == null ? NOT_AVAILABLE : formatDuration(r.time_s) }}</td>
            <td>{{ compare(r) }}</td>
          </tr>
        </tbody>
      </table>
    </GlassPanel>

    <section class="stack s6" aria-labelledby="rt-runs-h">
      <h2 id="rt-runs-h" class="section-title">Runs on this route</h2>
      <GlassPanel v-for="r in runs" :key="r.workout_id" as="div">
        <RouterLink class="row-link" :to="{ name: 'run-detail', params: { id: r.workout_id } }" data-testid="route-run">
          <span>
            <span class="row-title">{{ formatLocalDate(r.local_date) }}</span><br />
            <span class="row-meta">{{ formatDistance(r.distance_m, s.units) }} {{ du }} · {{ formatDuration(r.duration_s) }}</span>
          </span>
          <Icons name="chevron" :size="20" />
        </RouterLink>
      </GlassPanel>
    </section>

    <GlassPanel v-if="runs.length > 1" class="panel s6" role="group" aria-label="Join or split runs">
      <h3 class="chart-title">Fix the grouping</h3>
      <p class="row-meta">If two runs were grouped wrongly, say so here. Join treats them as the same route. Split keeps them apart.</p>
      <label class="field"><span class="row-meta">First run</span>
        <select v-model="a" class="input" data-testid="override-a"><option v-for="r in runs" :key="r.workout_id" :value="r.workout_id">{{ label(r.workout_id) }}</option></select>
      </label>
      <label class="field"><span class="row-meta">Second run</span>
        <select v-model="b" class="input" data-testid="override-b"><option v-for="r in runs" :key="r.workout_id" :value="r.workout_id">{{ label(r.workout_id) }}</option></select>
      </label>
      <div class="actions">
        <Button :disabled="!canAsk || store.overrideBusy" data-testid="ask-join" @click="pending = 'join'">Join these runs</Button>
        <Button :disabled="!canAsk || store.overrideBusy" data-testid="ask-split" @click="pending = 'split'">Split these runs</Button>
      </div>
      <div v-if="pending" class="confirm" role="alertdialog" aria-label="Confirm change" data-testid="override-confirm">
        <p>
          {{ pending === 'join' ? 'Join' : 'Split' }} the runs of {{ label(a) }} and {{ label(b) }}?
          Your routes and section comparisons will be recalculated.
        </p>
        <div class="actions">
          <Button variant="primary" data-testid="confirm-yes" @click="confirm">{{ pending === 'join' ? 'Yes, join them' : 'Yes, split them' }}</Button>
          <Button data-testid="confirm-no" @click="pending = null">Cancel</Button>
        </div>
      </div>
      <p v-if="store.overrideError" class="err" role="alert">{{ store.overrideError }}</p>
      <p v-else-if="done" class="row-meta" role="status" data-testid="override-done">
        Saved. Your routes are being recalculated.
        <button type="button" class="link" data-testid="override-undo" @click="undo">Undo</button>
      </p>
    </GlassPanel>
    </div>
  </template>
</template>

<style scoped>
.head { margin: 0; }
.panel { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.panel h3, .panel p { margin: 0; }
.muted { color: var(--ink-secondary); }
.field { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.input { height: 48px; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink); padding: 0 var(--space-4); font: inherit; min-width: 0; }
.input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.actions { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.confirm { border: 1.5px solid var(--divider); border-radius: var(--radius-md); padding: var(--space-3); display: flex; flex-direction: column; gap: var(--space-3); background: var(--surface-1); }
.link { background: none; border: 0; padding: 0; color: var(--accent-text); font: inherit; font-weight: 600; text-decoration: underline; cursor: pointer; }
.err { color: var(--danger); }
</style>
