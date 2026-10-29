<script setup lang="ts">
import Segmented from '@/components/ui/Segmented.vue'
import { useWorkoutsStore } from '@/stores/workouts'
import type { WorkoutType } from '@/api/types'

defineProps<{ workoutId: string; type: WorkoutType }>()
const w = useWorkoutsStore()
const options: { label: string; value: WorkoutType; testid: string }[] = [
  { label: 'Run', value: 'run', testid: 'type-run' },
  { label: 'Walk', value: 'walk', testid: 'type-walk' },
  { label: 'Hike', value: 'hike', testid: 'type-hike' },
]
</script>

<template>
  <div class="type" :aria-busy="w.typeBusy">
    <Segmented
      :model-value="type"
      :options="options"
      label="Workout type"
      @update:model-value="(v: WorkoutType) => v !== type && !w.typeBusy && w.setType(workoutId, v)"
    />
    <span v-if="w.updating" class="upd" role="status" data-testid="type-updating">Updating stats…</span>
    <span v-if="w.typeError" class="err" role="alert" data-testid="type-error">{{ w.typeError }}</span>
  </div>
</template>

<style scoped>
.type { display: inline-flex; flex-direction: column; gap: 4px; }
.upd { color: var(--ink-secondary); font-size: 13px; }
.err { color: var(--danger); font-size: 13px; }
</style>
