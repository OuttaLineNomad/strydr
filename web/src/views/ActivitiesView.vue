<script setup lang="ts">
import { onMounted } from 'vue'
import Segmented from '@/components/ui/Segmented.vue'
import WorkoutList from '@/components/app/WorkoutList.vue'
import { useWorkoutsStore } from '@/stores/workouts'

const w = useWorkoutsStore()
const ALL = 'walk,hike'
onMounted(() => w.loadList({ type: ALL, page: 0 }))

const filters = [
  { label: 'All', value: ALL },
  { label: 'Walks', value: 'walk' },
  { label: 'Hikes', value: 'hike' },
]
</script>

<template>
  <header class="title-row">
    <div>
      <h1 class="page-title">Other activities</h1>
      <p class="page-sub">Your walks and hikes, newest first.</p>
    </div>
    <div class="controls">
      <Segmented
        :model-value="w.type ?? ALL"
        :options="filters"
        label="Activity type"
        @update:model-value="(v: string) => w.loadList({ type: v, page: 0 })"
      />
    </div>
  </header>

  <WorkoutList from="activities" empty="You have no walks or hikes here yet." />
</template>

<style scoped>
.controls { display: flex; gap: var(--space-3); flex-wrap: wrap; align-items: center; }
@media (min-width: 1080px) { .controls { flex-wrap: nowrap; } }
</style>
