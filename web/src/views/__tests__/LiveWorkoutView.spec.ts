import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({ api: { GET: vi.fn(), POST: vi.fn() } }))
const push = vi.fn()
const replace = vi.fn()
const routeQuery: Record<string, string> = {}
const routeState = { name: 'workout-run' }
vi.mock('vue-router', () => ({ useRouter: () => ({ push, replace }), useRoute: () => ({ get name() { return routeState.name }, query: routeQuery }), RouterLink: { template: '<a><slot /></a>' } }))
import { api } from '@/api'
import LiveWorkoutView from '../LiveWorkoutView.vue'
import { usePlansStore } from '@/stores/plans'
import { useSettingsStore } from '@/stores/settings'
import { profile } from '@/mocks/fixtures'
import type { PlanOut } from '@/api/types'
import { memoryStorage } from '@/mocks/memoryStorage'
import { resetAudio } from '@/lib/useTone'

const post = vi.mocked(api.POST) as unknown as ReturnType<typeof vi.fn>
const getApi = vi.mocked(api.GET) as unknown as ReturnType<typeof vi.fn>
const KG25 = 11.3398

const plan = (o: Partial<PlanOut> = {}): PlanOut => ({
  id: 1, name: 'Swing circuit', format: 'amrap', cap_min: 20, emom_min: null, rounds: null, video_url: null,
  moves: ['Swing', 'Squat', 'Press', 'Row', 'Lunge'].map((name) => ({ name, reps: 10, seconds: null, weight_kg: KG25 })),
  created_at: '', updated_at: '', ...o,
})

// Web Audio and Wake Lock stubs
const oscillators: number[] = []
let audioCreated = 0
class FakeAudio {
  state = 'running'
  currentTime = 0
  destination = {}
  constructor() {
    audioCreated++
  }
  resume() { return Promise.resolve() }
  close() { return Promise.resolve() }
  createGain() {
    return { gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() }, connect: vi.fn() }
  }
  createOscillator() {
    const o = { type: '', frequency: { value: 0 }, connect: vi.fn(), start: vi.fn(), stop: vi.fn() }
    oscillators.push(0)
    const self = o
    Object.defineProperty(o.frequency, 'value', { set: (v: number) => (oscillators[oscillators.length - 1] = v), get: () => oscillators[oscillators.length - 1] ?? 0 })
    return self
  }
}
const release = vi.fn(() => Promise.resolve())
const request = vi.fn(() => Promise.resolve({ release, addEventListener: vi.fn() }))

