import { useCallback, useEffect, useRef, useState } from 'react'

const cache = new Map<string, unknown>()

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const key = fn.toString() + JSON.stringify(deps)
  const keyRef = useRef(key)
  keyRef.current = key
  const [data, setDataState] = useState<T | null>(() => (cache.get(key) as T | undefined) ?? null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(() => !cache.has(key))
  const seq = useRef(0)
  const setData = useCallback((v: T | null | ((prev: T | null) => T | null)) => {
    setDataState(prev => {
      const next = typeof v === 'function' ? (v as (p: T | null) => T | null)(prev) : v
      cache.set(keyRef.current, next)
      return next
    })
  }, [])
  const run = useCallback(() => {
    const id = ++seq.current
    const k = keyRef.current
    setError(null)
    if (cache.has(k)) { setDataState(cache.get(k) as T); setLoading(false) } else setLoading(true)
    fn().then(d => { cache.set(k, d); if (id === seq.current) { setDataState(d); setLoading(false) } })
      .catch(e => { if (id === seq.current) { setError((e as Error).message); setLoading(false) } })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { run() }, [run])
  return { data, error, loading, reload: run, setData }
}

export function useElapsed(active: boolean) {
  const [s, setS] = useState(0)
  useEffect(() => {
    if (!active) { setS(0); return }
    const start = Date.now()
    const t = setInterval(() => setS(Math.floor((Date.now() - start) / 1000)), 250)
    return () => clearInterval(t)
  }, [active])
  return s
}
