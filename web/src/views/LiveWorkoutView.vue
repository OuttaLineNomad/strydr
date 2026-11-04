<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePlansStore } from '@/stores/plans'
import { useSessionsStore } from '@/stores/sessions'
import { useSettingsStore } from '@/stores/settings'
import { planWeight } from '@/lib/plans'
import { weightUnit, formatClock } from '@/lib/units'
import { nextMoveIndex, READY_MS, replay, roundsText, stepBell, type InputEvent, type PlanShape } from '@/lib/workoutEngine'
import { useWakeLock } from '@/lib/useWakeLock'
import { useTone } from '@/lib/useTone'
import { useLongPress } from '@/lib/useLongPress'
import { clearDraft, readDraft, saveDraft } from '@/lib/liveDraft'
import type { PlanOut, SessionIn } from '@/api/types'

const props = defineProps<{ id: string }>()
const router = useRouter()
const plans = usePlansStore()
const sessions = useSessionsStore()
const settings = useSettingsStore()

const MAX_RUN_MS = 4 * 3600 * 1000 // the server takes at most 4 hours
const PAUSE_HOLD_MS = 600
const END_HOLD_MS = 1000
const FLASH_MS = 150

// The plan as it was when the run began: a reload of the library mid-session must not change or blank the run.
const planSnap = ref<PlanOut | null>(null)
const plan = computed<PlanOut | undefined>(() => planSnap.value ?? undefined)
const missing = ref(false)
const loadError = ref(false)
let gone = false

const startAt = ref(0) // epoch ms at which the workout begins (after Get ready)
const now = ref(Date.now())
const inputs = ref<InputEvent[]>([])
const running = ref(false)
let ticker: ReturnType<typeof setInterval> | null = null

const wake = useWakeLock()
const tone = useTone()
const flashOn = ref(false)
let flashTimer: ReturnType<typeof setTimeout> | null = null

// The bell for this session only. Null for a bodyweight plan.
const baseKg = computed(() => plan.value?.moves.find((m) => m.weight_kg != null)?.weight_kg ?? null)
const sessionKg = ref<number | null>(null)
const units = computed(() => settings.units)
const deltaKg = computed(() => (sessionKg.value != null && baseKg.value != null ? sessionKg.value - baseKg.value : 0))

function bellText(kg: number | null | undefined): string {
  return kg == null ? 'bodyweight' : `${planWeight(kg, units.value)} ${weightUnit(units.value)}`
}
function moveBell(i: number): string {
  const kg = plan.value?.moves[i]?.weight_kg
  return bellText(kg == null ? null : Math.max(0.5, kg + deltaKg.value))
}
function amount(i: number): string {
  const m = plan.value?.moves[i]
  return m?.reps != null ? `${m.reps} reps` : `${m?.seconds ?? 0} sec`
}
function stepWeight(dir: 1 | -1) {
  tone.unlock()
  if (sessionKg.value == null) return
  sessionKg.value = stepBell(sessionKg.value, dir, units.value)
  persist()
}
function persist() {
  if (!planSnap.value || !running.value) return
  saveDraft({ planId: planSnap.value.id, plan: planSnap.value, startAt: startAt.value, inputs: inputs.value, weight: sessionKg.value })
}

const rep = computed(() => {
  const p = plan.value
  if (!p || !running.value) return null
  return replay(p as PlanShape, inputs.value, now.value - startAt.value)
})
const st = computed(() => rep.value?.state ?? null)

function clock(): number {
  return Date.now() - startAt.value
}
function push(kind: InputEvent['kind']) {
  now.value = Date.now()
  // Never later than the server's 4 h cap, even if a throttled timer woke up late.
  inputs.value = [...inputs.value, { t_ms: Math.min(Math.max(0, clock()), MAX_RUN_MS - 1000), kind }]
  persist()
}
function flash() {
  flashOn.value = true
  if (flashTimer) clearTimeout(flashTimer)
  flashTimer = setTimeout(() => (flashOn.value = false), FLASH_MS)
}

const live = computed(() => !!st.value && (st.value.phase === 'work' || st.value.phase === 'rest' || st.value.phase === 'overtime' || st.value.phase === 'paused'))

