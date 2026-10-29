<script setup lang="ts">
import { onMounted } from 'vue'
import RunsRoutesSwitch from '@/components/app/RunsRoutesSwitch.vue'
import WorkoutList from '@/components/app/WorkoutList.vue'
import { useWorkoutsStore } from '@/stores/workouts'

const w = useWorkoutsStore()
onMounted(() => w.loadList({ type: 'run', page: 0 }))
</script>

<template>
  <header class="title-row">
    <div>
      <h1 class="page-title">Runs</h1>
      <p class="page-sub">Your runs, newest first. Walks and hikes are under Other activities.</p>
    </div>
    <div class="controls">
      <RunsRoutesSwitch current="runs" />
    </div>
  </header>

  <WorkoutList empty="You have no runs here yet." />
</template>

<style scoped>
.controls { display: flex; gap: var(--space-3); flex-wrap: wrap; align-items: center; }
@media (min-width: 1080px) { .controls { flex-wrap: nowrap; } }
</style>
