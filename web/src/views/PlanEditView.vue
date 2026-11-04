<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import Icons from '@/components/ui/Icons.vue'
import Segmented from '@/components/ui/Segmented.vue'
import { usePlansStore } from '@/stores/plans'
import { useSettingsStore } from '@/stores/settings'
import { displayToKg, weightUnit } from '@/lib/units'
import { planWeight } from '@/lib/plans'
import { LADDERS, LADDER_IDS, rungName, type LadderId } from '@/lib/ladders'
import type { PlanIn, PlanOut } from '@/api/types'

type Format = PlanOut['format']
/** `origKg` and `origText` are what was loaded: an untouched weight is saved back as exactly `origKg`. */
interface MoveRow { key: number; name: string; mode: 'reps' | 'seconds'; amount: string; weight: string; origKg: number | null; origText: string; ladder: LadderId | null; rung: number | null }

const props = defineProps<{ id?: string }>()
const store = usePlansStore()
const s = useSettingsStore()
const router = useRouter()
const route = useRoute()

const unit = computed(() => weightUnit(s.units))
const editingId = computed(() => (props.id == null ? null : /^\d+$/.test(props.id) ? Number(props.id) : NaN))
const invalidId = computed(() => editingId.value != null && Number.isNaN(editingId.value))

let nextKey = 1
const blankMove = (): MoveRow => ({ key: nextKey++, name: '', mode: 'reps', amount: '', weight: '', origKg: null, origText: '', ladder: null, rung: null })

const name = ref('')
const format = ref<Format>('amrap')
const cap = ref('20')
const emom = ref('12')
const rounds = ref('4')
const video = ref('')
const moves = reactive<MoveRow[]>([blankMove()])
const same = ref('')
const loading = ref(editingId.value != null)
const missing = ref(false)
const loadError = ref(false)
const tried = ref(false)
const confirmDelete = ref(false)
const ytUrl = ref('')
const ytInput = ref<HTMLInputElement | null>(null)
const builtFrom = ref<string | null>(null)

const formats = [
  { label: 'AMRAP', value: 'amrap' as Format, testid: 'format-amrap' },
  { label: 'EMOM', value: 'emom' as Format, testid: 'format-emom' },
  { label: 'Complex', value: 'complex' as Format, testid: 'format-complex' },
]

function fill(p: PlanOut) {
  name.value = p.name
  format.value = p.format
  cap.value = p.cap_min == null ? '20' : String(p.cap_min)
  emom.value = p.emom_min == null ? '12' : String(p.emom_min)
  rounds.value = p.rounds == null ? '4' : String(p.rounds)
  video.value = p.video_url ?? ''
  moves.splice(0, moves.length, ...p.moves.map((m) => ({
    key: nextKey++,
    name: m.name,
    mode: m.seconds != null ? ('seconds' as const) : ('reps' as const),
    amount: String(m.seconds ?? m.reps ?? ''),
    weight: m.weight_kg == null ? '' : planWeight(m.weight_kg, s.units),
    origKg: m.weight_kg ?? null,
    origText: m.weight_kg == null ? '' : planWeight(m.weight_kg, s.units),
    ladder: m.ladder ?? null,
    rung: m.rung ?? null,
  })))
}

function reset() {
  name.value = ''
  format.value = 'amrap'
  cap.value = '20'
  emom.value = '12'
  rounds.value = '4'
  video.value = ''
  same.value = ''
  moves.splice(0, moves.length, blankMove())
}

async function init() {
  loading.value = true
  missing.value = false
  loadError.value = false
  tried.value = false
  confirmDelete.value = false
  store.error = null
  store.nameError = null
  store.cancelImport() // an import still waiting must not fill a different form
  reset()
  ytUrl.value = ''
  builtFrom.value = null
  store.importError = null
  if (invalidId.value) {
    missing.value = true
    loading.value = false
    return
  }
  // the library feeds the move-name suggestions too, so a new plan loads it as well
  if (!store.loaded || (editingId.value != null && !store.plans.some((p) => p.id === editingId.value))) await store.load()
  if (store.error) loadError.value = true
  else if (editingId.value != null) {
    const p = store.plans.find((x) => x.id === editingId.value)
    if (p) fill(p)
    else missing.value = true
  }
  loading.value = false
  if (editingId.value == null && route.query.import != null) {
    await nextTick()
    ytInput.value?.focus()
  }
}

