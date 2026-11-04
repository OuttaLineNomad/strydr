import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Holds the screen awake while the view is open and takes the lock again when the tab comes back to the front
 * (the browser drops it when the tab is hidden). `unavailable` turns true if the API is missing or refuses.
 */
export function useWakeLock() {
  const unavailable = ref(false)
  const held = ref(false)
  let sentinel: WakeLockSentinel | null = null
  let wanted = false

  let inflight: Promise<void> | null = null

  function acquire(): Promise<void> {
    if (!wanted) return Promise.resolve()
    if (inflight) return inflight // a second request while one is pending would double-lock
    const wl = typeof navigator !== 'undefined' ? navigator.wakeLock : undefined
    if (!wl || typeof wl.request !== 'function') {
      unavailable.value = true
      return Promise.resolve()
    }
    inflight = (async () => {
      try {
        const s = await wl.request('screen')
        if (!wanted) {
          // stop() ran while the request was pending: let it go at once
          try {
            await s.release()
          } catch {
            /* already released */
          }
          return
        }
        sentinel = s
        held.value = true
        unavailable.value = false
        s.addEventListener?.('release', () => {
          held.value = false
        })
      } catch {
        unavailable.value = true
      } finally {
        inflight = null
      }
    })()
    return inflight
  }

  function onVisible() {
    if (document.visibilityState === 'visible' && wanted && !held.value) void acquire()
  }

  function start() {
    wanted = true
    void acquire()
  }
  async function stop() {
    wanted = false
    const s = sentinel
    sentinel = null
    held.value = false
    try {
      await s?.release()
    } catch {
      /* already released */
    }
  }

  onMounted(() => document.addEventListener('visibilitychange', onVisible))
  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisible)
    void stop()
  })
  return { unavailable, held, start, stop }
}
