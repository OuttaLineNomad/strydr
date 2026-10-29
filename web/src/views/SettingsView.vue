<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import Segmented from '@/components/ui/Segmented.vue'
import ShoesPanel from '@/components/app/ShoesPanel.vue'
import PrivacyZonesPanel from '@/components/app/PrivacyZonesPanel.vue'
import AiSettingsPanel from '@/components/app/AiSettingsPanel.vue'
import ThresholdsPanel from '@/components/app/ThresholdsPanel.vue'
import WeatherPanel from '@/components/app/WeatherPanel.vue'
import ImportPanel from '@/components/app/ImportPanel.vue'
import Icons from '@/components/ui/Icons.vue'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
import { hrmaxText } from '@/lib/profile'
import type { ProfileSettings } from '@/api/types'

const s = useSettingsStore()
const auth = useAuthStore()
const router = useRouter()

const form = reactive({
  units: 'imperial' as 'metric' | 'imperial',
  birthYear: '' as string,
  sex: '' as '' | 'male' | 'female',
  hrmaxOverride: '' as string,
  zones: ['', '', '', ''] as string[],
  homeTz: '',
})
const zonesTouched = ref(false)
const formError = ref<string | null>(null)
const saved = ref(false)

function fill() {
  const p = s.profile
  if (!p) return
  form.units = p.settings.units
  form.birthYear = p.settings.birth_year == null ? '' : String(p.settings.birth_year)
  form.sex = p.settings.sex ?? ''
  form.hrmaxOverride = p.settings.hrmax_override == null ? '' : String(p.settings.hrmax_override)
  const z = p.settings.zones ?? p.zone_bounds_pct
  form.zones = [0, 1, 2, 3].map((i) => (z[i] == null ? '' : String(z[i])))
  form.homeTz = p.settings.home_tz
  zonesTouched.value = false
}
onMounted(async () => {
  if (!s.profile) await s.load()
  fill()
})
// Refill only when a save lands, so typing is never overwritten by a poll.
watch(() => s.saving, (now, was) => { if (was && !now && !s.error) fill() })

const timeZones = (() => {
  try {
    return (Intl as unknown as { supportedValuesOf(k: string): string[] }).supportedValuesOf('timeZone')
  } catch {
    return [] as string[]
  }
})()
const tzOk = (tz: string) => {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz })
    return true
  } catch {
    return false
  }
}

const hrmaxLine = computed(() => hrmaxText(s.resolved))

function intOrNull(v: string, min: number, max: number, what: string): number | null {
  if (v.trim() === '') return null
  const n = Number(v)
  if (!Number.isInteger(n) || n < min || n > max) throw new Error(`${what} needs a whole number from ${min} to ${max}.`)
  return n
}

async function submit() {
  formError.value = null
  saved.value = false
  let body: ProfileSettings
  try {
    const birth = intOrNull(form.birthYear, 1900, 2100, 'Birth year')
    const hrmax = intOrNull(form.hrmaxOverride, 100, 230, 'HRmax override')
    let zones: number[] | null = s.profile?.settings.zones ?? null
    if (zonesTouched.value) {
      const z = form.zones.map(Number)
      if (form.zones.some((v) => v.trim() === '') || z.some((n) => !Number.isFinite(n) || n <= 0 || n > 100)) throw new Error('Each zone limit needs a percentage above 0 and up to 100.')
      if (z.some((n, i) => i > 0 && n <= z[i - 1]!)) throw new Error('Zone limits need to rise from zone 1 to zone 4.')
      zones = z
    }
    if (!form.homeTz.trim() || !tzOk(form.homeTz.trim())) throw new Error('Home time zone needs a name like America/Denver.')
    body = {
      units: form.units,
      birth_year: birth,
      sex: form.sex === '' ? null : form.sex,
      hrmax_override: hrmax,
      zones,
      home_tz: form.homeTz.trim(),
    }
  } catch (e) {
    formError.value = (e as Error).message
    return
  }
  saved.value = await s.save(body)
}

