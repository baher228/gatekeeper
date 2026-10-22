import { useCallback, useEffect, useRef, useState } from 'react'

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  const run = useCallback(() => {
    const id = ++seq.current
    setLoading(true); setError(null)
    fn().then(d => { if (id === seq.current) { setData(d); setLoading(false) } })
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