function act() {
  tone.unlock()
  const s = st.value
  if (!s || !plan.value) return
  if (s.phase === 'paused') {
    push('resume')
    tone.tap()
    flash()
  } else if (s.phase === 'work' || s.phase === 'rest' || s.phase === 'overtime') {
    push(plan.value.format === 'emom' ? 'flag' : 'next')
    tone.tap()
    flash()
  }
}
function togglePause() {
  tone.unlock()
  const s = st.value
  if (!s) return
  if (s.phase === 'paused') push('resume')
  else if (s.phase === 'work' || s.phase === 'rest' || s.phase === 'overtime') push('pause')
  else return
  tone.tap()
  flash()
}
function endNow() {
  if (!live.value) return
  push('end')
  tone.tap()
}
function startEnd(e?: Event) {
  if (live.value) pressEnd.start(e)
}

const pressField = useLongPress(PAUSE_HOLD_MS, () => {
  if (st.value && st.value.phase !== 'paused') togglePause()
})
const pressEnd = useLongPress(END_HOLD_MS, endNow)

function onFieldDown(e: Event) {
  tone.unlock()
  if (st.value?.phase === 'paused') {
    pressField.consumeClick() // a tap resumes; no hold needed, and a stale long-press flag must not eat it
    return
  }
  pressField.start(e)
}
function onFieldClick() {
  if (pressField.consumeClick()) return
  act()
}

function onKeydown(e: KeyboardEvent) {
  if (e.metaKey || e.ctrlKey || e.altKey) return
  const t = e.target as HTMLElement | null
  const onControl = !!t && !!t.closest && !!t.closest('button, a, input, select, textarea')
  if (e.key === ' ' || e.key === 'Enter') {
    if (onControl && !t?.closest('[data-testid="live-field"]')) return
    e.preventDefault()
    if (!e.repeat) act()
  } else if (e.key === 'p' || e.key === 'P') {
    if (!e.repeat) togglePause()
  } else if (e.key === 'Escape') {
    if (!e.repeat) startEnd()
  }
}
function onKeyup(e: KeyboardEvent) {
  if (e.key === 'Escape') pressEnd.cancel()
}
// Enter or Space on the focused End button starts the same 1 s hold.
function onEndKeydown(e: KeyboardEvent) {
  if (e.key !== ' ' && e.key !== 'Enter') return
  e.preventDefault()
  e.stopPropagation()
  if (!e.repeat) startEnd()
}
function onEndKeyup(e: KeyboardEvent) {
  if (e.key === ' ' || e.key === 'Enter') pressEnd.cancel()
}

// Auto changes (a timed move ends, a minute turns) get the chime and the flash.
const autoCount = computed(() => rep.value?.log.filter((e) => e.kind === 'auto').length ?? 0)
watch(autoCount, (n, was) => {
  if (n > was) {
    if (tone.ready) tone.chime()
    flash()
  }
})

function tick() {
  now.value = Date.now()
  if (clock() >= MAX_RUN_MS - 1000 && live.value) push('end')
}

function launch() {
  running.value = true
  now.value = Date.now()
  wake.start()
  ticker = setInterval(tick, 100)
  persist()
}

async function begin() {
  loadError.value = false
  missing.value = false
  const id = Number(props.id)
  const draft = readDraft(id)
  if (draft) {
    // A run that was interrupted: straight back into the live state.
    planSnap.value = draft.plan
    startAt.value = draft.startAt
    inputs.value = draft.inputs
    sessionKg.value = draft.weight
    launch()
    return
  }
  if (!plans.loaded) await plans.load()
  if (gone) return
  const p = plans.plans.find((x) => x.id === id)
  if (!p) {
    if (!plans.loaded) loadError.value = true
    else missing.value = true
    return
  }
  planSnap.value = JSON.parse(JSON.stringify(p))
  sessionKg.value = p.moves.find((m) => m.weight_kg != null)?.weight_kg ?? null
  startAt.value = Date.now() + READY_MS
  launch()
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('keyup', onKeyup)
  void begin()
})
function stopTicker() {
  if (ticker) clearInterval(ticker)
  ticker = null
}
onBeforeUnmount(() => {
  gone = true
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('keyup', onKeyup)
  stopTicker()
  if (flashTimer) clearTimeout(flashTimer)
})

