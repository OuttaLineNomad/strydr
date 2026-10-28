import type { Directive } from 'vue'

// Liquid Glass touch illumination: the element bounces on press (CSS) and a
// radial glint lights up at the contact point, fading out on release.
type PressEl = HTMLElement & { __pressOff?: () => void }

export const vPress: Directive<PressEl, boolean | undefined> = {
  mounted(el, binding) {
    if (binding.value === false) return
    el.classList.add('glass-interactive')
    const touch = document.createElement('span')
    touch.className = 'glass-touch'
    touch.setAttribute('aria-hidden', 'true')
    el.prepend(touch)
    const down = (e: PointerEvent) => {
      const r = el.getBoundingClientRect()
      el.style.setProperty('--tx', `${e.clientX - r.left}px`)
      el.style.setProperty('--ty', `${e.clientY - r.top}px`)
      el.classList.add('is-touched')
    }
    const up = () => el.classList.remove('is-touched')
    el.addEventListener('pointerdown', down)
    el.addEventListener('pointerup', up)
    el.addEventListener('pointerleave', up)
    el.addEventListener('pointercancel', up)
    el.__pressOff = () => {
      el.removeEventListener('pointerdown', down)
      el.removeEventListener('pointerup', up)
      el.removeEventListener('pointerleave', up)
      el.removeEventListener('pointercancel', up)
      touch.remove()
    }
  },
  unmounted(el) {
    el.__pressOff?.()
  },
}
