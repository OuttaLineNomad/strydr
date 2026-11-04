<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import TabBar from '@/components/ui/TabBar.vue'
import SideNav from '@/components/ui/SideNav.vue'

const route = useRoute()

// True refraction (SVG displacement behind the navigation) renders reliably
// only in Chromium; Safari and Firefox keep the standard glass recipe.
onMounted(() => {
  if (/Chrome\//.test(navigator.userAgent)) document.documentElement.classList.add('lens-ok')
})
</script>

<template>
  <div class="wash" aria-hidden="true"><i /><i /><i /></div>
  <svg width="0" height="0" style="position: absolute" aria-hidden="true" focusable="false">
    <filter id="glass-lens" x="-20%" y="-20%" width="140%" height="140%">
      <feTurbulence type="fractalNoise" baseFrequency="0.009 0.02" numOctaves="1" seed="9" result="noise" />
      <feGaussianBlur in="noise" stdDeviation="2.2" result="softNoise" />
      <feDisplacementMap in="SourceGraphic" in2="softNoise" scale="20" xChannelSelector="R" yChannelSelector="G" />
    </filter>
  </svg>

  <SideNav v-if="!route.meta.bare" />
  <main class="page" :class="{ 'page--bare': route.meta.bare, 'page--full': route.meta.full }">
    <RouterView v-slot="{ Component, route: r }">
      <Transition name="page" mode="out-in">
        <div :key="r.path" class="view">
          <component :is="Component" />
        </div>
      </Transition>
    </RouterView>
  </main>
  <TabBar v-if="!route.meta.bare" />
</template>

<style scoped>
.page {
  /* Where the page sits in the window; full-bleed blocks use these to reach the window edges. */
  --page-left: 0px;
  --pad-x: var(--gutter);
  --pad-top: var(--space-6);
  max-width: 1480px; margin: 0 auto;
  padding: var(--pad-top) var(--pad-x) calc(var(--space-4) + 64px + var(--space-6) + env(safe-area-inset-bottom, 0px));
}
.view { display: flex; flex-direction: column; gap: var(--space-5); }
.page--bare { padding-bottom: var(--space-6); min-height: 100dvh; display: flex; flex-direction: column; justify-content: center; max-width: 480px; }
/* The live workout owns the whole window: no max width, no padding, no centring. */
.page--full { max-width: none; margin: 0; padding: 0; min-height: 0; display: block; }
@media (min-width: 1080px) {
  .page:not(.page--bare) {
    --page-left: calc(var(--sidebar-w) + var(--space-4));
    --pad-x: var(--space-8);
    --pad-top: var(--space-8);
    margin-left: var(--page-left);
    margin-right: auto;
    padding: var(--pad-top) var(--pad-x) var(--space-10);
  }
  .view { gap: var(--space-6); }
}
@media (min-width: 1800px) {
  .page:not(.page--bare) { --page-left: max(calc(var(--sidebar-w) + var(--space-4)), calc((100vw - 1480px) / 2)); }
}
</style>
