<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import { useStreakStore } from '@/stores/streak'
import { formatShortDate } from '@/lib/format'

// The weekly home-workout streak: a figure, 8 squares and one coach sentence. No badges, no scolding.
const props = defineProps<{ compact?: boolean }>()
const store = useStreakStore()
onMounted(() => store.load())

const d = computed(() => store.data)
const figure = computed(() => `${d.value?.weeks ?? 0} ${d.value?.weeks === 1 ? 'week' : 'weeks'}`)
const sentence = computed(() => {
  const x = d.value
  if (!x) return ''
  if (x.this_week) return 'This week counts.'
  if (x.weeks >= 1) return 'This week: not yet. One round keeps it going.'
  if (x.last_streak >= 1) return `Last streak: ${x.last_streak} ${x.last_streak === 1 ? 'week' : 'weeks'}. Start again this week.`
  return 'Do one round this week to start a streak.'
})
const squares = computed(() => (d.value?.recent ?? []).map((w, i, all) => ({
  key: w.week_start,
  counted: w.counted,
  current: i === all.length - 1,
  name: `Week of ${formatShortDate(w.week_start)}: ${w.counted ? 'counted' : i === all.length - 1 ? 'this week, not yet' : 'missed'}`,
})))
</script>

<template>
  <component
    :is="props.compact ? RouterLink : 'div'"
    v-if="d || (!props.compact && store.error)"
    v-bind="props.compact ? { to: '/workouts', 'aria-label': `Weekly streak: ${figure} in a row. Open Workouts` } : {}"
    class="wrap"
    :class="{ 'wrap--compact': props.compact }"
  >
    <GlassPanel v-if="d" class="streak" :class="{ 'streak--compact': props.compact }" role="group" aria-label="Weekly streak" data-testid="streak">
      <div class="head">
        <span class="num" data-testid="streak-figure">{{ figure }}</span>
        <span class="in-a-row">in a row</span>
      </div>
      <ul class="squares" data-testid="streak-squares">
        <li v-for="q in squares" :key="q.key">
          <span class="sq" :class="{ 'sq--on': q.counted, 'sq--now': q.current && !q.counted }" role="img" :aria-label="q.name" data-testid="streak-square" />
        </li>
      </ul>
      <p class="sentence" data-testid="streak-sentence">{{ sentence }}</p>
    </GlassPanel>
    <p v-else class="err" role="alert" data-testid="streak-error">{{ store.error }}</p>
  </component>
</template>

<style scoped>
.wrap { display: block; color: var(--ink); text-decoration: none; }
.wrap--compact:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 16px; }
.streak { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.streak--compact { padding: var(--space-4) var(--space-5); gap: var(--space-2); }
.head { display: flex; align-items: baseline; gap: var(--space-2); }
.num { font-family: var(--font-display); font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -.02em; font-size: var(--metric-lg-size); line-height: var(--metric-lg-leading); }
.streak--compact .num { font-size: var(--metric-sm-size); line-height: var(--metric-sm-leading); }
.in-a-row { font-size: 15px; color: var(--ink-secondary); }
.squares { list-style: none; margin: 0; padding: 0; display: flex; gap: var(--space-2); }
.sq { display: block; width: 28px; height: 28px; border-radius: 6px; border: 2px solid var(--ink-muted); box-sizing: border-box; }
.streak--compact .sq { width: 22px; height: 22px; }
.sq--on { background: var(--ink); border-color: var(--ink); }
.sq--now { border-color: var(--accent); border-style: dashed; }
.sentence { margin: 0; font-size: 15px; color: var(--ink); }
.err { margin: 0; color: var(--danger); }
</style>
