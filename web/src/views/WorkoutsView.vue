<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import StreakBlock from '@/components/app/StreakBlock.vue'
import { usePlansStore } from '@/stores/plans'
import { useSettingsStore } from '@/stores/settings'
import { planSummary, lastLine } from '@/lib/plans'
import { useSessionsStore } from '@/stores/sessions'
import { unlockAudio } from '@/lib/useTone'
import { roundsText } from '@/lib/workoutEngine'
import type { SessionOut } from '@/api/types'

const store = usePlansStore()
const s = useSettingsStore()
const sessions = useSessionsStore()
onMounted(async () => {
  // A session that could not be saved on the phone is retried here, then the list reloads with its Last: line.
  await store.load()
  if ((await sessions.flush()) > 0) await store.load() // reload only if a kept session just synced
  recent.value = await sessions.list(undefined, 10)
})

const recent = ref<SessionOut[]>([])
function when(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

const confirming = ref<number | null>(null)
const plans = computed(() => [...store.plans].sort((a, b) => a.name.localeCompare(b.name)))

async function duplicate(id: number) {
  await store.duplicate(id)
}
async function remove(id: number) {
  if (await store.remove(id)) confirming.value = null
}
</script>

<template>
  <header class="title-row">
    <div>
      <h1 class="page-title">Workouts</h1>
      <p class="page-sub">Your saved kettlebell and bodyweight workouts.</p>
    </div>
    <div class="title-actions">
      <RouterLink to="/workouts/new?import=1" class="link" data-testid="from-video">From a video</RouterLink>
      <Button v-if="plans.length" variant="primary" to="/workouts/new" data-testid="new-workout">New workout</Button>
    </div>
  </header>

  <StreakBlock class="streak-block" />

  <p v-if="!store.loaded && !store.error" class="body" role="status" data-testid="workouts-loading">Loading workouts.</p>

  <GlassPanel v-else-if="store.error && !store.loaded" class="block" role="alert" data-testid="workouts-error">
    <p class="err">{{ store.error }}</p>
    <Button @click="store.load()">Retry</Button>
  </GlassPanel>

  <GlassPanel v-else-if="store.loaded && !plans.length" class="block" data-testid="workouts-empty">
    <h2 class="row-title">No workouts yet</h2>
    <p class="body">Write down a circuit once, and it is here every time you train.</p>
    <Button variant="primary" to="/workouts/new" data-testid="new-workout-empty">New workout</Button>
  </GlassPanel>

  <GlassPanel v-else-if="plans.length" class="list-panel" data-testid="workouts-list">
    <ul class="plans">
      <li v-for="p in plans" :key="p.id" class="plan" data-testid="plan-row">
        <div class="top">
          <div class="text">
            <h2 class="plan-name" data-testid="plan-name">{{ p.name }}</h2>
            <p class="body" data-testid="plan-summary">{{ planSummary(p, s.units) }}</p>
            <a v-if="p.video_url" :href="p.video_url" target="_blank" rel="noopener noreferrer" class="watch" data-testid="plan-video">Watch how</a>
          </div>
          <div class="start">
            <Button variant="primary" small class="startbtn" :to="`/workouts/${p.id}/run`" :aria-label="`Start ${p.name}`" data-testid="plan-start" @click="unlockAudio()">Start</Button>
          </div>
        </div>
        <p v-if="p.last_session" class="body last">
          <RouterLink :to="`/workouts/sessions/${p.last_session.id}`" class="link" data-testid="plan-last">{{ lastLine(p.last_session) }}</RouterLink>
        </p>

        <div v-if="confirming === p.id" class="actions" data-testid="plan-confirm">
          <span class="body">Delete {{ p.name }}? This cannot be undone.</span>
          <Button :disabled="store.busy" :aria-label="`Yes, delete ${p.name}`" data-testid="plan-confirm-yes" @click="remove(p.id)">Delete</Button>
          <Button :disabled="store.busy" data-testid="plan-confirm-cancel" @click="confirming = null">Keep</Button>
        </div>
        <div v-else class="actions">
          <Button class="act" :to="`/workouts/${p.id}/edit`" :aria-label="`Edit ${p.name}`" data-testid="plan-edit">Edit</Button>
          <Button class="act" :disabled="store.busy" :aria-label="`Duplicate ${p.name}`" data-testid="plan-duplicate" @click="duplicate(p.id)">Duplicate</Button>
          <button type="button" class="del" :aria-label="`Delete ${p.name}`" data-testid="plan-delete" @click="confirming = p.id">Delete</button>
        </div>
      </li>
    </ul>
    <p v-if="store.error" class="err pad" role="alert" data-testid="workouts-action-error">{{ store.error }}</p>
  </GlassPanel>

  <section v-if="recent.length" class="recent" aria-labelledby="recent-h" data-testid="recent-sessions">
    <h2 id="recent-h" class="section-title">Recent sessions</h2>
    <GlassPanel class="list-panel">
      <ul class="plans">
        <li v-for="x in recent" :key="x.id" class="plan session">
          <RouterLink :to="`/workouts/sessions/${x.id}`" class="session-link" data-testid="recent-row">
            <span class="plan-name">{{ x.plan.name }}</span>
            <span class="body">{{ when(x.start_utc) }} · {{ roundsText(x.rounds_done, x.partial_moves) }}</span>
          </RouterLink>
        </li>
      </ul>
    </GlassPanel>
  </section>
</template>

<style scoped>
.streak-block { margin-bottom: var(--space-4); }
.block { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); align-items: flex-start; }
.block h2, .block p { margin: 0; }
.body { margin: 0; color: var(--ink); font-size: var(--body-md-size, 16px); }
.list-panel { padding: 0; overflow: hidden; }
.plans { list-style: none; margin: 0; padding: 0; }
.plan { padding: var(--space-4) var(--space-5); display: flex; flex-direction: column; gap: var(--space-2); }
.plan + .plan { border-top: 1px solid var(--divider); }
.top { display: flex; gap: var(--space-3); align-items: flex-start; justify-content: space-between; }
.text { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.plan-name { font-family: var(--font-display); font-size: 20px; line-height: 26px; font-weight: 700; margin: 0; overflow-wrap: anywhere; }
.start { flex-shrink: 0; }
.startbtn { height: 44px; min-width: 44px; font-size: 15px; }
.last { color: var(--ink); }
.title-actions { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
.link { color: var(--accent-text); font-weight: 600; min-height: 44px; display: inline-flex; align-items: center; }
.recent { margin-top: var(--space-6); display: flex; flex-direction: column; gap: var(--space-3); }
.section-title { margin: 0; font-family: var(--font-display); font-size: 20px; line-height: 26px; font-weight: 700; }
.session { padding: 0; }
.session-link { display: flex; flex-direction: column; gap: 4px; padding: var(--space-4) var(--space-5); min-height: 44px; color: var(--ink); text-decoration: none; }
.session-link:focus-visible, .link:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.watch { color: var(--accent-text); font-weight: 600; min-height: 44px; display: inline-flex; align-items: center; width: fit-content; }
.actions { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-3); align-items: center; }
.act { height: 44px; padding: 0 var(--space-4); font-size: 15px; }
.del { min-height: 44px; padding: 0 var(--space-3); background: none; border: 0; font: inherit; font-weight: 600; color: var(--danger); cursor: pointer; }
.del:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 6px; }
.err { color: var(--danger); margin: 0; }
.pad { padding: 0 var(--space-5) var(--space-4); }
</style>