const open: Array<{ unmount: () => void }> = []
async function mountIt(p: PlanOut = plan(), units: 'imperial' | 'metric' = 'imperial') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsStore().profile = profile({}, { units }) as never
  const plans = usePlansStore()
  plans.plans = [p]
  plans.loaded = true
  const w = mount(LiveWorkoutView, { props: { id: String(p.id) }, attachTo: document.body, global: { plugins: [pinia] } })
  open.push(w)
  await flushPromises()
  return w
}
type W = Awaited<ReturnType<typeof mountIt>>
const t = (w: W, id: string) => w.get(`[data-testid="${id}"]`).text()
const field = (w: W) => w.get('[data-testid="live-field"]')
async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
}
async function start(w: W) {
  await advance(5100)
  expect(w.find('[data-testid="live-field"]').exists()).toBe(true)
}
const tapN = async (w: W, n: number) => {
  for (let i = 0; i < n; i++) {
    await field(w).trigger('click')
    await advance(1000)
  }
}
const key = (k: string, type: 'keydown' | 'keyup' = 'keydown') => window.dispatchEvent(new KeyboardEvent(type, { key: k, bubbles: true, cancelable: true }))

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-03T18:00:00Z'))
  vi.clearAllMocks()
  request.mockReset()
  request.mockImplementation(() => Promise.resolve({ release, addEventListener: vi.fn() }))
  vi.stubGlobal('localStorage', memoryStorage())
  oscillators.length = 0
  audioCreated = 0
  resetAudio()
  vi.stubGlobal('AudioContext', FakeAudio)
  Object.defineProperty(window, 'AudioContext', { value: FakeAudio, configurable: true, writable: true })
  Object.defineProperty(navigator, 'wakeLock', { value: { request }, configurable: true })
  post.mockResolvedValue({ data: { id: 1 }, response: { status: 201 } })
})
afterEach(() => {
  while (open.length) open.pop()!.unmount()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('Get ready', () => {
  it('shows the plan, the first move and the bell large, counts 5 s and starts on its own', async () => {
    const w = await mountIt()
    expect(t(w, 'ready-plan')).toBe('Swing circuit')
    expect(t(w, 'ready-move')).toContain('Swing')
    expect(t(w, 'ready-count')).toBe('5')
    expect(t(w, 'weight-up')).toBe('25 lb')
    await advance(2000)
    expect(t(w, 'ready-count')).toBe('3')
    await advance(3200)
    expect(w.find('[data-testid="ready"]').exists()).toBe(false)
    expect(t(w, 'live-state')).toBe('Work')
    expect(t(w, 'live-move')).toBe('Swing')
  })

  it('steps the bell up and down for this session only: 25 lb -> 30 lb, the plan stays', async () => {
    const p = plan()
    const w = await mountIt(p)
    await w.get('[data-testid="weight-up"]').trigger('click')
    expect(t(w, 'weight-up')).toBe('30 lb')
    await w.get('[data-testid="weight-down"]').trigger('click')
    await w.get('[data-testid="weight-down"]').trigger('click')
    expect(t(w, 'weight-up')).toBe('20 lb')
    await w.get('[data-testid="weight-up"]').trigger('click')
    await w.get('[data-testid="weight-up"]').trigger('click')
    await start(w)
    expect(t(w, 'live-amount')).toContain('30 lb')
    expect(usePlansStore().plans[0]!.moves[0]!.weight_kg).toBe(KG25)
  })

  it('steps in 2 kg for a metric runner', async () => {
    const w = await mountIt(plan({ moves: [{ name: 'Swing', reps: 10, seconds: null, weight_kg: 16 }] }), 'metric')
    await w.get('[data-testid="weight-up"]').trigger('click')
    expect(t(w, 'weight-up')).toBe('18 kg')
  })

  it('holds the wake lock from the start', async () => {
    await mountIt()
    expect(request).toHaveBeenCalledWith('screen')
  })
})

describe('AMRAP flow', () => {
  it('shows Rest after move 5; the next tap starts round 2', async () => {
    const w = await mountIt()
    await start(w)
    expect(t(w, 'live-position')).toBe('Round 1 · Move 1 of 5')
    expect(t(w, 'live-next')).toBe('Next: Squat × 10')
    await tapN(w, 4)
    expect(t(w, 'live-move')).toBe('Lunge')
    await tapN(w, 1)
    expect(t(w, 'live-state')).toBe('Rest')
    expect(t(w, 'live-move')).toBe('Rest')
    expect(w.classes()).toContain('s-rest')
    await tapN(w, 1)
    expect(t(w, 'live-state')).toBe('Work')
    expect(t(w, 'live-position')).toBe('Round 2 · Move 1 of 5')
  })

  it('goes to overtime at the cap, says Finish this round, and the last tap saves 1 round', async () => {
    const w = await mountIt(plan({ cap_min: 1 }))
    await start(w)
    await tapN(w, 2) // on move 3
    await advance(60_000)
    expect(t(w, 'live-state')).toBe('Overtime')
    expect(w.classes()).toContain('s-overtime')
    expect(t(w, 'live-hint')).toBe('Finish this round')
    expect(t(w, 'live-clock')).toMatch(/^\+0:\d\d$/)
    await tapN(w, 3)
    await flushPromises()
    expect(t(w, 'saved-rounds')).toBe('1 round')
    expect(post).toHaveBeenCalledTimes(1)
    const body = post.mock.calls[0]![1].body
    expect(body).toMatchObject({ plan_id: 1, rounds_done: 1, partial_moves: 0, fell_short: [], weight_kg: KG25 })
    expect(body.plan.name).toBe('Swing circuit')
    expect(body.events.filter((e: { kind: string }) => e.kind === 'next')).toHaveLength(5)
    expect(new Date(body.end_utc).getTime()).toBeGreaterThan(new Date(body.start_utc).getTime())
  })

  it('a seconds move counts down, advances itself with a different tone, and a tap skips it', async () => {
    const w = await mountIt(plan({ moves: [{ name: 'Plank', reps: null, seconds: 30, weight_kg: null }, { name: 'Swing', reps: 10, seconds: null, weight_kg: null }] }))
    await start(w)
    await field(w).trigger('click') // first tap creates the audio context
    expect(audioCreated).toBe(1)
    expect(t(w, 'live-move')).toBe('Swing')
    await field(w).trigger('click')
    expect(t(w, 'live-state')).toBe('Rest')
    await field(w).trigger('click')
    expect(t(w, 'live-move')).toBe('Plank')
    oscillators.length = 0
    expect(t(w, 'live-clock')).toBe('0:30')
    await advance(10_000)
    expect(t(w, 'live-clock')).toBe('0:20')
    await advance(20_500)
    expect(t(w, 'live-move')).toBe('Swing')
    expect(oscillators.length).toBeGreaterThan(0)
    expect(oscillators).not.toContain(880) // not the tap tone
  })
})

describe('EMOM', () => {
  const emom = () => plan({ format: 'emom', cap_min: null, emom_min: 3, moves: plan().moves.slice(0, 2) })

  it('rotates by minute, flags a tap as fell short, undoes it, and ends after the last minute', async () => {
    const w = await mountIt(emom())
    await start(w)
    expect(t(w, 'live-move')).toBe('Swing')
    expect(t(w, 'live-hint')).toBe('Tap if you fell short')
    await advance(61_000)
    expect(t(w, 'live-move')).toBe('Squat')
    expect(t(w, 'live-position')).toBe('Minute 2 of 3 · Move 2 of 2')
    await field(w).trigger('click')
    expect(t(w, 'live-hint')).toBe('Fell short. Tap to undo.')
    await field(w).trigger('click')
    expect(t(w, 'live-hint')).toBe('Tap if you fell short')
    await field(w).trigger('click')
    await advance(120_000)
    await flushPromises()
    expect(w.find('[data-testid="saved"]').exists()).toBe(true)
    expect(post.mock.calls[0]![1].body.fell_short).toEqual([2])
    expect(t(w, 'saved-rounds')).toBe('1 round + 1 move')
  })
})

describe('Complex', () => {
  it('counts up, rests between rounds and ends after round N', async () => {
    const w = await mountIt(plan({ format: 'complex', cap_min: null, rounds: 2, moves: plan().moves.slice(0, 2) }))
    await start(w)
    expect(t(w, 'live-position')).toBe('Round 1 of 2 · Move 1 of 2')
    await tapN(w, 3) // m1 m2 rest
    expect(t(w, 'live-state')).toBe('Work')
    expect(t(w, 'live-position')).toBe('Round 2 of 2 · Move 1 of 2')
    await tapN(w, 2)
    await flushPromises()
    expect(t(w, 'saved-rounds')).toBe('2 rounds')
  })
})

describe('Pause', () => {
  it('a 600 ms hold pauses, freezes the clock, and a tap resumes', async () => {
    const w = await mountIt()
    await start(w)
    await advance(4000)
    const before = t(w, 'live-clock')
    await field(w).trigger('pointerdown')
    await advance(300)
    expect(w.find('[data-testid="live-ring"]').exists()).toBe(true)
    await advance(400)
    expect(t(w, 'live-state')).toBe('Paused')
    expect(t(w, 'live-move')).toBe('Paused')
    expect(w.classes()).toContain('s-paused')
    await field(w).trigger('pointerup')
    await field(w).trigger('click') // the release click after a long press is swallowed
    expect(t(w, 'live-state')).toBe('Paused')
    const frozen = t(w, 'live-clock')
    await advance(120_000)
    expect(t(w, 'live-clock')).toBe(frozen)
    expect(before).toMatch(/^19:/)
    await field(w).trigger('click')
    expect(t(w, 'live-state')).toBe('Work')
    await advance(3000)
    expect(t(w, 'live-clock')).not.toBe(frozen)
  })

  it('a short press is a tap, not a pause', async () => {
    const w = await mountIt()
    await start(w)
    await field(w).trigger('pointerdown')
    await advance(200)
    await field(w).trigger('pointerup')
    await field(w).trigger('click')
    expect(t(w, 'live-state')).toBe('Work')
    expect(t(w, 'live-move')).toBe('Squat')
  })

  it('records the pause in the saved events', async () => {
    const w = await mountIt(plan({ format: 'complex', cap_min: null, rounds: 1, moves: [plan().moves[0]!] }))
    await start(w)
    key('p')
    await advance(2000)
    key('p')
    await tapN(w, 1)
    await flushPromises()
    const kinds = post.mock.calls[0]![1].body.events.map((e: { kind: string }) => e.kind)
    expect(kinds).toEqual(['pause', 'resume', 'next'])
  })
})

describe('End', () => {
  it('needs a 1 s hold, then saves the partial round: round 2, move 3 is 1 round + 2 moves', async () => {
    const w = await mountIt()
    await start(w)
    await tapN(w, 5 + 1 + 2) // round 1, rest tap, two moves into round 2
    const end = w.get('[data-testid="live-end"]')
    await end.trigger('pointerdown')
    await advance(600)
    expect(w.find('[data-testid="saved"]').exists()).toBe(false)
    await end.trigger('pointerup')
    await advance(2000)
    expect(w.find('[data-testid="saved"]').exists()).toBe(false)
    await end.trigger('pointerdown')
    await advance(1100)
    await flushPromises()
    expect(t(w, 'saved-rounds')).toBe('1 round + 2 moves')
    expect(post.mock.calls[0]![1].body).toMatchObject({ rounds_done: 1, partial_moves: 2 })
  })

  it('Escape held for 1 s ends; released early it does not', async () => {
    const w = await mountIt()
    await start(w)
    key('Escape')
    await advance(500)
    key('Escape', 'keyup')
    await advance(1500)
    expect(w.find('[data-testid="saved"]').exists()).toBe(false)
    key('Escape')
    await advance(1100)
    await flushPromises()
    expect(w.find('[data-testid="saved"]').exists()).toBe(true)
  })
})

describe('Keyboard and names', () => {
  it('Space and Enter are next, P pauses and resumes; controls have accessible names', async () => {
    const w = await mountIt()
    await start(w)
    key(' ')
    await advance(10)
    expect(t(w, 'live-move')).toBe('Squat')
    key('Enter')
    await advance(10)
    expect(t(w, 'live-move')).toBe('Press')
    key('p')
    await advance(10)
    expect(t(w, 'live-state')).toBe('Paused')
    key('P')
    await advance(10)
    expect(t(w, 'live-state')).toBe('Work')
    expect(field(w).attributes('aria-label')).toContain('Next move')
    expect(field(w).attributes('role')).toBe('button')
    expect(w.get('[data-testid="live-end"]').attributes('aria-label')).toContain('End workout')
  })
})

describe('Feedback', () => {
  it('flashes the field on a tap for about 150 ms and plays the tap tone, created on the first tap', async () => {
    const w = await mountIt()
    await start(w)
    expect(audioCreated).toBe(0)
    await field(w).trigger('click')
    expect(audioCreated).toBe(1)
    expect(oscillators).toContain(880)
    expect(w.get('[data-testid="live-flash"]').classes()).toContain('on')
    await advance(200)
    expect(w.get('[data-testid="live-flash"]').classes()).not.toContain('on')
  })
})

describe('Wake lock', () => {
  it('takes the lock again when the tab becomes visible after the browser dropped it', async () => {
    const releases: Array<() => void> = []
    request.mockImplementation(() => Promise.resolve({ release, addEventListener: vi.fn((_: string, f: () => void) => releases.push(f)) }))
    const w = await mountIt()
    await start(w)
    expect(request).toHaveBeenCalledTimes(1)
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(request).toHaveBeenCalledTimes(1) // still held: nothing to redo
    releases[0]!() // the tab was hidden and the browser released the lock
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(request).toHaveBeenCalledTimes(2)
    w.unmount()
    expect(release).toHaveBeenCalled()
  })

  it('shows one notice and still runs when the API is missing', async () => {
    Object.defineProperty(navigator, 'wakeLock', { value: undefined, configurable: true })
    const w = await mountIt()
    await start(w)
    expect(t(w, 'wake-notice')).toBe('Screen may sleep — keep it on in Settings')
    expect(w.findAll('[data-testid="wake-notice"]')).toHaveLength(1)
    await field(w).trigger('click')
    expect(t(w, 'live-move')).toBe('Squat')
  })

  it('shows the notice when the request is refused', async () => {
    request.mockImplementationOnce(() => Promise.reject(new Error('denied')))
    const w = await mountIt()
    await start(w)
    expect(w.find('[data-testid="wake-notice"]').exists()).toBe(true)
  })
})

describe('Saved', () => {
  async function finish(w: W) {
    await start(w)
    await tapN(w, 1) // a one-move complex ends on this tap
    await flushPromises()
  }
  const one = () => plan({ format: 'complex', cap_min: null, rounds: 1, moves: [plan().moves[0]!] })

  it('shows the plan, rounds, active time and bell, and Done goes to Workouts', async () => {
    const w = await mountIt(one())
    await finish(w)
    expect(t(w, 'saved-plan')).toBe('Swing circuit')
    expect(t(w, 'saved-rounds')).toBe('1 round')
    expect(t(w, 'saved-time')).toMatch(/^0:0\d$/)
    expect(t(w, 'saved-bell')).toBe('25 lb')
    await flushPromises()
    expect(w.find('[data-testid="saved-status"]').exists()).toBe(false) // saved cleanly: nothing more to say
    await w.get('[data-testid="saved-done"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/workouts')
    expect(localStorage.getItem('strydr.sessionOutbox')).toBeNull()
  })

  it('goes straight to the summary once the session is saved', async () => {
    post.mockResolvedValue({ data: { id: 42 }, response: { status: 201 } })
    const w = await mountIt(one())
    await finish(w)
    await flushPromises()
    expect(replace).toHaveBeenCalledWith('/workouts/sessions/42')
  })

  it('does not pull the runner away if the reply lands after he left the screen', async () => {
    let reply!: (v: unknown) => void
    post.mockReturnValue(new Promise((r) => (reply = r)))
    const w = await mountIt(one())
    await finish(w)
    routeState.name = 'workouts'
    try {
      reply({ data: { id: 42 }, response: { status: 201 } })
      await flushPromises()
      expect(replace).not.toHaveBeenCalled()
    } finally {
      routeState.name = 'workout-run'
    }
  })

  it('stays on the saved screen when the record is only kept on the phone', async () => {
    post.mockRejectedValue(new Error('offline'))
    const w = await mountIt(one())
    await finish(w)
    expect(replace).not.toHaveBeenCalled()
  })

  it('keeps the record on the phone when the POST fails', async () => {
    post.mockRejectedValue(new Error('offline'))
    const w = await mountIt(one())
    await finish(w)
    expect(t(w, 'saved-status')).toBe('Saved on this phone, will sync')
    expect(JSON.parse(localStorage.getItem('strydr.sessionOutbox')!)).toHaveLength(1)
  })

  it('seeds Get ready with the bell carried from a summary', async () => {
    routeQuery.weight = '13.6078'
    try {
      const w = await mountIt(one())
      await w.get('[data-testid="weight-up"]').trigger('click')
      await finish(w)
      expect(t(w, 'saved-bell')).toBe('35 lb') // 30 lb carried, stepped to the next bell
    } finally {
      delete routeQuery.weight
    }
  })

  it('ignores a carried bell that is not a weight', async () => {
    routeQuery.weight = 'heavy'
    try {
      const w = await mountIt(one())
      await finish(w)
      expect(t(w, 'saved-bell')).toBe('25 lb')
    } finally {
      delete routeQuery.weight
    }
  })

  it('saves the stepped weight, not the plan weight', async () => {
    const w = await mountIt(one())
    await w.get('[data-testid="weight-up"]').trigger('click')
    await finish(w)
    expect(t(w, 'saved-bell')).toBe('30 lb')
    expect(post.mock.calls[0]![1].body.weight_kg).toBeCloseTo(13.6078, 3)
    expect(post.mock.calls[0]![1].body.plan.moves[0].weight_kg).toBe(KG25)
  })
})

describe('missing plan', () => {
  it('says so and offers a way back', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const plans = usePlansStore()
    plans.loaded = true
    const w = mount(LiveWorkoutView, { props: { id: '99' }, global: { plugins: [pinia] } })
    await flushPromises()
    expect(w.find('[data-testid="live-missing"]').exists()).toBe(true)
  })
})


describe('interrupted runs', () => {
  const remount = async (id = '1') => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useSettingsStore().profile = profile({}, { units: 'imperial' }) as never
    const w = mount(LiveWorkoutView, { props: { id }, attachTo: document.body, global: { plugins: [pinia] } })
    open.push(w)
    await flushPromises()
    return w
  }

  it('resumes straight into the live state after a reload, without the plans list', async () => {
    const w = await mountIt()
    await start(w)
    await tapN(w, 2)
    expect(t(w, 'live-move')).toBe('Press')
    w.unmount()
    const w2 = await remount()
    expect(w2.find('[data-testid="ready"]').exists()).toBe(false)
    expect(t(w2, 'live-move')).toBe('Press')
    expect(t(w2, 'live-position')).toBe('Round 1 · Move 3 of 5')
    expect(getApi).not.toHaveBeenCalled()
    await w2.get('[data-testid="live-field"]').trigger('click')
    expect(t(w2, 'live-move')).toBe('Row')
  })

  it('keeps the stepped bell across a reload during Get ready', async () => {
    const w = await mountIt()
    await w.get('[data-testid="weight-up"]').trigger('click')
    w.unmount()
    const w2 = await remount()
    expect(t(w2, 'weight-up')).toBe('30 lb')
  })

  it('ignores a draft older than 4 h or for another plan', async () => {
    const w = await mountIt()
    await start(w)
    w.unmount()
    vi.setSystemTime(Date.now() + 4 * 3600 * 1000 + 1000)
    const stale = await remount()
    expect(stale.find('[data-testid="live-load-error"], [data-testid="live-missing"]').exists()).toBe(true)
    stale.unmount()
  })

  it('clears the draft once the session is saved', async () => {
    const w = await mountIt(plan({ format: 'complex', cap_min: null, rounds: 1, moves: [plan().moves[0]!] }))
    await start(w)
    expect(localStorage.getItem('strydr.liveDraft')).not.toBeNull()
    await tapN(w, 1)
    await flushPromises()
    expect(localStorage.getItem('strydr.liveDraft')).toBeNull()
  })

  it('a slow timer cannot push the end past 4 h: the record stays within the server cap', async () => {
    const w = await mountIt(plan({ format: 'complex', cap_min: null, rounds: 5, moves: plan().moves.slice(0, 2) }))
    await start(w)
    vi.setSystemTime(Date.now() + 5 * 3600 * 1000) // the phone slept
    await advance(200)
    await flushPromises()
    expect(w.find('[data-testid="saved"]').exists()).toBe(true)
    const body = post.mock.calls[0]![1].body
    const span = new Date(body.end_utc).getTime() - new Date(body.start_utc).getTime()
    expect(span).toBeLessThanOrEqual(4 * 3600 * 1000 - 1000)
    expect(Math.max(...body.events.map((e: { t_ms: number }) => e.t_ms))).toBeLessThanOrEqual(4 * 3600 * 1000 - 1000)
  })
})