async function buildFromVideo() {
  builtFrom.value = null
  const d = await store.importYoutube(ytUrl.value)
  if (!d || editingId.value != null) return
  reset()
  fill({ ...d.plan, id: 0, created_at: '', updated_at: '' } as PlanOut)
  builtFrom.value = d.title
}
onMounted(init)
onUnmounted(() => store.cancelImport())
watch(() => props.id, init)
// Switching units re-shows the entered weights in the new unit.
watch(() => s.units, (now, was) => {
  for (const m of moves) {
    if (m.origKg != null && m.weight === m.origText) {
      m.origText = m.weight = planWeight(m.origKg, now) // untouched: re-show the exact stored kg
      continue
    }
    const v = Number(m.weight)
    if (str(m.weight) && Number.isFinite(v)) {
      m.weight = planWeight(displayToKg(v, was), now)
      m.origKg = null
    }
  }
  const sv = Number(same.value)
  if (str(same.value) && Number.isFinite(sv)) same.value = planWeight(displayToKg(sv, was), now)
})

const suggestions = computed(() => store.moveNames())
const maxWeight = computed(() => planWeight(100, s.units))
const minWeight = computed(() => planWeight(0.5, s.units))

// type=number inputs hand v-model a number (or ''), so every read goes through a string
const str = (v: unknown) => String(v ?? '').trim()
const int = (v: unknown) => (/^\d+$/.test(str(v)) ? Number(str(v)) : NaN)
const inRange = (n: number, lo: number, hi: number) => Number.isInteger(n) && n >= lo && n <= hi
function weightKg(v: unknown): number | null | undefined {
  if (!str(v)) return null
  const n = Number(str(v))
  if (!Number.isFinite(n)) return undefined
  const kg = displayToKg(n, s.units)
  return kg >= 0.5 - 1e-9 && kg <= 100 + 1e-9 ? Math.min(100, Math.max(0.5, Math.round(kg * 10000) / 10000)) : undefined
}

const errors = computed(() => {
  const e: { name?: string; setting?: string; moves?: string; video?: string; rows: (string | undefined)[] } = { rows: [] }
  const n = name.value.trim()
  if (!n) e.name = 'Give the workout a name.'
  else if (n.length > 60) e.name = 'Use 60 characters or fewer.'
  if (format.value === 'amrap' && !inRange(int(cap.value), 1, 90)) e.setting = 'Time cap is 1 to 90 minutes.'
  if (format.value === 'emom' && !inRange(int(emom.value), 1, 90)) e.setting = 'Total time is 1 to 90 minutes.'
  if (format.value === 'complex' && !inRange(int(rounds.value), 1, 50)) e.setting = 'Rounds is 1 to 50.'
  if (moves.length < 1) e.moves = 'Add at least one move.'
  if (moves.length > 12) e.moves = 'Use 12 moves or fewer.'
  for (const m of moves) {
    const nm = m.name.trim()
    let msg: string | undefined
    if (m.ladder && m.rung == null) msg = 'Pick a rung for the level.'
    else if (!nm || nm.length > 40) msg = 'Name the move in 40 characters or fewer.'
    else if (m.mode === 'reps' ? !inRange(int(m.amount), 1, 500) : !inRange(int(m.amount), 5, 600)) {
      msg = m.mode === 'reps' ? 'Reps is 1 to 500.' : 'Seconds is 5 to 600.'
    } else if (weightKg(m.weight) === undefined) msg = `Bell is ${minWeight.value} to ${maxWeight.value} ${unit.value}, or blank for bodyweight.`
    e.rows.push(msg)
  }
  const v = video.value.trim()
  if (v) {
    try {
      if (!/^https?:\/\/[^\s/]+/i.test(v)) throw new Error('scheme')
      new URL(v)
    } catch {
      e.video = 'Use a link that starts with http:// or https://.'
    }
  }
  return e
})
const valid = computed(() => !errors.value.name && !errors.value.setting && !errors.value.moves && !errors.value.video && errors.value.rows.every((r) => !r))

