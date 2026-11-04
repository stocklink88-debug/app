import { useCallback, useEffect, useRef, useState } from 'react'
import ClipCard from './components/ClipCard'
import LoginScreen from './components/LoginScreen'
import ClipDetail from './components/ClipDetail'
import { IconBack, IconFilm, IconRefresh, IconSparkles, IconTrash } from './components/Icons'
import PipelineProgress from './components/PipelineProgress'
import UploadForm from './components/UploadForm'
import type { Capabilities, Clip, Project, ProjectOptions } from './lib/api'
import { api, formatDuration, getToken, setToken, subscribeProgress, UnauthorizedError } from './lib/api'

export default function App() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [active, setActive] = useState<Project | null>(null)
  const [openClip, setOpenClip] = useState<Clip | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [locked, setLocked] = useState<boolean | null>(null)
  const unsubscribe = useRef<(() => void) | null>(null)

  const boot = useCallback(async () => {
    try {
      const caps = await api.capabilities()
      setCapabilities(caps)
      setLocked(false)
      refreshProjects()
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        setLocked(true)
        return
      }
      // El servidor responde pero sin capacidades: seguimos sin bloquear.
      setCapabilities(null)
      setLocked(false)
    }
  }, [])

  useEffect(() => {
    api.authStatus()
      .then(({ required }) => {
        if (required && !getToken()) {
          setLocked(true)
          return
        }
        boot()
      })
      .catch(() => boot())
    return () => unsubscribe.current?.()
  }, [boot])

  async function refreshProjects() {
    try {
      setProjects(await api.listProjects())
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        setToken('')
        setLocked(true)
      }
    }
  }

  const loadProject = useCallback(async (id: string) => {
    const project = await api.getProject(id)
    setActive(project)
    return project
  }, [])

  /** Sigue el progreso por SSE y recarga el proyecto en cada cambio de etapa. */
  const watch = useCallback((id: string) => {
    unsubscribe.current?.()
    let lastStage = ''
    unsubscribe.current = subscribeProgress(id, (e) => {
      setActive((prev) =>
        prev && prev.id === id
          ? { ...prev, stage: e.stage, stage_label: e.stage_label, progress: e.progress,
              message: e.message, status: e.status as Project['status'], error: e.error ?? null }
          : prev,
      )
      // Al cambiar de etapa (o al acabar) recargamos para traer los clips nuevos.
      if (e.stage !== lastStage || e.status === 'done' || e.status === 'failed') {
        lastStage = e.stage
        loadProject(id).catch(() => undefined)
      }
      if (e.status === 'done' || e.status === 'failed') {
        refreshProjects()
        unsubscribe.current?.()
        unsubscribe.current = null
      }
    })
  }, [loadProject])

  // Mientras se montan clips refrescamos periódicamente para ver las miniaturas.
  useEffect(() => {
    if (!active || active.stage !== 'render' || active.status !== 'running') return
    const timer = window.setInterval(() => { loadProject(active.id).catch(() => undefined) }, 3000)
    return () => clearInterval(timer)
  }, [active?.id, active?.stage, active?.status, loadProject])

  async function handleSubmit(data: {
    file?: File; subtitles?: File; url?: string; title?: string; options: ProjectOptions
  }) {
    setBusy(true); setError(null)
    try {
      const project = await api.createProject(data)
      setActive(project)
      watch(project.id)
      refreshProjects()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear el proyecto.')
    } finally {
      setBusy(false)
    }
  }

  async function openProject(id: string) {
    setError(null)
    try {
      const project = await loadProject(id)
      if (project.status === 'running' || project.status === 'queued') watch(id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo abrir el proyecto.')
    }
  }

  async function removeProject(id: string) {
    try {
      await api.deleteProject(id)
      if (active?.id === id) setActive(null)
      refreshProjects()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo borrar.')
    }
  }

  async function retry() {
    if (!active) return
    try {
      const project = await api.retryProject(active.id)
      setActive(project)
      watch(project.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo reintentar.')
    }
  }

  function onClipChanged(updated: Clip) {
    setActive((prev) =>
      prev ? { ...prev, clips: prev.clips.map((c) => (c.id === updated.id ? updated : c)) } : prev,
    )
    setOpenClip((prev) => (prev && prev.id === updated.id ? updated : prev))
  }

  const readyClips = active?.clips.filter((c) => c.status === 'ready').length ?? 0

  if (locked === null) {
    return (
      <div className="min-h-screen grid place-items-center">
        <div className="w-7 h-7 rounded-full border-2 border-accent/30 border-t-accent animate-spin" />
      </div>
    )
  }

  if (locked) return <LoginScreen onUnlocked={boot} />

  return (
    <div className="min-h-screen">
      <header className="border-b border-white/[0.07] sticky top-0 z-30 bg-ink-900/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <button onClick={() => setActive(null)} className="flex items-center gap-2.5 group">
            <span className="w-8 h-8 rounded-xl bg-accent grid place-items-center shrink-0">
              <IconSparkles className="w-4 h-4 text-ink-900" />
            </span>
            <span className="font-extrabold tracking-tight text-lg">ViralClips</span>
          </button>

          {capabilities && (
            <div className="hidden sm:flex items-center gap-2 text-[11px]">
              <span className="chip">
                ASR: {capabilities.transcription.provider === 'energy'
                  ? 'sin configurar' : capabilities.transcription.provider}
              </span>
              <span className="chip">
                Selección: {capabilities.llm.enabled ? 'Claude' : 'heurística'}
              </span>
              <span className="chip">
                Caras: {capabilities.face_tracking ? 'sí' : 'no'}
              </span>
            </div>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
        {error && (
          <div className="mb-6 card border-coral/30 bg-coral/[0.06] px-4 py-3 text-sm text-coral">
            {error}
          </div>
        )}

        {!active ? (
          <>
            <div className="text-center max-w-2xl mx-auto mb-10">
              <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight leading-[1.1]">
                De vídeo largo a{' '}
                <span className="text-accent">clips verticales</span> listos para publicar
              </h1>
              <p className="text-slate-400 mt-4 leading-relaxed">
                Transcribe tu vídeo, busca los momentos con más potencial, los recorta en vertical
                siguiendo a quien habla y les pone subtítulos animados.
              </p>
            </div>

            <div className="max-w-3xl mx-auto">
              <UploadForm capabilities={capabilities} busy={busy} onSubmit={handleSubmit} />
            </div>

            {projects.length > 0 && (
              <section className="max-w-3xl mx-auto mt-12">
                <h2 className="text-sm font-semibold text-slate-400 mb-3">Proyectos recientes</h2>
                <div className="space-y-2">
                  {projects.map((p) => (
                    <div key={p.id} className="card px-4 py-3 flex items-center gap-3 hover:border-white/20 transition">
                      <button onClick={() => openProject(p.id)} className="flex items-center gap-3 flex-1 min-w-0 text-left">
                        <IconFilm className="w-4 h-4 text-slate-500 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium truncate">{p.title}</p>
                          <p className="text-[11px] text-slate-500">
                            {formatDuration(p.duration)} · {new Date(p.created_at).toLocaleDateString('es-ES')}
                          </p>
                        </div>
                        <span className={`chip shrink-0 ${
                          p.status === 'done' ? 'text-mint'
                            : p.status === 'failed' ? 'text-coral' : 'text-accent'}`}>
                          {p.status === 'done' ? 'Listo'
                            : p.status === 'failed' ? 'Error'
                            : `${Math.round(p.progress * 100)}%`}
                        </span>
                      </button>
                      <button
                        onClick={() => removeProject(p.id)}
                        className="btn-ghost btn-sm text-slate-500 hover:text-coral"
                        title="Borrar proyecto"
                      ><IconTrash className="w-3.5 h-3.5" /></button>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        ) : (
          <>
            <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
              <div className="min-w-0">
                <button onClick={() => setActive(null)} className="btn-ghost btn-sm mb-3">
                  <IconBack className="w-3.5 h-3.5" /> Volver
                </button>
                <h1 className="text-2xl font-bold truncate">{active.title}</h1>
                <p className="text-sm text-slate-500 mt-1">
                  {formatDuration(active.duration)}
                  {active.width ? ` · ${active.width}×${active.height}` : ''}
                  {active.language ? ` · ${active.language}` : ''}
                  {active.clips.length > 0 ? ` · ${readyClips}/${active.clips.length} clips` : ''}
                </p>
              </div>
              {active.status === 'done' && (
                <button onClick={retry} className="btn-ghost btn-sm">
                  <IconRefresh className="w-3.5 h-3.5" /> Volver a analizar
                </button>
              )}
            </div>

            <div className="mb-8">
              <PipelineProgress project={active} onRetry={retry} />
            </div>

            {active.clips.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                {active.clips.map((clip, i) => (
                  <ClipCard key={clip.id} clip={clip} index={i} onOpen={() => setOpenClip(clip)} />
                ))}
              </div>
            ) : active.status === 'done' ? (
              <p className="text-center text-slate-500 py-12">
                No se encontraron clips. Prueba a bajar la duración mínima.
              </p>
            ) : null}
          </>
        )}
      </main>

      {openClip && (
        <ClipDetail clip={openClip} onClose={() => setOpenClip(null)} onChanged={onClipChanged} />
      )}
    </div>
  )
}
