/**
 * Short tones from a Web Audio oscillator: no file, and it mixes over the runner's music instead of stopping it.
 * The AudioContext is created on the first call to `unlock()`, which must come from a tap (browsers require it).
 */
// One AudioContext for the whole app, so it can be unlocked by any earlier tap (the library's Start, a Get-ready
// interaction) and the minute and timed-move chimes still sound if the runner never taps the live field.
let ctx: AudioContext | null = null

export function unlockAudio() {
  if (ctx) {
    if (ctx.state === 'suspended') void ctx.resume?.()
    return
  }
  if (typeof window === 'undefined') return
  const Ctor = (window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext) as typeof AudioContext | undefined
  if (!Ctor) return
  try {
    ctx = new Ctor()
  } catch {
    ctx = null
  }
}
/** For specs: forget the shared context. */
export function resetAudio() {
  void ctx?.close?.()
  ctx = null
}

export function useTone() {
  const unlock = unlockAudio

  function beep(freq: number, at: number, len: number, peak: number) {
    if (!ctx) return
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = freq
    const t0 = ctx.currentTime + at
    gain.gain.setValueAtTime(0.0001, t0)
    gain.gain.exponentialRampToValueAtTime(peak, t0 + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + len)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(t0)
    osc.stop(t0 + len + 0.02)
  }

  /** A tap: one short, mid-high note. */
  function tap() {
    beep(880, 0, 0.09, 0.35)
  }
  /** A minute turning over or a timed move ending: two lower notes, clearly not the tap sound. */
  function chime() {
    beep(520, 0, 0.16, 0.4)
    beep(390, 0.18, 0.22, 0.4)
  }
  /** Back: one short note lower than the tap. */
  function low() {
    beep(440, 0, 0.07, 0.35)
  }
  return { unlock, tap, low, chime, get ready() { return ctx != null } }
}