function applySame() {
  const kg = weightKg(same.value)
  if (kg == null || kg === undefined) return
  const shown = planWeight(kg, s.units)
  for (const m of moves) if (str(m.weight)) m.weight = shown
}
const sameOk = computed(() => weightKg(same.value) != null)
const anyWeighted = computed(() => moves.some((m) => str(m.weight)))

/** The Level control belongs to a move with no bell, counted in reps. */
const canLevel = (m: MoveRow) => m.ladder != null || (m.mode === 'reps' && !str(m.weight))
function pickLadder(m: MoveRow, id: LadderId | null) {
  if (m.ladder !== id && m.ladder != null && m.rung != null && m.name === rungName(m.ladder, m.rung)) m.name = '' // drop the old auto name
  if (id == null) {
    m.ladder = m.rung = null
    return
  }
  if (m.ladder !== id) {
    m.ladder = id
    m.rung = null
  }
  m.mode = 'reps'
  m.weight = ''
  m.origKg = null
}
function pickRung(m: MoveRow, rung: number) {
  if (m.ladder == null) return
  m.rung = rung
  m.name = rungName(m.ladder, rung)
}

function addMove() {
  if (moves.length < 12) moves.push(blankMove())
}
function removeMove(i: number) {
  moves.splice(i, 1)
}
function shift(i: number, d: -1 | 1) {
  const j = i + d
  if (j < 0 || j >= moves.length) return
  const [m] = moves.splice(i, 1)
  moves.splice(j, 0, m!)
}

function body(): PlanIn {
  return {
    name: name.value.trim(),
    format: format.value,
    cap_min: format.value === 'amrap' ? int(cap.value) : null,
    emom_min: format.value === 'emom' ? int(emom.value) : null,
    rounds: format.value === 'complex' ? int(rounds.value) : null,
    moves: moves.map((m) => ({
      name: m.name.trim(),
      reps: m.mode === 'reps' ? int(m.amount) : null,
      seconds: m.mode === 'seconds' ? int(m.amount) : null,
      weight_kg: m.ladder ? null : m.origKg != null && m.weight === m.origText ? m.origKg : (weightKg(m.weight) ?? null),
      ...(m.ladder != null && m.rung != null ? { ladder: m.ladder, rung: m.rung } : {}),
    })),
    video_url: video.value.trim() || null,
  }
}

async function save() {
  tried.value = true
  if (!valid.value) return
  const p = editingId.value == null ? await store.create(body()) : await store.update(editingId.value, body())
  if (p) await router.push('/workouts')
}
async function remove() {
  if (editingId.value != null && (await store.remove(editingId.value))) await router.push('/workouts')
}
const nameMsg = computed(() => (tried.value ? errors.value.name : undefined) ?? store.nameError ?? undefined)
</script>

