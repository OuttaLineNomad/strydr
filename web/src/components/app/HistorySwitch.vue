<script setup lang="ts">
import { useRouter } from 'vue-router'
import Segmented from '@/components/ui/Segmented.vue'
import { historyRoute, type HistoryPage } from '@/lib/historyNav'

const props = defineProps<{ current: HistoryPage }>()
const router = useRouter()

const options: { label: string; value: HistoryPage; testid: string }[] = [
  { label: 'Weeks', value: 'weeks', testid: 'history-weeks' },
  { label: 'Calendar', value: 'calendar', testid: 'history-calendar' },
  { label: 'Recap', value: 'recap', testid: 'history-recap' },
]
function choose(v: HistoryPage) {
  if (v !== props.current) router.replace(historyRoute(v))
}
</script>

<template>
  <div class="history-switch">
    <Segmented :options="options" :model-value="current" label="History view" @update:model-value="choose" />
  </div>
</template>

<style scoped>
.history-switch { margin-bottom: var(--space-3); }
/* the phone tab bar's breakpoint: on desktop the side menu has all three pages */
@media (min-width: 1080px) { .history-switch { display: none; } }
</style>
