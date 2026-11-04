/** An in-memory Storage for specs (the test runtime's own localStorage is not a complete one). */
export function memoryStorage(): Storage {
  let m = new Map<string, string>()
  return {
    get length() { return m.size },
    clear: () => { m = new Map() },
    getItem: (k: string) => m.get(k) ?? null,
    key: (i: number) => [...m.keys()][i] ?? null,
    removeItem: (k: string) => { m.delete(k) },
    setItem: (k: string, v: string) => { m.set(k, String(v)) },
  }
}