<template>
  <header class="title-row">
    <div>
      <h1 class="page-title">{{ editingId == null ? 'New workout' : 'Edit workout' }}</h1>
    </div>
  </header>

  <GlassPanel v-if="loadError" class="block" role="alert" data-testid="plan-load-error">
    <p class="err">{{ store.error }}</p>
    <Button data-testid="plan-load-retry" @click="init">Retry</Button>
  </GlassPanel>
  <GlassPanel v-else-if="missing" class="block" data-testid="plan-missing">
    <p class="body">That workout is gone.</p>
    <Button to="/workouts">Back to workouts</Button>
  </GlassPanel>
  <p v-else-if="loading" class="body" role="status">Loading the workout.</p>

  <form v-else class="form" novalidate @submit.prevent="save">
    <GlassPanel v-if="editingId == null" class="block" data-testid="yt-block">
      <label class="field">
        <span class="lbl">YouTube link</span>
        <input ref="ytInput" v-model="ytUrl" class="input" type="url" inputmode="url" autocomplete="off" placeholder="https://youtube.com/shorts/…" :disabled="store.importing" :aria-describedby="store.importError ? 'yt-err' : undefined" data-testid="yt-input" @keydown.enter.prevent="buildFromVideo" />
      </label>
      <div class="yt-actions">
        <Button variant="primary" :disabled="store.importing" data-testid="yt-build" @click="buildFromVideo">{{ store.importing ? 'Reading the video…' : 'Build workout' }}</Button>
        <Button v-if="store.importing" data-testid="yt-cancel" @click="store.cancelImport()">Cancel</Button>
      </div>
      <p v-if="store.importError" id="yt-err" class="err" role="alert" data-testid="yt-error">
        {{ store.importError }}
        <RouterLink v-if="store.importError.startsWith('Turn on AI')" to="/settings" class="link" data-testid="yt-settings">Open Settings</RouterLink>
      </p>
      <p v-else-if="builtFrom !== null" class="hint" role="status" data-testid="yt-note">Built from {{ builtFrom }}. Check the moves, then save.</p>
    </GlassPanel>

    <GlassPanel class="block">
      <label class="field">
        <span class="lbl">Name</span>
        <input v-model="name" class="input" maxlength="60" autocomplete="off" :aria-invalid="!!nameMsg" :aria-describedby="nameMsg ? 'name-err' : undefined" data-testid="plan-name-input" />
        <span v-if="nameMsg" id="name-err" class="err" role="alert" data-testid="plan-name-error">{{ nameMsg }}</span>
      </label>

      <div class="field">
        <span class="lbl">Format</span>
        <Segmented v-model="format" :options="formats" label="Format" />
      </div>

      <label v-if="format === 'amrap'" class="field">
        <span class="lbl">Time cap (minutes)</span>
        <input v-model="cap" class="input short" type="number" inputmode="numeric" min="1" max="90" data-testid="plan-cap" />
      </label>
      <label v-else-if="format === 'emom'" class="field">
        <span class="lbl">Total time (minutes)</span>
        <input v-model="emom" class="input short" type="number" inputmode="numeric" min="1" max="90" data-testid="plan-emom" />
        <span class="hint">One move each minute, in order, repeating.</span>
      </label>
      <label v-else class="field">
        <span class="lbl">Rounds</span>
        <input v-model="rounds" class="input short" type="number" inputmode="numeric" min="1" max="50" data-testid="plan-rounds" />
      </label>
      <span v-if="tried && errors.setting" class="err" role="alert" data-testid="plan-setting-error">{{ errors.setting }}</span>
    </GlassPanel>

    <GlassPanel class="block">
      <h2 class="row-title">Moves</h2>
      <div class="same">
        <label class="field grow">
          <span class="lbl">Same weight for all ({{ unit }})</span>
          <input v-model="same" class="input short" type="number" inputmode="decimal" step="any" data-testid="same-weight" />
        </label>
        <Button :disabled="!sameOk || !anyWeighted" data-testid="same-apply" @click="applySame">Apply</Button>
      </div>
      <p class="hint">Moves with a bell take this weight. Blank ones stay bodyweight.</p>

      <ol class="moves">
        <li v-for="(m, i) in moves" :key="m.key" class="move" data-testid="move-row">
          <label class="field">
            <span class="lbl">Move {{ i + 1 }}</span>
            <input v-model="m.name" class="input" list="move-names" maxlength="40" autocomplete="off" :readonly="m.ladder != null && m.rung != null" :aria-label="`Move ${i + 1} name`" data-testid="move-name" />
          </label>
          <div class="amount">
            <div v-if="!m.ladder" class="toggle" role="group" :aria-label="`Move ${i + 1} counts`">
              <button type="button" class="tg" :class="{ on: m.mode === 'reps' }" :aria-pressed="m.mode === 'reps'" data-testid="move-mode-reps" @click="m.mode = 'reps'">Reps</button>
              <button type="button" class="tg" :class="{ on: m.mode === 'seconds' }" :aria-pressed="m.mode === 'seconds'" data-testid="move-mode-seconds" @click="m.mode = 'seconds'">Seconds</button>
            </div>
            <div class="field">
              <span v-if="m.ladder" class="lbl">Reps</span>
            <input v-model="m.amount" class="input num" type="number" inputmode="numeric" :min="m.mode === 'reps' ? 1 : 5" :aria-label="`Move ${i + 1} ${m.mode}`" data-testid="move-amount" />
            </div>
          </div>
          <label v-if="!m.ladder" class="field">
            <span class="lbl">Bell ({{ unit }})</span>
            <input v-model="m.weight" class="input num" type="number" inputmode="decimal" step="any" placeholder="bodyweight" :aria-label="`Move ${i + 1} bell weight`" data-testid="move-weight" />
          </label>
          <div v-if="canLevel(m)" class="field level" data-testid="move-level">
            <span :id="`level-${m.key}`" class="lbl">Level (optional)</span>
            <div class="chips" role="group" :aria-labelledby="`level-${m.key}`">
              <button type="button" class="chip" :class="{ on: m.ladder == null }" :aria-pressed="m.ladder == null" data-testid="level-none" @click="pickLadder(m, null)">None</button>
              <button v-for="id in LADDER_IDS" :key="id" type="button" class="chip" :class="{ on: m.ladder === id }" :aria-pressed="m.ladder === id" :data-testid="`level-ladder-${id}`" @click="pickLadder(m, id)">{{ id === 'push-up' ? 'Push-up' : 'Pull-up' }}</button>
            </div>
            <div v-if="m.ladder" class="chips" role="group" :aria-label="`Move ${i + 1} rung`">
              <button v-for="(r, ri) in LADDERS[m.ladder]" :key="r" type="button" class="chip" :class="{ on: m.rung === ri }" :aria-pressed="m.rung === ri" :data-testid="`level-rung-${ri}`" @click="pickRung(m, ri)">{{ r }}</button>
            </div>
          </div>
          <span v-if="tried && errors.rows[i]" class="err" role="alert" data-testid="move-error">{{ errors.rows[i] }}</span>
          <div class="tools">
            <button type="button" class="tool" :disabled="i === 0" :aria-label="`Move ${i + 1} up`" data-testid="move-up" @click="shift(i, -1)"><Icons name="arrow-up" :size="20" /></button>
            <button type="button" class="tool" :disabled="i === moves.length - 1" :aria-label="`Move ${i + 1} down`" data-testid="move-down" @click="shift(i, 1)"><Icons name="arrow-down" :size="20" /></button>
            <button type="button" class="tool rm" :disabled="moves.length === 1" :aria-label="`Remove move ${i + 1}`" data-testid="move-remove" @click="removeMove(i)">Remove</button>
          </div>
        </li>
      </ol>
      <datalist id="move-names"><option v-for="n in suggestions" :key="n" :value="n" /></datalist>
      <span v-if="tried && errors.moves" class="err" role="alert">{{ errors.moves }}</span>
      <Button variant="secondary" class="full" :disabled="moves.length >= 12" data-testid="add-move" @click="addMove">Add move</Button>
    </GlassPanel>

    <GlassPanel class="block">
      <label class="field">
        <span class="lbl">Video link (optional)</span>
        <input v-model="video" class="input" type="url" inputmode="url" autocomplete="off" placeholder="https://" data-testid="plan-video-input" />
        <span v-if="tried && errors.video" class="err" role="alert" data-testid="plan-video-error">{{ errors.video }}</span>
      </label>
    </GlassPanel>

    <p v-if="store.error" class="err" role="alert" data-testid="plan-save-error">{{ store.error }}</p>

    <div class="bottom">
      <Button variant="primary" type="submit" class="full" :disabled="store.busy" data-testid="plan-save">Save workout</Button>
      <Button to="/workouts" variant="secondary" class="full" data-testid="plan-cancel">Cancel</Button>
    </div>

    <GlassPanel v-if="editingId != null" class="block" data-testid="plan-danger">
      <h2 class="row-title">Delete this workout</h2>
      <div v-if="confirmDelete" class="confirm" data-testid="plan-delete-confirm">
        <span class="body">Delete {{ name }}? This cannot be undone.</span>
        <Button :disabled="store.busy" data-testid="plan-delete-yes" @click="remove">Yes, delete</Button>
        <Button data-testid="plan-delete-no" @click="confirmDelete = false">Keep</Button>
      </div>
      <button v-else type="button" class="del" data-testid="plan-delete" @click="confirmDelete = true">Delete workout</button>
    </GlassPanel>
  </form>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: var(--space-4); margin-top: var(--space-4); }
