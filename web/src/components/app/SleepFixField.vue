<script setup lang="ts">
import { ref } from 'vue'
import Button from '@/components/ui/Button.vue'
import { useWorkoutsStore } from '@/stores/workouts'

// The runner's own hours for a night the watch recorded short. Saved as a correction; Clear restores the recorded value.
const props = defineProps<{ workoutId: string; night: string; hours: number; corrected: boolean }>()
const emit = defineEmits<{ done: [] }>()
const w = useWorkoutsStore()

w.sleepError = null // a stale error from an earlier attempt does not follow the form
const text = ref<string | number>(props.corrected ? String(Math.round(props.hours * 10) / 10) : '')
const local = ref<string | null>(null)

async function save() {
  local.value = null
  const raw = String(text.value ?? '').trim()
  const v = Number(raw)
  if (!raw || !Number.isFinite(v) || v < 0.5 || v > 14) {
    local.value = 'Enter about how many hours you slept, from 0.5 to 14.'
    return
  }
  if (await w.setSleepCorrection(props.workoutId, props.night, v)) emit('done')
}
async function clear() {
  local.value = null
  if (await w.setSleepCorrection(props.workoutId, props.night, null)) emit('done')
}
</script>

<template>
  <form class="fix" @submit.prevent="save">
    <label class="lbl" for="sleep-hours">About how many hours did you sleep?</label>
    <span class="row">
      <input id="sleep-hours" v-model="text" class="inp" type="number" inputmode="decimal" min="0.5" max="14" step="any" placeholder="6.5" data-testid="sleep-hours" :disabled="w.sleepBusy" />
      <Button small type="submit" :disabled="w.sleepBusy" data-testid="sleep-save">Save</Button>
      <Button v-if="corrected" small type="button" :disabled="w.sleepBusy" data-testid="sleep-clear" @click="clear">Use recorded</Button>
      <Button small type="button" :disabled="w.sleepBusy" data-testid="sleep-cancel" @click="emit('done')">Cancel</Button>
    </span>
    <span v-if="local || w.sleepError" class="err" role="alert" data-testid="sleep-error">{{ local ?? w.sleepError }}</span>
  </form>
</template>

<style scoped>
.fix { display: flex; flex-direction: column; gap: 4px; }
.lbl { font-size: 13px; font-weight: 600; color: var(--ink-secondary); }
.row { display: inline-flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
.inp { min-height: 44px; width: 6rem; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink); padding: 0 var(--space-3); font: inherit; }
.inp:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.err { color: var(--danger); font-size: 13px; }
</style>
