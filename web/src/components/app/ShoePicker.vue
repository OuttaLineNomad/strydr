<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useShoesStore } from '@/stores/shoes'
import { useWorkoutsStore } from '@/stores/workouts'
import type { WorkoutShoe } from '@/api/types'

const props = defineProps<{ workoutId: string; shoe: WorkoutShoe | null; chosen: boolean }>()
const shoes = useShoesStore()
const w = useWorkoutsStore()
onMounted(() => {
  if (!shoes.shoes.length) shoes.load()
})

const DEFAULT = 'default'
const NONE = 'none'

// Every active shoe, plus the current one even when retired or when the list has not loaded.
const options = computed(() => {
  const list = shoes.shoes.filter((x) => !x.retired || x.id === props.shoe?.id).map((x) => ({ id: x.id, name: x.retired ? `${x.name} (retired)` : x.name }))
  const cur = props.shoe
  if (cur && !list.some((o) => o.id === cur.id)) list.push({ id: cur.id, name: cur.retired ? `${cur.name} (retired)` : cur.name })
  return list
})
// Not chosen follows the default; chosen shows its shoe, or none.
const value = computed(() => (!props.chosen ? DEFAULT : props.shoe ? String(props.shoe.id) : NONE))

function onChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  const el = e.target as HTMLSelectElement
  const done = v === DEFAULT ? w.clearShoe(props.workoutId) : w.saveShoe(props.workoutId, v === NONE ? null : Number(v))
  // On failure the shown shoe is unchanged, so put the control back.
  done.then((ok) => {
    if (!ok) el.value = value.value
  })
}
</script>

<template>
  <label class="picker">
    <span class="lbl">Shoe</span>
    <select class="sel" :value="value" :disabled="w.shoeBusy" aria-label="Shoe" data-testid="shoe-picker" @change="onChange">
      <option v-for="o in options" :key="o.id" :value="String(o.id)">{{ o.name }}</option>
      <option :value="NONE">No shoe</option>
      <option :value="DEFAULT" data-testid="shoe-use-default">Use default</option>
    </select>
    <span class="hint" data-testid="shoe-current">{{ shoe ? `${shoe.name}${shoe.retired ? ' (retired)' : ''}${shoe.source === 'default' ? ' (default)' : ''}` : 'No shoe' }}</span>
    <span v-if="shoes.error" class="err" role="alert" data-testid="shoe-list-error">{{ shoes.error }}</span>
    <span v-if="w.shoeError" class="err" role="alert" data-testid="shoe-error">{{ w.shoeError }}</span>
  </label>
</template>

<style scoped>
.picker { display: inline-flex; flex-direction: column; gap: 4px; }
.picker { min-width: 0; }
.lbl { font-size: 13px; font-weight: 600; color: var(--ink-secondary); }
.sel { min-height: 44px; width: 100%; max-width: 22rem; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: var(--surface-1); color: var(--ink); padding: 0 var(--space-3); font: inherit; }
.hint { font-size: 13px; color: var(--ink-secondary); }
.sel:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.err { color: var(--danger); font-size: 13px; }
</style>
