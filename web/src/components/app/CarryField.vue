<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import { useSettingsStore } from '@/stores/settings'
import { useWorkoutsStore } from '@/stores/workouts'
import { displayToKg, formatWeightValue, kgToDisplay, weightUnit } from '@/lib/units'

const props = defineProps<{ workoutId: string; carryKg: number | null }>()
const s = useSettingsStore()
const w = useWorkoutsStore()
const unit = computed(() => weightUnit(s.units))

function shown(): string {
  return props.carryKg == null ? '' : formatWeightValue(props.carryKg, s.units)
}
const text = ref<string | number>(shown())
watch(() => [props.carryKg, s.units, props.workoutId], () => (text.value = shown()))

const local = ref<string | null>(null)
async function save() {
  local.value = null
  const raw = String(text.value ?? '').trim()
  if (!raw) {
    // an empty field means no weight, the same as Clear
    if (props.carryKg != null) await clear()
    return
  }
  const v = Number(raw)
  const kg = displayToKg(v, s.units)
  if (!Number.isFinite(v) || kg <= 0 || kg > 100) {
    local.value = `Enter a weight above 0 and up to ${Math.floor(kgToDisplay(100, s.units))} ${unit.value}.`
    return
  }
  if (!(await w.setCarry(props.workoutId, kg))) text.value = shown()
}
async function clear() {
  local.value = null
  if (await w.setCarry(props.workoutId, null)) text.value = ''
}
</script>

<template>
  <form class="carry" @submit.prevent="save">
    <label class="lbl" for="carry-input">Extra weight carried ({{ unit }})</label>
    <span class="row">
      <input id="carry-input" v-model="text" class="inp" placeholder="None" type="number" inputmode="decimal" min="0.1" step="any" data-testid="carry-input" :disabled="w.carryBusy" />
      <Button small type="submit" :disabled="w.carryBusy" data-testid="carry-save">Save</Button>
      <Button small type="button" :disabled="w.carryBusy || carryKg == null" data-testid="carry-clear" @click="clear">Clear</Button>
    </span>
    <span v-if="local || w.carryError" class="err" role="alert" data-testid="carry-error">{{ local ?? w.carryError }}</span>
  </form>
</template>

<style scoped>
.carry { display: inline-flex; flex-direction: column; gap: 4px; }
.lbl { font-size: 13px; font-weight: 600; color: var(--ink-secondary); }
.row { display: inline-flex; gap: var(--space-2); align-items: center; }
.inp { min-height: 44px; width: 7rem; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink); padding: 0 var(--space-3); font: inherit; }
.inp:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.err { color: var(--danger); font-size: 13px; }
</style>