// --- Finish and save ---------------------------------------------------------------------------------------------
const saveState = ref<'saving' | 'saved' | 'kept' | 'rejected' | 'unsaved'>('saving')
const finished = ref<{ rounds: number; partial: number; activeMs: number; bell: string } | null>(null)

watch(
  () => st.value?.phase,
  (phase) => {
    if (phase !== 'done' || finished.value || !st.value || !plan.value || !rep.value) return
    stopTicker()
    void wake.stop()
    clearDraft() // the record below is now the log; the outbox takes over if the POST fails
    const s = st.value
    const p = plan.value
    finished.value = { rounds: s.roundsDone, partial: s.partialMoves, activeMs: s.activeMs, bell: bellText(sessionKg.value) }
    const record: SessionIn = {
      plan_id: p.id,
      plan: {
        name: p.name, format: p.format, cap_min: p.cap_min, emom_min: p.emom_min, rounds: p.rounds,
        moves: p.moves.map((m) => ({ name: m.name, reps: m.reps, seconds: m.seconds, weight_kg: m.weight_kg })),
        video_url: p.video_url,
      },
      weight_kg: sessionKg.value,
      start_utc: new Date(startAt.value).toISOString(),
      end_utc: new Date(startAt.value + Math.min(s.endedMs ?? 0, MAX_RUN_MS - 1000)).toISOString(),
      events: rep.value.log,
      rounds_done: s.roundsDone,
      partial_moves: s.partialMoves,
      fell_short: s.fellShort,
    }
    void sessions.save(record).then((r) => (saveState.value = r))
  },
)

// --- What the screen says -----------------------------------------------------------------------------------------
const stateWord = computed(() => {
  switch (st.value?.phase) {
    case 'rest': return 'Rest'
    case 'overtime': return 'Overtime'
    case 'paused': return 'Paused'
    case 'ready': return 'Get ready'
    default: return 'Work'
  }
})
const fieldClass = computed(() => `s-${st.value?.phase ?? 'work'}`)

const moveName = computed(() => plan.value?.moves[st.value?.move ?? 0]?.name ?? '')
const headline = computed(() => {
  const ph = st.value?.phase
  if (ph === 'paused') return 'Paused'
  if (ph === 'rest') return 'Rest'
  return moveName.value
})
const amountLine = computed(() => {
  const s = st.value
  if (!s || !plan.value) return ''
  if (s.phase === 'paused') return 'Tap to resume'
  if (s.phase === 'rest') return `Tap to start round ${s.round + 2}`
  const m = plan.value.moves[s.move]
  return `${amount(s.move)}${m?.weight_kg != null ? ` · ${moveBell(s.move)}` : ''}`
})
const clockText = computed(() => {
  const s = st.value
  const p = plan.value
  if (!s || !p) return ''
  if (s.moveLeftMs != null) return formatClock(Math.ceil(s.moveLeftMs / 1000))
  if (p.format === 'emom') return String(Math.ceil(s.clockMs / 1000))
  if (p.format === 'amrap') {
    return s.base === 'overtime' ? `+${formatClock(Math.floor(s.clockMs / 1000))}` : formatClock(Math.ceil(s.clockMs / 1000))
  }
  return formatClock(Math.floor(s.clockMs / 1000))
})
const positionLine = computed(() => {
  const s = st.value
  const p = plan.value
  if (!s || !p) return ''
  const n = p.moves.length
  if (p.format === 'emom') return `Minute ${s.minute + 1} of ${p.emom_min} · Move ${s.move + 1} of ${n}`
  const round = p.format === 'complex' ? `Round ${s.round + 1} of ${p.rounds}` : `Round ${s.round + 1}`
  let line = s.phase === 'rest' ? `${round} done` : `${round} · Move ${s.move + 1} of ${n}`
  if (p.format === 'amrap' && s.moveLeftMs != null) {
    line += s.base === 'overtime' ? ` · +${formatClock(Math.floor(s.clockMs / 1000))}` : ` · ${formatClock(Math.ceil(s.clockMs / 1000))} left`
  }
  return line
})
const hint = computed(() => {
  const s = st.value
  const p = plan.value
  if (!s || !p) return ''
  if (s.base === 'overtime' && s.phase !== 'paused') return 'Finish this round'
  if (p.format === 'emom' && s.phase !== 'paused') return s.fellShort.includes(s.minute + 1) ? 'Fell short. Tap to undo.' : 'Tap if you fell short'
  return ''
})
const nextLine = computed(() => {
  const s = st.value
  const p = plan.value
  if (!s || !p) return ''
  const i = nextMoveIndex(p as PlanShape, s)
  if (i == null) return 'Next: done'
  const m = p.moves[i]
  if (!m) return 'Next: done'
  return `Next: ${m.name} ${m.reps != null ? `× ${m.reps}` : `· ${m.seconds} sec`}`
})
const fieldLabel = computed(() => {
  const s = st.value
  if (!s) return ''
  const act = s.phase === 'paused' ? 'Resume' : plan.value?.format === 'emom' ? 'Flag this minute as fell short' : s.phase === 'rest' ? 'Start next round' : 'Next move'
  return `${act}. ${headline.value}. ${amountLine.value}`
})
const readySeconds = computed(() => Math.max(1, Math.ceil((st.value?.readyMs ?? 0) / 1000)))
const wakeNote = computed(() => wake.unavailable.value)

