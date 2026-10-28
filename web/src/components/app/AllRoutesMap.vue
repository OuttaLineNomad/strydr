<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import { api } from '@/api'
import type { RouteMap } from '@/api/types'
import { MAP_STYLE, loadMapLibre, lonLat } from '@/lib/map'
import { vPress } from '@/directives/press'

// Everywhere you have been: every workout's clipped track on one light map. Lines are
// translucent, so the roads you repeat build up brighter. Tap a line to open that workout.
// Zoomed out, each place you have run is a counted dot, and the place chips fly to each one.
const router = useRouter()
const el = ref<HTMLDivElement | null>(null)
const data = ref<RouteMap | null>(null)
const state = ref<'loading' | 'ready' | 'empty' | 'error'>('loading')
let map: import('maplibre-gl').Map | null = null

// Places: workouts whose starts lie within about 30 km of each other. No names: naming a place would mean
// asking a geocoding service, and nothing about your location leaves the server for that.
const PLACE_DEG = 0.3
const places = computed(() => {
  const out: { lines: RouteMap['lines']; lat: number; lon: number }[] = []
  for (const l of data.value?.lines ?? []) {
    const [lat, lon] = l.display_geometry.start
    const p = out.find((x) => Math.abs(x.lat - lat) < PLACE_DEG && Math.abs(x.lon - lon) < PLACE_DEG)
    if (p) p.lines.push(l)
    else out.push({ lines: [l], lat, lon })
  }
  return out
    .map((p) => {
      const dates = p.lines.map((l) => l.local_date).sort()
      const span = (d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' })
      const a = span(dates[0]!), b = span(dates.at(-1)!)
      return { box: bounds(p.lines), n: p.lines.length, when: a === b ? a : `${a} – ${b}`, last: dates.at(-1)! }
    })
    .sort((x, y) => y.last.localeCompare(x.last))
})
const active = ref<number | null>(null)
function flyTo(i: number | null) {
  if (!map || !data.value) return
  active.value = i
  map.fitBounds(i == null ? bounds(data.value.lines) : places.value[i]!.box, { padding: 48, maxZoom: 15, duration: 900 })
}

const counts = computed(() => {
  const lines = data.value?.lines ?? []
  return { runs: lines.filter((l) => l.type === 'run').length, other: lines.filter((l) => l.type !== 'run').length }
})

type Box = [[number, number], [number, number]]
function bounds(lines: RouteMap['lines']): Box {
  let [s, w, n, e] = [90, 180, -90, -180]
  for (const l of lines) {
    const [a, b, c, d] = l.display_geometry.bounds
    s = Math.min(s, a); w = Math.min(w, b); n = Math.max(n, c); e = Math.max(e, d)
  }
  return [[w, s], [e, n]]
}

onMounted(async () => {
  try {
    const { data: d } = await api.GET('/api/v1/routes/map')
    if (!d) throw new Error('no data')
    data.value = d as RouteMap
  } catch {
    state.value = 'error'
    return
  }
  if (!data.value.lines.length || !el.value) {
    state.value = 'empty'
    return
  }
  try {
    const maplibregl = await loadMapLibre()
    const root = getComputedStyle(document.documentElement)
    const accent = root.getPropertyValue('--accent').trim() || '#ff5a36'
    const other = root.getPropertyValue('--chart-elevation').trim() || '#3b82f6'
    const m = new maplibregl.Map({
      container: el.value,
      style: MAP_STYLE,
      // Open on the most recent place; "Everywhere" zooms out to all of them.
      bounds: places.value.length > 1 ? places.value[0]!.box : bounds(data.value.lines),
      fitBoundsOptions: { padding: 48, animate: false, maxZoom: 15 },
      attributionControl: { compact: true },
      cooperativeGestures: true, // the page keeps the scroll; two fingers or a modifier move the map
    })
    map = m
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('load', () => {
      m.addSource('all', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: data.value!.lines.map((l) => ({
            type: 'Feature',
            properties: { id: l.workout_id, run: l.type === 'run' },
            geometry: { type: 'MultiLineString', coordinates: l.display_geometry.segments.map((s) => s.map(lonLat)) },
          })),
        },
      })
      m.addLayer({ id: 'all-casing', type: 'line', source: 'all', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#ffffff', 'line-width': 5, 'line-opacity': 0.5 } })
      m.addLayer({ id: 'all-lines', type: 'line', source: 'all', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': ['case', ['get', 'run'], accent, other], 'line-width': 3, 'line-opacity': 0.42 } })
      m.addSource('starts', {
        type: 'geojson', cluster: true, clusterRadius: 40, clusterMaxZoom: 10,
        data: {
          type: 'FeatureCollection',
          features: data.value!.lines.map((l) => ({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: lonLat(l.display_geometry.start) } })),
        },
      })
      const dot = { 'circle-color': accent, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3 }
      m.addLayer({ id: 'starts-cluster', type: 'circle', source: 'starts', maxzoom: 11, filter: ['has', 'point_count'],
        paint: { ...dot, 'circle-radius': ['interpolate', ['linear'], ['get', 'point_count'], 2, 14, 20, 24] } })
      m.addLayer({ id: 'starts-count', type: 'symbol', source: 'starts', maxzoom: 11, filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Bold'], 'text-size': 13 },
        paint: { 'text-color': '#ffffff' } })
      m.addLayer({ id: 'starts-one', type: 'circle', source: 'starts', maxzoom: 11, filter: ['!', ['has', 'point_count']],
        paint: { ...dot, 'circle-radius': 8 } })
      for (const id of ['starts-cluster', 'starts-one']) {
        m.on('click', id, (e) => {
          const f = e.features?.[0]
          if (f?.geometry.type === 'Point') m.easeTo({ center: f.geometry.coordinates as [number, number], zoom: Math.max(m.getZoom() + 3, 12), duration: 800 })
        })
        m.on('mouseenter', id, () => { m.getCanvas().style.cursor = 'pointer' })
        m.on('mouseleave', id, () => { m.getCanvas().style.cursor = '' })
      }
      m.on('click', 'all-lines', (e) => {
        const id = e.features?.[0]?.properties?.id
        if (id) router.push({ name: 'run-detail', params: { id: String(id) } })
      })
      m.on('mouseenter', 'all-lines', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'all-lines', () => { m.getCanvas().style.cursor = '' })
      state.value = 'ready'
    })
  } catch {
    state.value = 'error'
  }
})
onBeforeUnmount(() => {
  map?.remove()
  map = null
})
</script>

<template>
  <GlassPanel class="all" role="group" aria-label="Map of everywhere you have run" data-testid="all-routes-map">
    <div class="head">
      <div>
        <h2 class="row-title">Everywhere you have been</h2>
        <p class="row-meta">
          <template v-if="data">{{ counts.runs }} {{ counts.runs === 1 ? 'run' : 'runs' }}<template v-if="counts.other"> and {{ counts.other }} walks and hikes</template>. Roads you repeat show brighter. Parts inside a privacy zone are hidden.</template>
          <template v-else>Loading your map…</template>
        </p>
      </div>
      <ul v-if="counts.other" class="legend" aria-label="Legend">
        <li><i class="sw sw--run" /> Runs</li>
        <li><i class="sw sw--other" /> Walks and hikes</li>
      </ul>
    </div>
    <div v-if="places.length > 1" class="places" role="group" aria-label="Places you have run">
      <button v-press type="button" class="chip" :class="{ on: active === null }" :aria-pressed="active === null" @click="flyTo(null)">Everywhere</button>
      <button v-for="(p, i) in places" :key="i" v-press type="button" class="chip" :class="{ on: active === i }" :aria-pressed="active === i" @click="flyTo(i)">
        {{ p.n }} {{ p.n === 1 ? 'workout' : 'workouts' }} · {{ p.when }}
      </button>
    </div>
    <div class="frame">
      <div v-show="state !== 'empty' && state !== 'error'" ref="el" class="map" role="img" aria-label="All your routes on one map" />
      <p v-if="state === 'empty'" class="na" data-testid="all-routes-empty">Your map fills in once a workout with GPS arrives.</p>
      <p v-else-if="state === 'error'" class="na" role="alert">The map could not load. Try again in a moment.</p>
    </div>
  </GlassPanel>
</template>

<style scoped>
.all { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-4); }
.head { display: flex; justify-content: space-between; align-items: flex-end; gap: var(--space-3); flex-wrap: wrap; }
.head h2, .head p { margin: 0; }
.head h2 { font-family: var(--font-display); font-size: 17px; }
.legend { list-style: none; margin: 0; padding: 0; display: flex; gap: var(--space-4); font-size: var(--body-sm-size); color: var(--ink-secondary); }
.legend li { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 18px; height: 4px; border-radius: 2px; display: inline-block; }
.sw--run { background: var(--accent); }
.sw--other { background: var(--chart-elevation); }
.places { display: flex; gap: var(--space-2); overflow-x: auto; scrollbar-width: none; margin: 0 calc(-1 * var(--space-1)); padding: 2px var(--space-1); }
.chip {
  flex: none; height: 36px; padding: 0 14px; border-radius: var(--radius-full); border: 1px solid var(--divider);
  background: color-mix(in srgb, var(--surface-1) 70%, transparent); color: var(--ink-secondary); font: inherit; font-size: var(--body-sm-size); font-weight: 600; cursor: pointer;
  transition: background var(--dur-release) var(--ease-settle), color var(--dur-release) var(--ease-settle), transform var(--dur-release) var(--ease-glass);
}
.chip:hover { color: var(--ink); }
.chip:active { transform: scale(.95); }
.chip.on { background: color-mix(in srgb, var(--accent) 14%, var(--surface-2)); color: var(--accent-text); border-color: transparent; }
.chip:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.frame { position: relative; height: clamp(320px, 52svh, 560px); border-radius: var(--radius-md); overflow: hidden; background: color-mix(in srgb, var(--surface-2) 70%, transparent); }
.map { position: absolute; inset: 0; }
.na { margin: 0; position: absolute; inset: 0; display: grid; place-items: center; padding: var(--space-5); text-align: center; color: var(--ink-secondary); }
</style>
