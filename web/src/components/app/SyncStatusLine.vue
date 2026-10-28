<script setup lang="ts">
import { computed } from 'vue'
import Icons from '@/components/ui/Icons.vue'
import type { SyncStatus } from '@/api/types'
import { formatInstant } from '@/lib/format'

const props = defineProps<{ sync: SyncStatus | null; tz?: string }>()

const last = computed(() => (props.sync?.last_processed_at ? formatInstant(props.sync.last_processed_at, props.tz) : null))
const held = computed(() => props.sync?.quarantined.length ?? 0)
</script>

<template>
  <div class="sync" data-testid="sync-status">
    <template v-if="!sync">
      <span class="muted">Sync status is not available.</span>
    </template>
    <template v-else>
      <span v-if="last" class="muted">Last synced {{ last }}.</span>
      <span v-else class="muted">Nothing has synced yet.</span>
      <span v-if="sync.stale" class="pill pill--tertiary" data-testid="sync-stale" role="status">
        <Icons name="warning" :size="14" />
        Stale: no new data in over {{ sync.stale_after_days }} {{ sync.stale_after_days === 1 ? 'day' : 'days' }}
      </span>
      <span v-if="held" class="muted">{{ held }} {{ held === 1 ? 'upload needs' : 'uploads need' }} a look.</span>
    </template>
  </div>
</template>

<style scoped>
.sync { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); font-size: var(--body-sm-size); }
.muted { color: var(--ink-secondary); }
.pill { height: auto; min-height: 24px; white-space: normal; padding-block: 2px; }
</style>