function done() {
  void router.push('/workouts')
}
</script>

<template>
  <div class="live" :class="fieldClass" data-testid="live">
    <!-- Could not load -->
    <section v-if="loadError" class="center" role="alert" data-testid="live-load-error">
      <h1 class="plain">The workout did not load</h1>
      <p class="line">Check your connection, then try again.</p>
      <button type="button" class="big-btn" data-testid="live-retry" @click="begin()">Retry</button>
    </section>

    <!-- Not found -->
    <section v-else-if="missing" class="center" data-testid="live-missing">
      <h1 class="plain">That workout is gone</h1>
      <p class="line">It may have been deleted. Pick another from your library.</p>
      <button type="button" class="big-btn" @click="done">Back to Workouts</button>
    </section>

    <!-- Loading -->
    <section v-else-if="!st" class="center" role="status" data-testid="live-loading">
      <p class="line">Loading workout.</p>
    </section>

    <!-- Saved -->
    <section v-else-if="finished" class="center saved" data-testid="saved">
      <p class="state-word">Saved</p>
      <h1 class="plain" data-testid="saved-plan">{{ plan?.name }}</h1>
      <p class="big" data-testid="saved-rounds">{{ roundsText(finished.rounds, finished.partial) }}</p>
      <dl class="facts">
        <div><dt>Active time</dt><dd data-testid="saved-time">{{ formatClock(Math.round(finished.activeMs / 1000)) }}</dd></div>
        <div><dt>Bell</dt><dd data-testid="saved-bell">{{ finished.bell === 'bodyweight' ? 'Bodyweight' : finished.bell }}</dd></div>
      </dl>
      <p v-if="saveState === 'kept'" class="line" role="status" data-testid="saved-status">Saved on this phone, will sync</p>
      <p v-else-if="saveState === 'rejected'" class="line" role="alert" data-testid="saved-status">This session could not be saved.</p>
      <p v-else-if="saveState === 'unsaved'" class="line" role="alert" data-testid="saved-status">This session could not be stored on this phone.</p>
      <p v-else-if="saveState === 'saving'" class="line" role="status" data-testid="saved-status">Saving.</p>
      <button type="button" class="big-btn" data-testid="saved-done" @click="done">Done</button>
    </section>

    <!-- Get ready -->
    <section v-else-if="st.phase === 'ready'" class="center ready" data-testid="ready" @pointerdown="tone.unlock()">
      <p class="state-word">Get ready</p>
      <h1 class="plain" data-testid="ready-plan">{{ plan?.name }}</h1>
      <p class="count" aria-live="off" data-testid="ready-count">{{ readySeconds }}</p>
      <p class="first" data-testid="ready-move">{{ plan?.moves[0]?.name }} · {{ amount(0) }}</p>
      <div v-if="sessionKg != null" class="bell">
        <button type="button" class="weight" :aria-label="`Bell ${bellText(sessionKg)}. Tap for the next heavier bell`" data-testid="weight-up" @click="stepWeight(1)">
          {{ bellText(sessionKg) }}
        </button>
        <button type="button" class="lighter" :aria-label="`Next lighter bell, now ${bellText(sessionKg)}`" data-testid="weight-down" @click="stepWeight(-1)">Lighter</button>
      </div>
      <p v-else class="line">Bodyweight</p>
      <p class="line">This changes today only, not the workout.</p>
    </section>

    <!-- The live field -->
    <template v-else>
      <div
        class="field"
        role="button"
        tabindex="0"
        aria-keyshortcuts="Space Enter"
        :aria-label="fieldLabel"
        data-testid="live-field"
        @pointerdown="onFieldDown"
        @pointerup="pressField.cancel"
        @pointerleave="pressField.cancel"
        @pointercancel="pressField.cancel"
        @contextmenu.prevent
        @click="onFieldClick"
      >
        <p class="state-word" data-testid="live-state">{{ stateWord }}</p>
        <h1 class="move" data-testid="live-move">{{ headline }}</h1>
        <p class="amount" data-testid="live-amount">{{ amountLine }}</p>
        <p class="clock" data-testid="live-clock">{{ clockText }}</p>
        <p class="hint" data-testid="live-hint">{{ hint }}</p>
        <p class="position" data-testid="live-position">{{ positionLine }}</p>
        <p class="next" data-testid="live-next">{{ nextLine }}</p>
        <div v-if="pressField.holding.value" class="ring" aria-hidden="true" data-testid="live-ring">
          <svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="44" /></svg>
        </div>
        <i class="flash" :class="{ on: flashOn }" aria-hidden="true" data-testid="live-flash" />
      </div>

      <p v-if="wakeNote" class="notice" role="status" data-testid="wake-notice">Screen may sleep — keep it on in Settings</p>

      <button
        type="button"
        class="end"
        :class="{ holding: pressEnd.holding.value }"
        aria-keyshortcuts="Escape"
        aria-label="End workout. Hold for 1 second."
        data-testid="live-end"
        @pointerdown="startEnd"
        @keydown="onEndKeydown"
        @keyup="onEndKeyup"
        @pointerup="pressEnd.cancel"
        @pointerleave="pressEnd.cancel"
        @pointercancel="pressEnd.cancel"
        @contextmenu.prevent
        @click.prevent
      >
        <span class="end-fill" aria-hidden="true" />
        <span class="end-text">End</span>
      </button>

      <p class="sr" role="status" aria-live="polite">{{ stateWord }}. {{ headline }}. {{ amountLine }}</p>
      <p class="sr">Keys: Space or Enter for next, P to pause or resume, hold Escape to end.</p>
    </template>
  </div>
