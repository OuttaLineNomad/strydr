<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import GlassPanel from '@/components/ui/GlassPanel.vue'
import Button from '@/components/ui/Button.vue'
import { useShoesStore } from '@/stores/shoes'
import { useSettingsStore } from '@/stores/settings'
import { distanceUnit, formatDistance } from '@/lib/units'

const store = useShoesStore()
const s = useSettingsStore()
onMounted(() => store.load())

function today(): string {
  const tz = s.profile?.settings.home_tz
  try {
    return new Date().toLocaleDateString('en-CA', tz ? { timeZone: tz } : undefined)
  } catch {
    return new Date().toLocaleDateString('en-CA')
  }
}

const units = computed(() => s.units)
const newName = ref('')
const fromDate = ref(today())
const defaultId = ref<string>('')
// Start on the current default, and follow it when the list loads or changes.
watch(() => store.current?.shoe_id, (id) => { defaultId.value = id == null ? '' : String(id) }, { immediate: true })
const editing = ref<number | null>(null)
const editName = ref('')

const active = computed(() => store.shoes.filter((x) => !x.retired))
const currentDefault = computed(() => store.shoes.find((x) => x.id === store.current?.shoe_id) ?? null)

async function add() {
  if (!newName.value.trim()) return
  if (await store.add(newName.value.trim())) newName.value = ''
}
function startEdit(id: number, name: string) {
  editing.value = id
  editName.value = name
}
async function saveEdit() {
  if (editing.value == null || !editName.value.trim()) return
  if (await store.rename(editing.value, editName.value.trim())) editing.value = null
}
async function saveDefault() {
  if (!fromDate.value) return
  await store.setDefault(defaultId.value === '' ? null : Number(defaultId.value), fromDate.value)
}
</script>

<template>
  <GlassPanel class="panel" role="group" aria-label="Shoes" data-testid="shoes-panel">
    <h2 class="row-title">Shoes</h2>
    <p class="row-meta">Track how far each pair has gone. Retire a pair when you are done with it. Strydr does not warn you about wear.</p>

    <ul v-if="store.shoes.length" class="shoes" data-testid="shoe-list">
      <li v-for="x in store.shoes" :key="x.id" class="shoe" data-testid="shoe-row">
        <template v-if="editing === x.id">
          <input v-model="editName" class="input" maxlength="60" :aria-label="`Name for ${x.name}`" data-testid="shoe-rename-input" @keydown.enter.prevent="saveEdit" />
          <Button small :disabled="store.busy" data-testid="shoe-rename-save" @click="saveEdit">Save</Button>
          <Button small data-testid="shoe-rename-cancel" @click="editing = null">Cancel</Button>
        </template>
        <template v-else>
          <span class="name">
            <span data-testid="shoe-name">{{ x.name }}</span>
            <span v-if="x.retired" class="row-meta" data-testid="shoe-retired"> (retired)</span>
          </span>
          <span class="row-meta" data-testid="shoe-total">{{ formatDistance(x.distance_m, units) }} {{ distanceUnit(units) }}, {{ x.runs }} {{ x.runs === 1 ? 'run' : 'runs' }}</span>
          <Button small :aria-label="`Rename ${x.name}`" data-testid="shoe-rename" @click="startEdit(x.id, x.name)">Rename</Button>
          <Button small :disabled="store.busy" :aria-label="`${x.retired ? 'Unretire' : 'Retire'} ${x.name}`" data-testid="shoe-retire" @click="store.setRetired(x.id, !x.retired)">
            {{ x.retired ? 'Unretire' : 'Retire' }}
          </Button>
        </template>
      </li>
    </ul>
    <p v-else class="row-meta" data-testid="shoes-empty">You have no shoes yet.</p>

    <form class="add" @submit.prevent="add">
      <label class="field">
        <span class="row-meta">New shoe</span>
        <input v-model="newName" class="input" maxlength="60" placeholder="Name" data-testid="shoe-name-input" />
      </label>
      <Button variant="primary" type="submit" :disabled="store.busy || !newName.trim()" data-testid="shoe-add">Add shoe</Button>
    </form>

    <h3 class="chart-title">Default shoe</h3>
    <p class="row-meta" data-testid="shoe-default-now">
      <template v-if="currentDefault">Now: {{ currentDefault.name }}, from {{ store.current?.from_date }}.</template>
      <template v-else>No default shoe is set.</template>
      Runs on or after the date use it unless you choose another.
    </p>
    <div class="add">
      <label class="field">
        <span class="row-meta">Shoe</span>
        <select v-model="defaultId" class="input" data-testid="shoe-default-select">
          <option value="">No default</option>
          <option v-for="x in active" :key="x.id" :value="String(x.id)">{{ x.name }}</option>
        </select>
      </label>
      <label class="field">
        <span class="row-meta">From</span>
        <input v-model="fromDate" type="date" class="input" data-testid="shoe-default-date" />
      </label>
      <Button :disabled="store.busy || !fromDate" data-testid="shoe-default-save" @click="saveDefault">Set default</Button>
    </div>
    <p v-if="store.error" class="err" role="alert" data-testid="shoes-error">{{ store.error }}</p>
  </GlassPanel>
</template>

<style scoped>
.panel { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-3); }
.panel h2, .panel h3, .panel p { margin: 0; }
.shoes { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
.shoe { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
.name { flex: 1 1 8rem; min-width: 0; }
.add { display: flex; gap: var(--space-3); align-items: end; flex-wrap: wrap; }
.field { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.input { height: 48px; border-radius: var(--radius-md); border: 1.5px solid var(--divider); background: color-mix(in srgb, var(--surface-1) 75%, transparent); color: var(--ink); padding: 0 var(--space-4); font: inherit; min-width: 0; }
.input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.err { color: var(--danger); }
</style>
