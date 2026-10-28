import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

// Animates a pre-formatted figure up to its value: plain decimals ("1.63", "138")
// and clock strings ("24:13", "1:02:45"). Anything else, and every case under
// Reduce Motion or without a browser clock, shows the final text at once.
const DECIMAL = /^\d+(\.\d+)?$/
const CLOCK = /^\d+(:\d{2}){1,2}$/
const DURATION_MS = 900

function canAnimate(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function' || typeof requestAnimationFrame !== 'function') return false
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function clockParts(s: string): number[] {
  return s.split(':').map(Number)
}
function toSeconds(parts: number[]): number {
  return parts.reduce((acc, p) => acc * 60 + p, 0)
}
function fromSeconds(total: number, shape: number[]): string {
  const out: string[] = []
  let rest = Math.round(total)
  for (let i = shape.length - 1; i >= 0; i--) {
    const v = i === 0 ? rest : rest % 60
    rest = Math.floor(rest / 60)
    out.unshift(i === 0 ? String(v) : String(v).padStart(2, '0'))
  }
  return out.join(':')
}

export function useCountUp(source: Ref<string | null>): Ref<string | null> {
  const shown = ref<string | null>(source.value)
  let raf = 0
  const stop = () => {
    if (raf && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(raf)
  }
  const run = (target: string | null) => {
    stop()
    if (target == null || !canAnimate() || !(DECIMAL.test(target) || CLOCK.test(target))) {
      shown.value = target
      return
    }
    const isClock = CLOCK.test(target)
    const decimals = isClock ? 0 : (target.split('.')[1]?.length ?? 0)
    const shape = isClock ? clockParts(target) : []
    const end = isClock ? toSeconds(shape) : Number(target)
    const t0 = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / DURATION_MS)
      const eased = 1 - Math.pow(1 - t, 4)
      const v = end * eased
      shown.value = t >= 1 ? target : isClock ? fromSeconds(v, shape) : v.toFixed(decimals)
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  }
  watch(source, run, { immediate: true })
  onBeforeUnmount(stop)
  return shown
}
