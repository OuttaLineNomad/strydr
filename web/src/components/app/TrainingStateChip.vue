<script setup lang="ts">
import { computed } from 'vue'
import Icons, { type IconName } from '@/components/ui/Icons.vue'
import { formatLocalDate } from '@/lib/format'
import type { TrainingState } from '@/api/types'

const props = defineProps<{ state: TrainingState | null; since?: string | null }>()

// Neutral on purpose: a training state is a description, never a warning (FR-24c).
const ICON: Record<TrainingState, IconName> = { Building: 'arrow-up', Holding: 'minus', Easing: 'arrow-down', Overreaching: 'power' }
const SENTENCE: Record<TrainingState, string> = {
  Building: 'Your recent load is rising.',
  Holding: 'Your recent load is steady.',
  Easing: 'Your recent load is coming down.',
  Overreaching: 'Your recent load is well above your usual.',
}
const sentence = computed(() => (props.state ? SENTENCE[props.state] : null))
</script>

<template>
  <div class="state" data-testid="training-state">
    <span v-if="state" class="chip-state" :data-state="state">
      <Icons :name="ICON[state]" :size="24" /> {{ state }}
    </span>
    <span v-else class="chip-state na">Training state not available yet</span>
    <span v-if="sentence" class="row-meta">{{ sentence }}<template v-if="since"> Since {{ formatLocalDate(since) }}.</template></span>
  </div>
</template>

<style scoped>
.state { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
.chip-state { display: inline-flex; align-items: center; gap: var(--space-2); font-family: var(--font-display); color: var(--ink); font-weight: 700; font-size: 28px; line-height: 32px; letter-spacing: -.01em; }
.na { color: var(--ink-secondary); font-weight: 500; font-family: var(--font-body); font-size: var(--body-size); }
.state { flex-direction: column; align-items: flex-start; gap: var(--space-2); }
</style>
