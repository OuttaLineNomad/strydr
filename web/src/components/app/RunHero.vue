<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Icons from '@/components/ui/Icons.vue'
import HeroStat from './HeroStat.vue'
import { vPress } from '@/directives/press'
import { MAP_STYLE, drawRoute, lngLatBounds, loadMapLibre } from '@/lib/map'
import type { DisplayGeometry } from '@/api/types'

// The run's first screen: the route on a full-bleed light map, the headline
// numbers laid over a dark scrim at its foot. Scrolling drifts the map slower
// than the page while the content below rises over it. "Explore map" hands the
// map to the pointer; until then it never steals the page's scroll.
const props = defineProps<{
  geometry: DisplayGeometry | null
  title: string
  date: string
  /** Weather in one line ("18 °C · Warm"); null hides it. */
  conditions?: string | null
  /** Last night's sleep in one line ("7h 32m sleep"); null hides it. */
  sleep?: string | null
  /** Extra weight carried in one line ("Carrying 25 lb"); null hides it. */
  carry?: string | null
  stats: { label: string; value: string | null; unit?: string }[]
}>()

const hero = ref<HTMLElement | null>(null)
const mapEl = ref<HTMLDivElement | null>(null)
const overlay = ref<HTMLElement | null>(null)
const failed = ref(false)
const exploring = ref(false)
const scrollY = ref(0)
const hasMap = computed(() => !!props.geometry && !failed.value)
let map: import('maplibre-gl').Map | null = null
let raf = 0

const reduced = typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    scrollY.value = window.scrollY
  })
}
const heroH = computed(() => hero.value?.offsetHeight ?? 700)
const mapShift = computed(() => (reduced || exploring.value ? 0 : Math.min(scrollY.value, heroH.value) * 0.35))
const overlayFade = computed(() => (reduced ? 1 : Math.max(0, 1 - scrollY.value / (heroH.value * 0.55))))

const HANDLERS = ['dragPan', 'scrollZoom', 'touchZoomRotate', 'doubleClickZoom', 'boxZoom', 'keyboard'] as const
function setInteractive(on: boolean) {
  if (!map) return
  for (const h of HANDLERS) (on ? map[h].enable() : map[h].disable())
}
function fitPadding() {
  const css = getComputedStyle(hero.value!)
  const left = parseFloat(css.getPropertyValue('--hero-inset')) || 24
  // The map layer runs past the hero's foot for the parallax; that overhang is hidden too.
  const overhang = (mapEl.value?.offsetHeight ?? 0) - (hero.value?.offsetHeight ?? 0)
  return { top: 96, right: 48, left: left + 24, bottom: (overlay.value?.offsetHeight ?? 260) + 56 + Math.max(0, overhang) }
}
function toggleExplore() {
  exploring.value = !exploring.value
  setInteractive(exploring.value)
  if (!exploring.value && map && props.geometry) map.fitBounds(lngLatBounds(props.geometry), { padding: fitPadding(), duration: 600 })
}

