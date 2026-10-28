<script setup lang="ts">
import { onMounted, ref } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Segmented from '@/components/ui/Segmented.vue'
import Icons from '@/components/ui/Icons.vue'
import { api } from '@/api'
import type { WeatherSettings } from '@/api/types'

// Opt-in weather lookup. Off by default; off also deletes everything that was fetched.
const w = ref<WeatherSettings | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)
const choice = ref<'off' | 'on'>('off')

async function load() {
  try {
    const { data } = await api.GET('/api/v1/settings/weather')
    if (data) {
      w.value = data
      choice.value = data.enabled ? 'on' : 'off'
    }
  } catch {
    error.value = 'Weather settings could not load.'
  }
}
onMounted(load)

async function set(v: 'off' | 'on') {
  if (busy.value || !w.value || (v === 'on') === w.value.enabled) return
  busy.value = true
  error.value = null
  try {
    const { data } = await api.PUT('/api/v1/settings/weather', { body: { enabled: v === 'on' } })
    if (data) w.value = data
    else error.value = 'That change did not save. Try again.'
  } catch {
    error.value = 'That change did not save. Check your connection.'
  } finally {
    busy.value = false
    choice.value = w.value?.enabled ? 'on' : 'off'
  }
}
</script>

<template>
  <GlassPanel id="weather" class="panel" role="group" aria-label="Weather lookup" data-testid="weather-settings">
    <h2 class="row-title">Weather lookup</h2>
    <p class="row-meta">
      Your watch records temperature and humidity at the start of most outdoor runs, and Strydr always uses those.
      Turn this on to add wind, rain, cloud and feels-like temperature, and to fill runs your watch missed.
    </p>
    <Segmented
      :model-value="choice"
      label="Weather lookup"
      :options="[{ label: 'Off', value: 'off', testid: 'weather-off' }, { label: 'On', value: 'on', testid: 'weather-on' }]"
      @update:model-value="set"
    />
    <p class="row-meta privacy">
      <Icons name="info" :size="14" />
      <span>
        What is sent: an area of about 11 km around where a run starts, outside your privacy zones, and the date. Never your route,
        start time, heart rate or name. It goes to {{ w?.provider_host ?? 'Open-Meteo' }}, which sees this server's address.
        Turning it off deletes everything fetched.
      </span>
    </p>
    <p v-if="w?.enabled" class="row-meta" role="status" data-testid="weather-counts">
      {{ w.fetched }} {{ w.fetched === 1 ? 'run has' : 'runs have' }} weather<template v-if="w.unavailable">, {{ w.unavailable }} could not be looked up yet</template><template v-if="w.skipped">, {{ w.skipped }} {{ w.skipped === 1 ? 'is' : 'are' }} entirely inside a privacy zone</template>.
    </p>
    <p v-if="error" class="err" role="alert">{{ error }}</p>
    <p class="row-meta credit">Weather data by <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo.com</a> (CC BY 4.0).</p>
  </GlassPanel>
</template>

<style scoped>
.panel { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.panel h2, .panel p { margin: 0; }
.panel h2 { font-family: var(--font-display); font-size: 17px; }
.panel :deep(.seg) { align-self: flex-start; }
.privacy { display: flex; gap: var(--space-2); align-items: flex-start; }
.privacy :deep(svg) { flex: none; margin-top: 3px; }
.credit { color: var(--ink-muted); }
.credit a { color: inherit; }
.err { color: var(--danger); }
</style>
