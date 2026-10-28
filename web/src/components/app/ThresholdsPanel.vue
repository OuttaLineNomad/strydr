<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import { usePrefsStore } from '@/stores/prefs'

const prefs = usePrefsStore()
const opened = ref(false)
const formError = ref<string | null>(null)
const saved = ref<string | null>(null)

// Draft text per section.key. A value equal to the default is not an override.
const draft = reactive<Record<string, Record<string, string>>>({})
const json = (v: unknown) => JSON.stringify(v)

const sections = computed(() => Object.entries(prefs.thresholds?.defaults ?? {}))
function effective(sec: string, key: string): unknown {
  return prefs.thresholds?.overrides?.[sec]?.[key] ?? prefs.thresholds?.defaults?.[sec]?.[key]
}
function fill() {
  for (const [sec, keys] of Object.entries(prefs.thresholds?.defaults ?? {})) {
    draft[sec] = {}
    for (const k of Object.keys(keys)) draft[sec]![k] = json(effective(sec, k))
  }
}
watch(() => prefs.thresholds, fill, { immediate: true })

async function toggle() {
  opened.value = !opened.value
  if (opened.value && !prefs.thresholds) await prefs.loadThresholds()
}
const isOverridden = (sec: string, key: string) => !!prefs.thresholds?.overrides?.[sec] && key in prefs.thresholds.overrides[sec]!

function build(): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {}
  for (const [sec, keys] of Object.entries(prefs.thresholds?.defaults ?? {})) {
    for (const [k, def] of Object.entries(keys)) {
      const text = draft[sec]?.[k] ?? json(def)
      let val: unknown
      try {
        val = JSON.parse(text)
      } catch {
        throw new Error(`${sec} ${k.replace(/_/g, ' ')} needs a number, true, false or a JSON value.`)
      }
      if (typeof def === 'number' && typeof val !== 'number') throw new Error(`${sec} ${k.replace(/_/g, ' ')} needs a number.`)
      if (json(val) !== json(def)) (out[sec] ??= {})[k] = val
    }
  }
  return out
}

async function save() {
  formError.value = null
  saved.value = null
  let overrides
  try {
    overrides = build()
  } catch (e) {
    formError.value = (e as Error).message
    return
  }
  if (await prefs.saveThresholds(overrides as never)) saved.value = 'Thresholds saved.'
}
async function reset() {
  formError.value = null
  saved.value = null
  if (await prefs.saveThresholds({})) saved.value = 'Every threshold is back to its default.'
}
</script>

<template>
  <GlassPanel class="panel" role="group" aria-label="Thresholds" data-testid="thresholds">
    <h2 class="row-title">Advanced: thresholds</h2>
    <p class="row-meta">The cut-offs behind your insights and training load. The defaults suit most people. Changing one recalculates your numbers.</p>
    <div class="actions">
      <Button small :aria-expanded="opened" data-testid="thresholds-toggle" @click="toggle">{{ opened ? 'Hide thresholds' : 'Show thresholds' }}</Button>
    </div>

    <template v-if="opened">
      <p v-if="prefs.thresholdsError && !prefs.thresholds" class="err" role="alert">{{ prefs.thresholdsError }}</p>
      <p v-if="prefs.thresholds?.recompute_pending" class="row-meta" role="status" data-testid="thresholds-recalc">Recalculating your numbers…</p>
      <form v-if="prefs.thresholds" class="stack" novalidate @submit.prevent="save">
        <fieldset v-for="[sec, keys] in sections" :key="sec" class="sec">
          <legend class="row-title">{{ sec }}</legend>
          <label v-for="(def, k) in keys" :key="k" class="field">
            <span class="row-meta">
              {{ String(k).replace(/_/g, ' ') }}
              <strong v-if="isOverridden(sec, String(k))" class="changed" data-testid="threshold-changed">(changed, default {{ json(def) }})</strong>
            </span>
            <input v-if="draft[sec]" v-model="draft[sec]![String(k)]" class="input" autocomplete="off" :data-testid="`th-${sec}-${k}`" />
          </label>
        </fieldset>
        <div class="actions">
          <Button variant="primary" type="submit" :disabled="prefs.thresholdsBusy" data-testid="thresholds-save">Save thresholds</Button>
          <Button :disabled="prefs.thresholdsBusy" data-testid="thresholds-reset" @click="reset">Reset to defaults</Button>
        </div>
        <p v-if="formError" class="err" role="alert" data-testid="thresholds-form-error">{{ formError }}</p>
        <p v-else-if="prefs.thresholdsError" class="err" role="alert">{{ prefs.thresholdsError }}</p>
        <p v-else-if="saved" class="row-meta" role="status" data-testid="thresholds-saved">{{ saved }}</p>
      </form>
    </template>
  </GlassPanel>
</template>

<style scoped>
.panel { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.panel h2, .panel p { margin: 0; }
.sec { border: 0; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
.sec legend { padding: 0; margin-bottom: var(--space-2); text-transform: capitalize; }
.field { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.field .row-meta { text-transform: capitalize; }
.changed { text-transform: none; color: var(--tertiary-text); font-weight: 600; }
.input { height: 44px; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink); padding: 0 var(--space-4); font: inherit; min-width: 0; }
.input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.actions { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.err { color: var(--danger); }
</style>