onMounted(async () => {
  window.addEventListener('scroll', onScroll, { passive: true })
  const g = props.geometry
  if (!g || !mapEl.value) return
  try {
    const maplibregl = await loadMapLibre()
    const line = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#ff5a36'
    const m = new maplibregl.Map({
      container: mapEl.value,
      style: MAP_STYLE,
      bounds: lngLatBounds(g),
      fitBoundsOptions: { padding: fitPadding(), animate: false },
      attributionControl: { compact: true },
    })
    map = m
    setInteractive(false)
    m.on('load', () => drawRoute(maplibregl, m, g, line, 5))
    m.on('error', () => {
      /* a missing tile leaves the route drawn; nothing to surface per tile */
    })
  } catch {
    failed.value = true
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  if (raf) cancelAnimationFrame(raf)
  map?.remove()
  map = null
})
</script>

<template>
  <section ref="hero" class="hero" :class="{ 'hero--plain': !hasMap, exploring }" aria-label="Run summary" data-testid="run-hero">
    <div class="backdrop">
      <div v-if="geometry && !failed" class="map-layer" :style="{ transform: `translate3d(0, ${mapShift}px, 0)` }">
        <div ref="mapEl" class="map" data-testid="route-map" role="img" aria-label="Map of this route. Any part inside a privacy zone is hidden." />
      </div>
      <div class="scrim" aria-hidden="true" />
    </div>

    <div class="top">
      <slot name="start" />
      <div class="top-end">
        <slot name="end" />
        <button v-if="hasMap" v-press type="button" class="btn btn-glass btn-sm" :aria-pressed="exploring" data-testid="explore-map" @click="toggleExplore">
          <Icons :name="exploring ? 'check' : 'routes'" :size="16" /> {{ exploring ? 'Done' : 'Explore map' }}
        </button>
      </div>
    </div>

    <div ref="overlay" class="overlay" :style="{ opacity: exploring ? 0 : overlayFade }">
      <h1 class="title">{{ title }}</h1>
      <p class="date">{{ date }}<template v-if="!geometry"> · No route recorded</template><template v-else-if="failed"> · The map could not load</template></p>
      <div v-if="conditions || sleep || carry" class="chips">
        <p v-if="conditions" class="cond" data-testid="hero-conditions"><Icons name="sun" :size="16" /> {{ conditions }}</p>
        <p v-if="sleep" class="cond" data-testid="hero-sleep"><Icons name="moon" :size="16" /> {{ sleep }}</p>
        <p v-if="carry" class="cond" data-testid="hero-carry"><Icons name="plus" :size="16" /> {{ carry }}</p>
      </div>
      <dl class="stats">
        <HeroStat v-for="s in stats" :key="s.label" :label="s.label" :value="s.value" :unit="s.unit" />
      </dl>
    </div>
  </section>
</template>

<style scoped>
.hero {
  /* Bleeds to the window's left, right and top edges from inside the page's padding. */
  --hero-inset: calc(var(--page-left) + var(--pad-x));
  --fade-h: 120px;
  position: relative;
  width: 100vw;
  margin: calc(-1 * var(--pad-top)) 0 0 calc(-1 * var(--hero-inset));
  height: max(560px, min(82svh, 860px));
  overflow: hidden;
  isolation: isolate;
}
.hero--plain { height: max(420px, min(56svh, 600px)); }
.hero--plain .scrim { background: color-mix(in srgb, var(--accent) 62%, #16181d); }
.map-layer { position: absolute; inset: 0 0 -12% 0; will-change: transform; }
/* The map and its scrim dissolve into the page at the hero's foot instead of stopping on a hard edge;
   the cards that rise over the foot sit in that fade. The mask is on a fixed frame, so the drifting map
   never reaches a hard edge either. */
.backdrop {
  position: absolute; inset: 0; overflow: hidden;
  -webkit-mask-image: linear-gradient(180deg, #000 calc(100% - var(--fade-h)), transparent 100%);
  mask-image: linear-gradient(180deg, #000 calc(100% - var(--fade-h)), transparent 100%);
}
.map { position: absolute; inset: 0; }
.scrim {
  position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(180deg, rgba(10, 12, 16, 0.22) 0%, rgba(10, 12, 16, 0) 16%, rgba(10, 12, 16, 0) 38%, rgba(10, 12, 16, 0.6) 58%, rgba(10, 12, 16, 0.88) 86%, rgba(10, 12, 16, 0.88) 100%);
  transition: opacity var(--dur-morph) var(--ease-settle);
}
.exploring .scrim { opacity: 0; }
.exploring .backdrop { -webkit-mask-image: none; mask-image: none; }
.top {
  position: absolute; z-index: 2; left: var(--hero-inset); right: var(--pad-x); top: calc(var(--pad-top) + env(safe-area-inset-top, 0px));
  display: flex; justify-content: space-between; align-items: center; gap: var(--space-3);
}
.top {
  /* The map is always light, so its controls are light glass with dark ink in both themes. */
  --glass-fill: rgba(255, 255, 255, 0.72);
  --glass-border: rgba(255, 255, 255, 0.85);
  --glass-specular: rgba(255, 255, 255, 0.95);
  --ink: #16181d;
}
.top-end { display: flex; gap: var(--space-2); flex-wrap: wrap; justify-content: flex-end; }
.overlay {
  position: absolute; z-index: 1; left: var(--hero-inset); right: var(--pad-x);
  /* Clears the first row of cards, which rises 56px over the hero's foot. */
  bottom: calc(56px + var(--space-10));
  color: #fff;
  transition: opacity var(--dur-morph) var(--ease-settle);
}
.exploring .overlay { pointer-events: none; }
.title { margin: 0; font-family: var(--font-display); font-weight: 700; font-size: 40px; line-height: 44px; letter-spacing: -0.02em; color: #fff; }
.date { margin: var(--space-1) 0 0; font-size: 15px; color: rgba(255, 255, 255, 0.86); }
.chips { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-2); }
.cond { margin: 0; display: inline-flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 600; color: #fff; padding: 4px 12px; border-radius: 999px; background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.28); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); }
.stats { margin: var(--space-5) 0 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4) var(--space-5); max-width: 980px; }
@media (min-width: 1080px) {
  .title { font-size: 56px; line-height: 60px; }
  .stats { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: var(--space-6); }
}
.overlay > * { animation: rise .7s var(--ease-settle) both; }
.overlay > :nth-child(2) { animation-delay: 60ms; }
.overlay > :nth-child(3) { animation-delay: 120ms; }
.overlay > :nth-child(4) { animation-delay: 180ms; }
.hero :deep(.maplibregl-ctrl-bottom-right) { bottom: calc(56px + var(--space-2)); }
</style>
