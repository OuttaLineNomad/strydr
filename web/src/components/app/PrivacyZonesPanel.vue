<script setup lang="ts">
import { onMounted, ref } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import Icons from '@/components/ui/Icons.vue'
import ZonePicker from './ZonePicker.vue'
import { usePrefsStore } from '@/stores/prefs'

const prefs = usePrefsStore()
onMounted(() => prefs.loadZones())

const DEFAULT_RADIUS = 400
const radius = ref(DEFAULT_RADIUS)
// Held only until Add is pressed, then dropped. It is never shown as text.
const point = ref<{ lat: number; lon: number } | null>(null)

async function add() {
  if (!point.value) return
  if (await prefs.addZone(point.value.lat, point.value.lon, radius.value)) {
    point.value = null
    radius.value = DEFAULT_RADIUS
  }
}
</script>

<template>
  <GlassPanel class="panel" role="group" aria-label="Privacy zones" data-testid="privacy-zones">
    <h2 class="row-title">Privacy zones</h2>
    <p class="row-meta" data-testid="zones-caveat">
      A zone hides the part of any route that falls inside it, so your maps do not show where you start or finish.
      Zones reduce the risk of revealing where you live, but do not remove it. Your routes, times and pace around the zone can still hint at it.
    </p>
    <p class="row-meta">For safety, Strydr never shows a zone's location again after you add it.</p>

    <ul v-if="prefs.zones.length" class="zones" data-testid="zone-list">
      <li v-for="(z, i) in prefs.zones" :key="z.id" class="zone">
        <span data-testid="zone-label">Zone ({{ Math.round(z.radius_m) }} m)</span>
        <Button small :disabled="prefs.zonesBusy" :aria-label="`Delete zone ${i + 1}, ${Math.round(z.radius_m)} m`" data-testid="zone-delete" @click="prefs.deleteZone(z.id)">
          <Icons name="trash" :size="16" /> Delete
        </Button>
      </li>
    </ul>
    <p v-else class="row-meta" data-testid="zones-empty">You have no privacy zones.</p>

    <h3 class="chart-title">Add a zone</h3>
    <p class="row-meta">Tap the map where your home is. Then set the radius and add it.</p>
    <ZonePicker :radius-m="radius" :point="point" @pick="point = $event" />
    <label class="field">
      <span class="row-meta">Radius: {{ radius }} m</span>
      <input v-model.number="radius" type="range" min="100" max="2000" step="50" data-testid="zone-radius" />
    </label>
    <div class="actions">
      <Button variant="primary" :disabled="!point || prefs.zonesBusy" data-testid="zone-add" @click="add">Add zone</Button>
      <span v-if="point" class="row-meta" data-testid="zone-picked"><Icons name="check" :size="14" /> Point chosen</span>
    </div>
    <p v-if="prefs.zonesError" class="err" role="alert" data-testid="zones-error">{{ prefs.zonesError }}</p>
  </GlassPanel>
</template>

<style scoped>
.panel { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.panel h2, .panel h3, .panel p { margin: 0; }
.zones { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
.zone { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.field { display: flex; flex-direction: column; gap: var(--space-1); }
.actions { display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap; }
.err { color: var(--danger); }
</style>
