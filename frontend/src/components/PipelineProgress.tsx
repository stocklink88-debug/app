import type { Project } from '../lib/api'
import { IconWarning } from './Icons'

const STAGES = [
  { key: 'ingest', label: 'Preparar vídeo' },
  { key: 'transcribe', label: 'Transcribir' },
  { key: 'analyze', label: 'Buscar momentos' },
  { key: 'render', label: 'Montar clips' },
]

interface Props {
  project: Project
  onRetry?: () => void
}

export default function PipelineProgress({ project, onRetry }: Props) {
  const current = STAGES.findIndex((s) => s.key === project.stage)
  const failed = project.status === 'failed'
  const done = project.status === 'done'
  const pct = Math.round(project.progress * 100)

  if (failed) {
    return (
      <div className="card p-6 border-coral/30 bg-coral/[0.06]">
        <div className="flex items-start gap-3">
          <IconWarning className="w-5 h-5 text-coral shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold text-coral">No se pudo completar el proceso</p>
            <p className="text-sm text-slate-300 mt-1.5 leading-relaxed">{project.error}</p>
            {onRetry && (
              <button onClick={onRetry} className="btn-ghost btn-sm mt-3">Reintentar</button>
            )}
          </div>
        </div>
      </div>
    )
  }

  if (done) return null

  return (
    <div className="card p-6">
      <div className="flex items-baseline justify-between mb-4">
        <p className="font-semibold">{project.stage_label}</p>
        <span className="text-sm font-mono text-accent">{pct}%</span>
      </div>

      <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-accent-deep to-accent rounded-full transition-all duration-500"
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>

      {project.message && (
        <p className="text-xs text-slate-400 mt-3">{project.message}</p>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-5">
        {STAGES.map((stage, i) => {
          const state = current < 0 ? 'pending' : i < current ? 'done' : i === current ? 'active' : 'pending'
          return (
            <div
              key={stage.key}
              className={`rounded-xl px-3 py-2.5 border text-xs font-medium transition-colors
                ${state === 'done' ? 'border-mint/30 bg-mint/[0.08] text-mint'
                  : state === 'active' ? 'border-accent/40 bg-accent/[0.08] text-accent animate-pulse-soft'
                  : 'border-white/[0.07] bg-white/[0.02] text-slate-500'}`}
            >
              <span className="block text-[10px] opacity-70 mb-0.5">Paso {i + 1}</span>
              {stage.label}
            </div>
          )
        })}
      </div>
    </div>
  )
}
