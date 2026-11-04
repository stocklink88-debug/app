import { useEffect, useRef, useState } from 'react'
import type { CaptionStyle, Clip, Layout } from '../lib/api'
import { api, formatTimestamp } from '../lib/api'
import { IconCheck, IconCopy, IconDownload, IconRefresh, IconX } from './Icons'
import ScoreRing from './ScoreRing'

interface Props {
  clip: Clip
  onClose: () => void
  onChanged: (clip: Clip) => void
}

const LAYOUTS: { value: Layout; label: string }[] = [
  { value: 'fill', label: 'Seguir sujeto' },
  { value: 'blur', label: 'Fondo borroso' },
  { value: 'split', label: 'Dividido' },
]

const STYLES: { value: CaptionStyle; label: string }[] = [
  { value: 'pop', label: 'Resaltado' },
  { value: 'karaoke', label: 'Karaoke' },
  { value: 'boxed', label: 'Con caja' },
  { value: 'minimal', label: 'Discreto' },
  { value: 'none', label: 'Sin subtítulos' },
]

const BREAKDOWN_LABELS: Record<string, string> = {
  hook: 'Gancho',
  emotion: 'Emoción',
  clarity: 'Claridad',
  completeness: 'Idea completa',
  energy: 'Energía de voz',
  pacing: 'Ritmo',
}