async function signOut() {
  await auth.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <header class="title-row">
    <div>
      <h1 class="page-title">Settings</h1>
      <p class="page-sub">Set how your numbers are shown and how your heart-rate zones are worked out.</p>
    </div>
  </header>

  <p v-if="s.recalculating" class="pill pill--tertiary status" role="status" data-testid="recalculating">
    <Icons name="sync" :size="14" /> Recalculating…
  </p>
  <p v-if="!s.profile && s.error" class="err" role="alert">{{ s.error }}</p>

  <form v-if="s.profile" class="form" novalidate @submit.prevent="submit">
    <div class="cards">
    <GlassPanel class="panel">
      <h2 class="row-title">Units</h2>
      <p class="row-meta">Stored data stays metric. This only changes what you see.</p>
      <Segmented
        v-model="form.units"
        label="Units"
        :options="[{ label: 'Miles', value: 'imperial' }, { label: 'Kilometres', value: 'metric' }]"
      />
    </GlassPanel>

    <GlassPanel class="panel">
      <h2 class="row-title">About you</h2>
      <label class="field">
        <span class="row-meta">Birth year</span>
        <input v-model="form.birthYear" class="input" inputmode="numeric" data-testid="birth-year" />
      </label>
      <label class="field">
        <span class="row-meta">Sex</span>
        <select v-model="form.sex" class="input">
          <option value="">Prefer not to say</option>
          <option value="female">Female</option>
          <option value="male">Male</option>
        </select>
      </label>
      <label class="field">
        <span class="row-meta">Home time zone</span>
        <input v-model="form.homeTz" class="input" list="tz-list" autocomplete="off" data-testid="home-tz" />
        <datalist id="tz-list"><option v-for="z in timeZones" :key="z" :value="z" /></datalist>
      </label>
    </GlassPanel>

    <GlassPanel class="panel">
      <h2 class="row-title">Heart rate</h2>
      <p class="hrmax" data-testid="hrmax-source">Your HRmax: {{ hrmaxLine }}</p>
      <label class="field">
        <span class="row-meta">HRmax override (bpm)</span>
        <input v-model="form.hrmaxOverride" class="input" inputmode="numeric" placeholder="Leave empty to use the value above" data-testid="hrmax-override" />
      </label>
      <fieldset class="zones">
        <legend class="row-meta">Zone upper limits, % of HRmax</legend>
        <div class="zone-row">
          <label v-for="(_, i) in form.zones" :key="i" class="field">
            <span class="row-meta">Zone {{ i + 1 }}</span>
            <input v-model="form.zones[i]" class="input" inputmode="decimal" @input="zonesTouched = true" />
          </label>
        </div>
        <p class="row-meta">Zone 5 covers everything above zone 4.</p>
      </fieldset>
    </GlassPanel>

    </div>
    <p v-if="formError" class="err" role="alert" data-testid="form-error">{{ formError }}</p>
    <p v-else-if="s.error" class="err" role="alert">{{ s.error }}</p>
    <div class="actions">
      <Button variant="primary" type="submit" :disabled="s.saving" data-testid="save">{{ s.saving ? 'Saving…' : 'Save settings' }}</Button>
      <span v-if="saved && !s.recalculating" class="row-meta" role="status"><Icons name="check" :size="14" /> Saved.</span>
    </div>
  </form>

  <div class="cards">
    <PrivacyZonesPanel />
    <ShoesPanel />
    <WeatherPanel />
    <ImportPanel />
    <AiSettingsPanel />
    <ThresholdsPanel />
    <GlassPanel class="panel">
      <h2 class="row-title">Account</h2>
      <div class="choices"><Button data-testid="logout" @click="signOut">Sign out</Button></div>
    </GlassPanel>
  </div>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: var(--space-4); }
.form .cards { align-items: start; }
.panel { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.panel h2, .panel p { margin: 0; }
.panel h2 { font-family: var(--font-display); font-size: 17px; }
.panel :deep(.seg) { align-self: flex-start; }
.choices, .actions { display: flex; gap: var(--space-3); flex-wrap: wrap; align-items: center; }
.field { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.input { height: 48px; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: color-mix(in srgb, var(--surface-1) 75%, transparent); color: var(--ink); padding: 0 var(--space-4); font: inherit; min-width: 0; }
.input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.zones { border: 0; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
.zones legend { padding: 0; margin-bottom: var(--space-2); }
.zone-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(84px, 1fr)); gap: var(--space-3); }
.hrmax { font-weight: 600; }
.status { align-self: flex-start; }
.err { margin: 0; color: var(--danger); }
</style>
