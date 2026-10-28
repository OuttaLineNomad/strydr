import { nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref, type WatchSource } from 'vue'

// Measures the active item inside a container so a single glass "lens" can
// glide between items (one shape morphing, not a swap). The lens moves on
// --ease-glass; the first placement is instant so it never flies in from 0,0.
export function useLens(container: Ref<HTMLElement | null>, selector: string, trigger: WatchSource) {
  const style = ref<Record<string, string>>({ opacity: '0' })
  let ready = false
  let ro: ResizeObserver | null = null

  function place() {
    const box = container.value
    const el = box?.querySelector<HTMLElement>(selector)
    if (!box || !el) {
      style.value = { ...style.value, opacity: '0' }
      return
    }
    style.value = {
      opacity: '1',
      width: `${el.offsetWidth}px`,
      height: `${el.offsetHeight}px`,
      transform: `translate(${el.offsetLeft}px, ${el.offsetTop}px)`,
      transition: ready ? '' : 'none',
    }
    if (!ready) {
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => (ready = true))
      else ready = true
    }
  }

  onMounted(() => {
    void nextTick(place)
    if (typeof ResizeObserver === 'function' && container.value) {
      ro = new ResizeObserver(() => place())
      ro.observe(container.value)
    }
    // Web fonts change label widths after first paint.
    void document.fonts?.ready?.then(place)
  })
  onBeforeUnmount(() => ro?.disconnect())
  watch(trigger, () => void nextTick(place))
  return { style, place }
}