export default function ClipDetail({ clip, onClose, onChanged }: Props) {
  const [current, setCurrent] = useState(clip)
  const [caption, setCaption] = useState(clip.caption)
  const [title, setTitle] = useState(clip.title)
  const [copied, setCopied] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    setCurrent(clip); setCaption(clip.caption); setTitle(clip.title)
  }, [clip])

  // Mientras se remonta el clip, consultamos su estado periódicamente.
  useEffect(() => {
    if (current.status !== 'rendering') {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
      return
    }
    pollRef.current = window.setInterval(async () => {
      try {
        const fresh = await api.getClip(current.id)
        setCurrent(fresh)
        onChanged(fresh)
      } catch { /* se reintenta en el siguiente ciclo */ }
    }, 1800)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [current.status, current.id, onChanged])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [onClose])

  async function copy(text: string, key: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(key)
      setTimeout(() => setCopied(null), 1600)
    } catch {
      setError('El navegador bloqueó el portapapeles.')
    }
  }

  async function save() {
    setSaving(true); setError(null)
    try {
      const updated = await api.updateClip(current.id, { title, caption })
      setCurrent(updated); onChanged(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar.')
    } finally {
      setSaving(false)
    }
  }

  async function rerender(patch: { layout?: Layout; caption_style?: CaptionStyle }) {
    setError(null)
    try {
      const updated = await api.rerenderClip(current.id, patch)
      setCurrent(updated); onChanged(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo volver a montar.')
    }
  }

  const fullCaption = [current.caption, current.hashtags.join(' ')].filter(Boolean).join('\n\n')
  const breakdown = Object.entries(current.score_breakdown)
    .filter(([k, v]) => k in BREAKDOWN_LABELS && typeof v === 'number')

  return (
    <div
      className="fixed inset-0 z-50 bg-ink-900/85 backdrop-blur-sm overflow-y-auto"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="min-h-full flex items-start justify-center p-4 sm:p-8">
        <div className="card w-full max-w-5xl overflow-hidden rise">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.07]">
            <div className="flex items-center gap-3 min-w-0">
              <ScoreRing score={current.score} size={38} />
              <div className="min-w-0">
                <p className="text-xs text-slate-400 font-mono">
                  {formatTimestamp(current.start)} – {formatTimestamp(current.end)} · {current.duration.toFixed(0)}s
                </p>
              </div>
            </div>
            <button onClick={onClose} className="btn-ghost btn-sm"><IconX /></button>
          </div>

          <div className="grid lg:grid-cols-[minmax(0,320px)_1fr] gap-6 p-5 sm:p-6">
            {/* Reproductor */}
            <div>
              <div className="rounded-2xl overflow-hidden bg-ink-900 border border-white/10">
                {current.video_url && current.status === 'ready' ? (
                  <video
                    key={`${current.video_url}-${current.status}`}
                    src={current.video_url} controls playsInline
                    poster={current.thumb_url ?? undefined}
                    className="w-full aspect-[9/16] object-contain bg-black"
                  />
                ) : (
                  <div className="aspect-[9/16] grid place-items-center text-slate-500 gap-2.5">
                    <div className="w-7 h-7 rounded-full border-2 border-accent/30 border-t-accent animate-spin" />
                    <span className="text-xs">Montando el clip…</span>
                  </div>
                )}
              </div>

              <div className="flex gap-2 mt-3">
                <a
                  href={`/api/clips/${current.id}/download`} download
                  className={`btn-primary flex-1 ${current.status !== 'ready' ? 'pointer-events-none opacity-40' : ''}`}
                >
                  <IconDownload /> Descargar
                </a>
                <a href={`/api/clips/${current.id}/srt`} download className="btn-ghost" title="Descargar subtítulos">
                  .srt
                </a>
              </div>
            </div>

            {/* Panel derecho */}
            <div className="space-y-5 min-w-0">
              <div>
                <label className="label">Título</label>
                <input className="field" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>

              {current.summary && (
                <p className="text-sm text-slate-300 leading-relaxed">{current.summary}</p>
              )}

              {current.reasons.length > 0 && (
                <div>
                  <label className="label">Por qué puede funcionar</label>
                  <ul className="space-y-1.5">
                    {current.reasons.map((r, i) => (
                      <li key={i} className="flex gap-2 text-sm text-slate-300">
                        <span className="text-mint mt-0.5 shrink-0">▸</span>
                        <span className="leading-snug">{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {breakdown.length > 0 && (
                <div>
                  <label className="label">Desglose de la puntuación</label>
                  <div className="grid sm:grid-cols-2 gap-x-5 gap-y-2">
                    {breakdown.map(([key, value]) => (
                      <div key={key} className="flex items-center gap-2.5">
                        <span className="text-xs text-slate-400 w-28 shrink-0">{BREAKDOWN_LABELS[key]}</span>
                        <div className="h-1.5 flex-1 rounded-full bg-white/[0.08] overflow-hidden">
                          <div
                            className="h-full rounded-full bg-accent/80"
                            style={{ width: `${Math.round((value as number) * 100)}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-mono text-slate-500 w-7 text-right">
                          {Math.round((value as number) * 100)}
                        </span>
                      </div>
                    ))}
                  </div>
                  {typeof current.score_breakdown.llm === 'number' && (
                    <p className="text-[11px] text-slate-500 mt-2">
                      Claude: {current.score_breakdown.llm} · heurística: {current.score_breakdown.heuristic}
                    </p>
                  )}
                </div>
              )}

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="label mb-0">Texto para publicar</label>
                  <button onClick={() => copy(fullCaption, 'caption')} className="btn-ghost btn-sm">
                    {copied === 'caption' ? <IconCheck className="w-3 h-3 text-mint" /> : <IconCopy className="w-3 h-3" />}
                    {copied === 'caption' ? 'Copiado' : 'Copiar'}
                  </button>
                </div>
                <textarea
                  className="field min-h-[84px] resize-y" value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                />
                {current.hashtags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {current.hashtags.map((t) => <span key={t} className="chip">{t}</span>)}
                  </div>
                )}
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="label">Encuadre</label>
                  <div className="flex flex-wrap gap-1.5">
                    {LAYOUTS.map((l) => (
                      <button
                        key={l.value} disabled={current.status === 'rendering'}
                        onClick={() => rerender({ layout: l.value })}
                        className={`btn btn-sm ${current.layout === l.value ? 'bg-accent text-ink-900' : 'bg-white/[0.06] text-slate-300 hover:bg-white/[0.1]'}`}
                      >{l.label}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="label">Subtítulos</label>
                  <div className="flex flex-wrap gap-1.5">
                    {STYLES.map((s) => (
                      <button
                        key={s.value} disabled={current.status === 'rendering'}
                        onClick={() => rerender({ caption_style: s.value })}
                        className={`btn btn-sm ${current.caption_style === s.value ? 'bg-accent text-ink-900' : 'bg-white/[0.06] text-slate-300 hover:bg-white/[0.1]'}`}
                      >{s.label}</button>
                    ))}
                  </div>
                </div>
              </div>

              {current.transcript && (
                <details className="group">
                  <summary className="label cursor-pointer hover:text-slate-200 transition list-none">
                    Transcripción del clip ▾
                  </summary>
                  <p className="text-xs text-slate-400 leading-relaxed mt-2 max-h-40 overflow-y-auto pr-2">
                    {current.transcript}
                  </p>
                </details>
              )}

              {error && <p className="text-sm text-coral">{error}</p>}

              <div className="flex gap-2 pt-1">
                <button onClick={save} disabled={saving} className="btn-primary">
                  {saving ? 'Guardando…' : 'Guardar cambios'}
                </button>
                <button
                  onClick={() => rerender({})} disabled={current.status === 'rendering'}
                  className="btn-ghost" title="Volver a montar el clip"
                >
                  <IconRefresh /> Remontar
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