describe('plan loading', () => {
  it('shows a load error with Retry, not "gone", when the list fails to load', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    getApi.mockResolvedValueOnce({ data: undefined, response: { status: 500 } })
    const w = mount(LiveWorkoutView, { props: { id: '1' }, global: { plugins: [pinia] } })
    await flushPromises()
    expect(w.find('[data-testid="live-load-error"]').exists()).toBe(true)
    expect(w.find('[data-testid="live-missing"]').exists()).toBe(false)
    getApi.mockResolvedValueOnce({ data: [plan()], response: { status: 200 } })
    await w.get('[data-testid="live-retry"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="ready"]').exists()).toBe(true)
    w.unmount()
  })

  it('a library reload mid-session does not change or blank the run', async () => {
    const w = await mountIt()
    await start(w)
    usePlansStore().plans = []
    await advance(300)
    expect(t(w, 'live-move')).toBe('Swing')
    usePlansStore().plans = [plan({ name: 'Renamed', moves: [{ name: 'Other', reps: 3, seconds: null, weight_kg: null }] })]
    await advance(300)
    expect(t(w, 'live-move')).toBe('Swing')
  })

  it('unmounting while the list loads leaves no timer or wake lock behind', async () => {
    let resolve!: (v: unknown) => void
    getApi.mockReturnValueOnce(new Promise((r) => (resolve = r)))
    const pinia = createPinia()
    setActivePinia(pinia)
    const w = mount(LiveWorkoutView, { props: { id: '1' }, global: { plugins: [pinia] } })
    w.unmount()
    resolve({ data: [plan()], response: { status: 200 } })
    await flushPromises()
    expect(request).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('wake lock races', () => {
  it('releases a lock that arrives after the view was closed', async () => {
    let grant!: (s: unknown) => void
    request.mockImplementationOnce(() => new Promise((r) => (grant = r)) as never)
    const w = await mountIt()
    w.unmount()
    grant({ release, addEventListener: vi.fn() })
    await flushPromises()
    expect(release).toHaveBeenCalled()
  })

  it('does not request twice while one request is pending, and clears the notice after a success', async () => {
    let grant!: (s: unknown) => void
    request.mockImplementationOnce(() => new Promise((r) => (grant = r)) as never)
    const w = await mountIt()
    document.dispatchEvent(new Event('visibilitychange'))
    document.dispatchEvent(new Event('visibilitychange'))
    expect(request).toHaveBeenCalledTimes(1)
    grant({ release, addEventListener: vi.fn() })
    await flushPromises()
    w.unmount()
  })

  it('unavailable goes back to false after a later success', async () => {
    const handlers: Array<() => void> = []
    request.mockImplementationOnce(() => Promise.reject(new Error('denied')))
    request.mockImplementationOnce(() => Promise.resolve({ release, addEventListener: vi.fn((_: string, f: () => void) => handlers.push(f)) }))
    const w = await mountIt()
    expect(w.find('[data-testid="wake-notice"]').exists()).toBe(false) // still in Get ready: no live screen yet
    await start(w)
    expect(w.find('[data-testid="wake-notice"]').exists()).toBe(true)
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(w.find('[data-testid="wake-notice"]').exists()).toBe(false)
  })
})

describe('End by keyboard and sound unlock', () => {
  it('Enter or Space on the focused End button starts the same 1 s hold', async () => {
    const w = await mountIt()
    await start(w)
    const end = w.get('[data-testid="live-end"]')
    await end.trigger('keydown', { key: 'Enter' })
    await advance(400)
    await end.trigger('keyup', { key: 'Enter' })
    await advance(1500)
    expect(w.find('[data-testid="saved"]').exists()).toBe(false)
    await end.trigger('keydown', { key: ' ' })
    await advance(1100)
    await flushPromises()
    expect(w.find('[data-testid="saved"]').exists()).toBe(true)
  })

  it('Cancel leaves Get ready without saving anything or leaving a draft', async () => {
    const w = await mountIt()
    await w.get('[data-testid="ready-cancel"]').trigger('click')
    expect(replace).toHaveBeenCalledWith('/workouts/1')
    await advance(6000)
    expect(post).not.toHaveBeenCalled()
    expect(localStorage.length).toBe(0)
    expect(release).toHaveBeenCalled()
  })

  it('has no Cancel once the workout is running', async () => {
    const w = await mountIt()
    await start(w)
    expect(w.find('[data-testid="ready-cancel"]').exists()).toBe(false)
    expect(w.find('[data-testid="live-end"]').exists()).toBe(true)
  })

  it('an Escape hold during Get ready does nothing', async () => {
    const w = await mountIt()
    key('Escape')
    await advance(1500)
    key('Escape', 'keyup')
    expect(w.find('[data-testid="ready"]').exists()).toBe(true)
  })

  it('a Get-ready interaction unlocks the audio so auto chimes sound without any tap on the field', async () => {
    const w = await mountIt(plan({ format: 'emom', cap_min: null, emom_min: 3, moves: plan().moves.slice(0, 2) }))
    expect(audioCreated).toBe(0)
    await w.get('[data-testid="ready"]').trigger('pointerdown')
    expect(audioCreated).toBe(1)
    await start(w)
    oscillators.length = 0
    await advance(61_000)
    expect(oscillators.length).toBeGreaterThan(0) // the minute chime, with no tap on the field
  })

  describe('Back', () => {
    const back = (w: W) => w.get('[data-testid="live-back"]')
    const remount = async () => {
      const pinia = createPinia()
      setActivePinia(pinia)
      useSettingsStore().profile = profile({}, { units: 'imperial' }) as never
      const w = mount(LiveWorkoutView, { props: { id: '1' }, attachTo: document.body, global: { plugins: [pinia] } })
      open.push(w)
      await flushPromises()
      return w
    }
    it('is disabled with nothing to undo and does not move the field', async () => {
      const w = await mountIt()
      await start(w)
      expect(back(w).attributes('aria-disabled')).toBe('true')
      expect(back(w).attributes('aria-label')).toBe('Back: undo the last tap')
      await back(w).trigger('click')
      expect(t(w, 'live-move')).toBe('Swing')
    })
    it('has no Back on Get ready', async () => {
      const w = await mountIt()
      expect(w.find('[data-testid="live-back"]').exists()).toBe(false)
    })
    it('undoes the last next without tapping the field, plays a lower tone and saves the draft', async () => {
      const w = await mountIt()
      await start(w)
      await tapN(w, 2)
      expect(t(w, 'live-move')).toBe('Press')
      expect(back(w).attributes('aria-disabled')).toBe('false')
      oscillators.length = 0
      await back(w).trigger('click')
      expect(t(w, 'live-move')).toBe('Squat')
      expect(oscillators).toEqual([440])
      w.unmount()
      const w2 = await remount()
      expect(t(w2, 'live-move')).toBe('Squat')
    })
    it('does not reach the field', async () => {
      const w = await mountIt()
      await start(w)
      await tapN(w, 1)
      await back(w).trigger('pointerdown')
      await back(w).trigger('click')
      expect(t(w, 'live-move')).toBe('Swing')
    })
  })
})
