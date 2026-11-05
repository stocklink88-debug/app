import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, type Capabilities, type Job, type Plan, type User } from './api'

interface SessionValue {
  user: User | null
  plan: Plan | null
  caps: Capabilities | null
  loading: boolean
  jobs: Job[]                        // trabajos activos o recién terminados
  refreshUser: () => Promise<void>
  setUser: (u: User | null) => void
  trackJob: (job: Job) => void
  logout: () => Promise<void>
}

const Ctx = createContext<SessionValue>(null as unknown as SessionValue)
export const useSession = () => useContext(Ctx)

const KEEP = 12  // cuántos trabajos recientes guardamos en memoria

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const [loading, setLoading] = useState(true)
  const [jobs, setJobs] = useState<Job[]>([])
  const source = useRef<EventSource | null>(null)

  const refreshUser = useCallback(async () => {
    try {
      const data = await api.me()
      setUser(data.user)
      setPlan(data.plan)
    } catch {
      setUser(null)
      setPlan(null)
    }
  }, [])

  useEffect(() => {
    Promise.all([refreshUser(), api.capabilities().then(setCaps).catch(() => {})])
      .finally(() => setLoading(false))
  }, [refreshUser])

  const trackJob = useCallback((job: Job) => {
    setJobs((prev) => {
      const rest = prev.filter((j) => j.id !== job.id)
      return [job, ...rest].slice(0, KEEP)
    })
  }, [])

  // Flujo de actividad en vivo (SSE) mientras haya sesión.
  useEffect(() => {
    if (!user) {
      source.current?.close()
      source.current = null
      setJobs([])
      return
    }
    api.activeJobs().then((d) => setJobs(d.jobs.slice(0, KEEP))).catch(() => {})

    const es = new EventSource('/api/activity/stream', { withCredentials: true })
    source.current = es
    es.addEventListener('progress', (event) => {
      try {
        const job = JSON.parse((event as MessageEvent).data) as Job
        trackJob(job)
        if (job.status === 'succeeded' || job.status === 'failed' || job.status === 'canceled') {
          refreshUser()
        }
      } catch { /* evento mal formado: se ignora */ }
    })
    return () => { es.close(); source.current = null }
  }, [user?.id, trackJob, refreshUser])

  const logout = useCallback(async () => {
    await api.logout().catch(() => {})
    setUser(null)
    setPlan(null)
    setJobs([])
  }, [])

  return (
    <Ctx.Provider value={{ user, plan, caps, loading, jobs, refreshUser, setUser, trackJob, logout }}>
      {children}
    </Ctx.Provider>
  )
}

/** Sigue un trabajo concreto hasta que termina. */
export function useJobWatcher(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null)
  const { trackJob } = useSession()

  useEffect(() => {
    if (!jobId) { setJob(null); return }
    let closed = false
    const es = new EventSource(`/api/jobs/${jobId}/stream`, { withCredentials: true })
    es.addEventListener('progress', (event) => {
      try {
        const next = JSON.parse((event as MessageEvent).data) as Job
        if (closed) return
        setJob(next)
        trackJob(next)
        if (['succeeded', 'failed', 'canceled'].includes(next.status)) {
          closed = true
          es.close()
        }
      } catch { /* ignorar */ }
    })
    es.onerror = () => {
      // Si el navegador corta el flujo, caemos a sondeo simple.
      if (closed) return
      es.close()
      const timer = setInterval(async () => {
        try {
          const next = await api.job(jobId)
          setJob(next)
          trackJob(next)
          if (['succeeded', 'failed', 'canceled'].includes(next.status)) clearInterval(timer)
        } catch { clearInterval(timer) }
      }, 2000)
    }
    return () => { closed = true; es.close() }
  }, [jobId, trackJob])

  return job
}