</template>

<style scoped>
.live {
  position: fixed; inset: 0; z-index: 10;
  background: var(--surface-0); color: var(--ink);
  display: flex; flex-direction: column; overflow: hidden;
  user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.live.s-rest { background: var(--secondary); color: var(--ink-on-secondary); }
.live.s-overtime { background: var(--accent); color: var(--ink-on-accent); }
.live.s-paused { background: var(--surface-2); color: var(--ink); }
.live.s-done { background: var(--surface-0); color: var(--ink); }

.field {
  position: relative; flex: 1; min-height: 0; cursor: pointer;
  display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: var(--space-3);
  padding: calc(env(safe-area-inset-top, 0px) + 72px) var(--space-5) calc(env(safe-area-inset-bottom, 0px) + var(--space-5));
  outline-offset: -4px;
}
.field:focus-visible { outline: 3px solid var(--focus-ring); }
.state-word { margin: 0; font-family: var(--font-display); font-weight: 700; font-size: 20px; line-height: 28px; }
.move { margin: 0; font-family: var(--font-display); font-weight: 700; font-size: clamp(48px, 14vw, 120px); line-height: 1; letter-spacing: -.02em;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; max-width: 100%; }
.amount { margin: 0; font-family: var(--font-display); font-weight: 600; font-size: clamp(28px, 8vw, 64px); line-height: 1.1; }
.clock { margin: var(--space-2) 0 0; font-family: var(--font-display); font-weight: 700; font-variant-numeric: tabular-nums; font-size: clamp(64px, 22vw, 168px); line-height: 1; letter-spacing: -.03em; }
.hint { margin: 0; min-height: 28px; font-weight: 700; font-size: 20px; line-height: 28px; }
.position { margin: 0; font-size: 18px; line-height: 24px; font-weight: 600; }
.next { margin: 0; font-size: 18px; line-height: 24px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }

.flash { position: absolute; inset: 0; background: var(--ink); opacity: 0; pointer-events: none; transition: opacity 150ms ease-out; }
.live.s-rest .flash, .live.s-overtime .flash { background: var(--ink); }
.flash.on { opacity: .28; }

.ring { position: absolute; left: 50%; top: 50%; width: 140px; height: 140px; margin: -70px 0 0 -70px; pointer-events: none; }
.ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.ring circle { fill: none; stroke: currentColor; stroke-width: 8; stroke-linecap: round; stroke-dasharray: 276.5; stroke-dashoffset: 276.5; animation: fill 600ms linear forwards; }
@keyframes fill { to { stroke-dashoffset: 0; } }

.end {
  position: absolute; top: calc(env(safe-area-inset-top, 0px) + var(--space-3)); right: var(--space-3); z-index: 2;
  min-width: 88px; min-height: 52px; padding: 0 var(--space-5); border: 2px solid currentColor; border-radius: var(--radius-full, 999px);
  background: transparent; color: inherit; font: inherit; font-weight: 700; font-size: 18px; cursor: pointer; overflow: hidden;
  touch-action: manipulation; -webkit-touch-callout: none;
}
.end:focus-visible { outline: 3px solid var(--focus-ring); outline-offset: 2px; }
.end-fill { position: absolute; inset: 0; background: currentColor; opacity: .25; transform: scaleX(0); transform-origin: left; }
.end.holding .end-fill { animation: endfill 1000ms linear forwards; }
@keyframes endfill { to { transform: scaleX(1); } }
.end-text { position: relative; }

.notice { position: absolute; top: calc(env(safe-area-inset-top, 0px) + var(--space-3)); left: var(--space-4); right: 120px; margin: 0; z-index: 2; font-size: 15px; line-height: 20px; font-weight: 600; pointer-events: none; }

.center { flex: 1; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: var(--space-4); padding: var(--space-6) var(--space-5); padding-top: calc(env(safe-area-inset-top, 0px) + var(--space-6)); }
.plain { margin: 0; font-family: var(--font-display); font-size: clamp(32px, 9vw, 64px); line-height: 1.05; font-weight: 700; overflow-wrap: anywhere; }
.line { margin: 0; font-size: 18px; line-height: 26px; }
.big { margin: 0; font-family: var(--font-display); font-weight: 700; font-size: clamp(48px, 14vw, 96px); line-height: 1; }
.count { margin: 0; font-family: var(--font-display); font-weight: 700; font-variant-numeric: tabular-nums; font-size: clamp(96px, 34vw, 220px); line-height: 1; }
.first { margin: 0; font-family: var(--font-display); font-weight: 600; font-size: clamp(28px, 8vw, 56px); line-height: 1.1; }
.bell { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
.weight { min-height: 64px; padding: 0 var(--space-6); border: 3px solid currentColor; border-radius: var(--radius-full, 999px); background: transparent; color: inherit; font-family: var(--font-display); font-weight: 700; font-size: clamp(32px, 9vw, 56px); cursor: pointer; }
.lighter { min-height: 48px; padding: 0 var(--space-4); border: 0; background: transparent; color: inherit; font: inherit; font-weight: 700; font-size: 18px; text-decoration: underline; cursor: pointer; }
.weight:focus-visible, .lighter:focus-visible, .big-btn:focus-visible { outline: 3px solid var(--focus-ring); outline-offset: 3px; }
.big-btn { min-height: 64px; padding: 0 var(--space-8); border: 0; border-radius: var(--radius-full, 999px); background: var(--accent); color: var(--ink-on-accent); font-family: var(--font-display); font-weight: 700; font-size: 24px; cursor: pointer; }
.facts { margin: 0; display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-5); width: 100%; }
.facts dt { font-size: 16px; line-height: 22px; }
.facts dd { margin: 0; font-family: var(--font-display); font-weight: 700; font-variant-numeric: tabular-nums; font-size: clamp(32px, 9vw, 56px); line-height: 1.1; }
.sr { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }

@media (prefers-reduced-motion: reduce) {
  /* The tone stays; the pulse becomes a colour step with no fade. */
  .flash { transition: none; }
}
</style>
