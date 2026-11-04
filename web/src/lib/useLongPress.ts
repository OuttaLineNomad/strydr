import { onBeforeUnmount, ref } from 'vue'

/**
 * A press held for `ms` fires `onTrigger` once. `holding` is true while the hold is running, for a ring that fills.
 * The click the browser sends when a long press is released is swallowed: `consumeClick()` returns true once for it.
 */
export function useLongPress(ms: number, onTrigger: () => void) {
  const holding = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let fired = false

  function cancel() {
    if (timer) clearTimeout(timer)
    timer = null
    holding.value = false
  }
  function start(e?: Event) {
    if (e && 'button' in e && (e as MouseEvent).button > 0) return
    cancel()
    fired = false
    holding.value = true
    timer = setTimeout(() => {
      timer = null
      holding.value = false
      fired = true
      onTrigger()
    }, ms)
  }
  /** True if the click that follows belongs to a completed long press. */
  function consumeClick(): boolean {
    const f = fired
    fired = false
    return f
  }
  onBeforeUnmount(cancel)
  return {
    holding,
    start,
    cancel,
    consumeClick,
    handlers: { pointerdown: start, pointerup: cancel, pointerleave: cancel, pointercancel: cancel, contextmenu: (e: Event) => e.preventDefault() },
  }
}
