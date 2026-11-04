<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import { useOrphansStore } from '@/stores/orphans'
import { usePlansStore } from '@/stores/plans'
import { useSettingsStore } from '@/stores/settings'
import { planWeight } from '@/lib/plans'
import { displayToKg, weightUnit } from '@/lib/units'
import { roundsText } from '@/lib/workoutEngine'

// A watch strength workout with no session: one question at a time, a guess from history, one tap to log it.
const store = useOrphansStore()
const plansStore = usePlansStore()
const settings = useSettingsStore()
onMounted(() => {
  store.load()
  if (!plansStore.loaded) plansStore.load()
})

const o = computed(() => store.current)
const g = computed(() => o.value?.guess ?? null)
const unit = computed(() => weightUnit(settings.units))
const other = ref(false)
const planId = ref<number | null>(null)
const weight = ref('')
const rounds = ref(0)
const formError = ref('')
const plans = computed(() => [...plansStore.plans].sort((a, b) => a.name.localeCompare(b.name)))

watch(() => o.value?.workout_id, () => {
  other.value = false
  formError.value = ''
})

function when(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}
function localDate(day: string): Date {
  const [y = 1970, m = 1, d = 1] = day.split('-').map(Number)
  return new Date(y, m - 1, d)
}
const sentence = computed(() => {
  if (!o.value) return ''
  const x = g.value
  if (!x) return `Your watch logged a strength workout on ${when(o.value.start_utc)}${o.value.duration_s ? ` (${Math.round(o.value.duration_s / 60)} min)` : ''}.`
  const lead = x.same_weekday ? `Same as last ${localDate(x.session_date).toLocaleDateString(undefined, { weekday: 'long' })}` : 'Same as last time'
  const bell = x.weight_kg == null ? 'bodyweight' : `${planWeight(x.weight_kg, settings.units)} ${unit.value}`
  return `${lead}: ${x.plan_name}, ${bell}, ${roundsText(x.rounds_done, x.partial_moves)}?`
})
const title = computed(() => (g.value ? `Log your ${when(o.value!.start_utc)} watch workout?` : 'Log this watch workout?'))

function openOther() {
  const x = g.value
  planId.value = x?.plan_id ?? plans.value[0]?.id ?? null
  weight.value = x?.weight_kg != null ? planWeight(x.weight_kg, settings.units) : ''
  rounds.value = x?.rounds_done ?? 0
  formError.value = ''
  other.value = true
}
function pickPlan() {
  const p = plansStore.plans.find((x) => x.id === planId.value)
  const w = p?.moves.map((m) => m.weight_kg).find((k): k is number => k != null)
  weight.value = w != null ? planWeight(w, settings.units) : ''
}
function step(d: 1 | -1) {
  rounds.value = Math.min(1000, Math.max(0, rounds.value + d))
}

async function yes() {
  const x = g.value
  if (!o.value || !x) return
  await store.log(o.value.workout_id, { plan_id: x.plan_id, weight_kg: x.weight_kg, rounds_done: x.rounds_done, partial_moves: x.partial_moves }, x.plan_name)
}
async function submitOther() {
  if (!o.value || planId.value == null) return
  let kg: number | null = null
  if (weight.value.trim() !== '') {
    const v = Number(weight.value)
    kg = Number.isFinite(v) ? displayToKg(v, settings.units) : NaN
    if (!(kg >= 0.5 && kg <= 300)) {
      formError.value = `Bell is a number from ${planWeight(0.5, settings.units)} to ${planWeight(300, settings.units)} ${unit.value}, or blank for bodyweight.`
      return
    }
  }
  formError.value = ''
  const name = plansStore.plans.find((p) => p.id === planId.value)?.name ?? ''
  await store.log(o.value.workout_id, { plan_id: planId.value, weight_kg: kg, rounds_done: rounds.value, partial_moves: 0 }, name)
}
async function no() {
  if (o.value) await store.dismiss(o.value.workout_id)
}
</script>

<template>
  <div v-if="o || store.logged" class="orphan">
    <GlassPanel v-if="o" class="panel" role="group" aria-labelledby="orphan-h" data-testid="orphan">
      <h2 id="orphan-h" class="title" data-testid="orphan-title">{{ title }}</h2>
      <p class="sentence" data-testid="orphan-sentence">{{ sentence }}</p>
      <div v-if="!other" class="actions">
        <Button v-if="g" variant="primary" :disabled="store.busy" data-testid="orphan-yes" @click="yes">Yes, log it</Button>
        <Button :variant="g ? 'glass' : 'primary'" :disabled="store.busy || !plans.length" data-testid="orphan-other" @click="openOther">Something else</Button>
        <Button :disabled="store.busy" data-testid="orphan-no" @click="no">Not a Strydr workout</Button>
      </div>
      <form v-else class="form" data-testid="orphan-form" @submit.prevent="submitOther">
        <label class="field">Workout
          <select v-model.number="planId" data-testid="orphan-plan" @change="pickPlan">
            <option v-for="p in plans" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <label class="field">Bell ({{ unit }}), blank for bodyweight
          <input v-model="weight" inputmode="decimal" data-testid="orphan-weight" />
        </label>
        <div class="field" role="group" aria-label="Rounds">
          <span>Rounds</span>
          <div class="stepper">
            <Button icon label="Fewer rounds" :disabled="rounds <= 0" data-testid="orphan-minus" @click="step(-1)">−</Button>
            <span class="count" data-testid="orphan-rounds">{{ rounds }}</span>
            <Button icon label="More rounds" data-testid="orphan-plus" @click="step(1)">+</Button>
          </div>
        </div>
        <p v-if="formError" class="err" role="alert" data-testid="orphan-form-error">{{ formError }}</p>
        <div class="actions">
          <Button variant="primary" type="submit" :disabled="store.busy" data-testid="orphan-log">Log</Button>
          <Button :disabled="store.busy" data-testid="orphan-cancel" @click="other = false">Cancel</Button>
        </div>
      </form>
      <p v-if="store.error" class="err" role="alert" data-testid="orphan-error">{{ store.error }}</p>
    </GlassPanel>
    <p v-if="store.logged" class="done" role="status" data-testid="orphan-logged">
      Logged {{ store.logged.plan }}.
      <RouterLink :to="`/workouts/sessions/${store.logged.id}`" class="link" data-testid="orphan-summary-link">See the summary</RouterLink>
    </p>
  </div>
</template>

<style scoped>
.orphan { display: flex; flex-direction: column; gap: var(--space-3); }
.panel { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.title { margin: 0; font-family: var(--font-display); font-size: 20px; line-height: 26px; font-weight: 700; }
.sentence { margin: 0; color: var(--ink); font-size: 16px; }
.actions { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-3); align-items: center; }
.form { display: flex; flex-direction: column; gap: var(--space-3); }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 15px; color: var(--ink); }
.field select, .field input { min-height: 44px; font: inherit; padding: 0 var(--space-3); border-radius: 10px; border: 1px solid var(--divider); background: transparent; color: var(--ink); }
.stepper { display: flex; align-items: center; gap: var(--space-3); }
.count { min-width: 3ch; text-align: center; font-variant-numeric: tabular-nums; font-size: 20px; font-weight: 700; }
.done { margin: 0; color: var(--ink); }
.link { color: var(--accent-text); font-weight: 600; }
.err { margin: 0; color: var(--danger); }
</style>