.block { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-4); }
.block h2, .block p { margin: 0; }
.body { margin: 0; color: var(--ink); }
.field { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.field.grow { flex: 1 1 10rem; }
.lbl { font-size: 15px; font-weight: 600; color: var(--ink); }
.hint { font-size: var(--body-sm-size); color: var(--ink-secondary); margin: 0; }
.input { height: 48px; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: color-mix(in srgb, var(--surface-1) 75%, transparent); color: var(--ink); padding: 0 var(--space-4); font: inherit; min-width: 0; width: 100%; box-sizing: border-box; }
.input.short { max-width: 10rem; }
.input.num { max-width: 9rem; }
.input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.input[aria-invalid='true'] { border-color: var(--danger); }
.err { color: var(--danger); font-size: var(--body-sm-size); }
.link { color: var(--accent-text); font-weight: 600; margin-left: var(--space-2); }
.yt-actions { display: flex; flex-wrap: wrap; gap: var(--space-3); }
.same { display: flex; gap: var(--space-3); align-items: flex-end; flex-wrap: wrap; }
.moves { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.move { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4) 0; }
.move + .move { border-top: 1px solid var(--divider); }
.amount { display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap; }
.toggle { display: inline-flex; border: 1.5px solid var(--divider); border-radius: var(--radius-full); padding: 2px; }
.tg { min-height: 44px; padding: 0 var(--space-4); border: 0; border-radius: var(--radius-full); background: transparent; color: var(--ink-secondary); font: inherit; font-weight: 600; cursor: pointer; }
.tg.on { background: color-mix(in srgb, var(--accent) 16%, var(--surface-2)); color: var(--accent-text); }
.tg:focus-visible, .tool:focus-visible, .del:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.chips { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.chip { min-height: 44px; padding: 0 var(--space-4); border: 1.5px solid var(--divider); border-radius: var(--radius-full); background: transparent; color: var(--ink); font: inherit; font-weight: 600; cursor: pointer; }
.chip.on { background: color-mix(in srgb, var(--accent) 16%, var(--surface-2)); color: var(--accent-text); border-color: var(--accent); }
.chip:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.tools { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.tool { min-height: 44px; min-width: 44px; padding: 0 var(--space-3); border: 1.5px solid var(--divider); border-radius: var(--radius-full); background: transparent; color: var(--ink); font: inherit; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
.tool:disabled { opacity: .4; cursor: not-allowed; }
.tool.rm { color: var(--danger); }
.full { width: 100%; }
.bottom { display: flex; flex-direction: column; gap: var(--space-3); }
.confirm { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
.del { min-height: 44px; width: fit-content; padding: 0 var(--space-3); background: none; border: 0; font: inherit; font-weight: 600; color: var(--danger); cursor: pointer; }
</style>
