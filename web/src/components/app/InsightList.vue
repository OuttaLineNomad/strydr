<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import InsightCard from './InsightCard.vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import { useInsightsStore } from '@/stores/insights'
import type { InsightOut } from '@/api/types'

// The feed arrives newest first. Paging appends the next page below.
const props = withDefaults(defineProps<{ run?: string; week?: string; pageSize?: number; title?: string; emptyText?: string }>(), {
  pageSize: 10,
  title: 'Insights',
  emptyText: 'No insights yet. They appear after your runs have synced.',
})

const store = useInsightsStore()
const items = ref<InsightOut[]>([])
const total = ref(0)
const loaded = ref(false)
const error = ref<string | null>(null)
const disclaimer = ref('Not medical advice.')

async function load(reset: boolean) {
  error.value = null
  const feed = await store.fetchFeed({ run: props.run, week: props.week, limit: props.pageSize, offset: reset ? 0 : items.value.length })
  loaded.value = true
  if (!feed) {
    error.value = 'Your insights could not load. Try again in a moment.'
    return
  }
  items.value = reset ? feed.items : [...items.value, ...feed.items]
  total.value = feed.total
  if (feed.disclaimer) disclaimer.value = feed.disclaimer
}

onMounted(() => load(true))
watch(() => [props.run, props.week], () => load(true))
</script>

<template>
  <section class="stack" :aria-label="title" data-testid="insight-list">
    <h2 class="section-title">{{ title }}</h2>
    <p v-if="error" class="err" role="alert" data-testid="insights-error">{{ error }}</p>
    <GlassPanel v-else-if="loaded && !items.length" class="empty"><p class="page-sub" data-testid="insights-empty">{{ emptyText }}</p></GlassPanel>
    <InsightCard v-for="i in items" :key="i.insight_key" :insight="i" />
    <Button v-if="items.length < total" small :disabled="store.feedBusy" data-testid="insights-more" @click="load(false)">
      {{ store.feedBusy ? 'Loading…' : `Show older insights (${total - items.length} more)` }}
    </Button>
    <p class="row-meta foot" data-testid="insights-disclaimer">Insights describe your training patterns. {{ disclaimer }}</p>
  </section>
</template>

<style scoped>
.head { margin: 0; }
.empty { padding: var(--space-5); }
.empty p { margin: 0; }
.foot { margin: 0; }
.err { margin: 0; color: var(--danger); }
</style>
