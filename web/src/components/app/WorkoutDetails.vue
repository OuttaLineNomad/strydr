<script setup lang="ts">
import GlassPanel from '@/components/ui/GlassPanel.vue'
import TypePicker from './TypePicker.vue'
import ShoePicker from './ShoePicker.vue'
import CarryField from './CarryField.vue'
import type { WorkoutShoe, WorkoutType } from '@/api/types'

// What the runner records about a workout, on a solid panel of its own rather than over the map:
// its type, the shoe it was run in and any extra weight carried.
defineProps<{ workoutId: string; type: WorkoutType; shoe: WorkoutShoe | null; shoeChosen: boolean; carryKg: number | null }>()
</script>

<template>
  <GlassPanel as="section" class="details" aria-labelledby="details-title" data-testid="workout-details">
    <h2 id="details-title" class="chart-title">About this workout</h2>
    <div class="fields">
      <div class="field">
        <span class="lbl">Type</span>
        <TypePicker :workout-id="workoutId" :type="type" />
      </div>
      <div class="field">
        <ShoePicker :workout-id="workoutId" :shoe="shoe" :chosen="shoeChosen" />
      </div>
      <div class="field">
        <CarryField :workout-id="workoutId" :carry-kg="carryKg" />
      </div>
    </div>
  </GlassPanel>
</template>

<style scoped>
.details { padding: var(--space-4) var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.details h2 { margin: 0; }
.fields { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-4); }
.field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.lbl { font-size: 13px; font-weight: 600; color: var(--ink-secondary); }
@media (min-width: 720px) {
  .fields { grid-template-columns: auto minmax(0, 1fr) auto; gap: var(--space-6); align-items: start; }
}
</style>
