import { useRef, useState } from 'react'
import type { AudioMode, Capabilities, CaptionStyle, Layout, ProjectOptions } from '../lib/api'
import VoicePicker from './VoicePicker'
import { IconFilm, IconLink, IconSparkles, IconUpload, IconX } from './Icons'

interface Props {
  capabilities: Capabilities | null
  busy: boolean
  onSubmit: (data: { file?: File; subtitles?: File; url?: string; title?: string; options: ProjectOptions }) => void
}

const LAYOUT_INFO: Record<Layout, { name: string; desc: string }> = {
  fill: { name: 'Seguir al sujeto', desc: 'Recorta en vertical y sigue a quien habla' },
  blur: { name: 'Fondo desenfocado', desc: 'Vídeo completo sobre un fondo borroso' },
  split: { name: 'Dividido', desc: 'Primer plano arriba, plano general abajo' },
}

const CAPTION_INFO: Record<CaptionStyle, string> = {
  pop: 'Palabra resaltada',
  karaoke: 'Karaoke',
  boxed: 'Con caja',
  minimal: 'Discreto',
  none: 'Sin subtítulos',
}

const AUDIO_INFO: Record<AudioMode, { name: string; desc: string }> = {
  original: { name: 'Audio original', desc: 'Se conserva el sonido del vídeo' },
  mute: { name: 'Silenciar', desc: 'Clips mudos, sólo imagen y subtítulos' },
  voiceover: { name: 'Voz de IA', desc: 'Sustituye la voz por una locución generada' },
}

const DEFAULTS: ProjectOptions = {
  clip_count: 8,
  min_duration: 15,
  max_duration: 75,
  layout: 'fill',
  caption_style: 'pop',
  aspect: '9:16',
  language: null,
  output_language: null,
  keywords: null,
  normalize_audio: true,
  resolution: 1080,
  audio_mode: 'original',
  voice_id: null,
  background_volume: 0,
}

export default function UploadForm({ capabilities, busy, onSubmit }: Props) {
  const [mode, setMode] = useState<'file' | 'url'>('file')
  const [file, setFile] = useState<File | null>(null)
  const [subtitles, setSubtitles] = useState<File | null>(null)
  const [url, setUrl] = useState('')
  const [dragging, setDragging] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [opts, setOpts] = useState<ProjectOptions>(capabilities?.defaults ?? DEFAULTS)
  const [error, setError] = useState<string | null>(null)

  const fileInput = useRef<HTMLInputElement>(null)
  const subsInput = useRef<HTMLInputElement>(null)

  const maxMb = capabilities?.max_upload_mb ?? 4096
  const needsSubtitles = capabilities ? !capabilities.transcription.has_text : false

  function set<K extends keyof ProjectOptions>(key: K, value: ProjectOptions[K]) {
    setOpts((o) => ({ ...o, [key]: value }))
  }

  function pickFile(f: File | null) {
    if (!f) return
    if (f.size > maxMb * 1024 * 1024) {
      setError(`El archivo supera el límite de ${maxMb} MB.`)
      return
    }
    setError(null)
    setFile(f)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const dropped = Array.from(e.dataTransfer.files)
    const video = dropped.find((f) => f.type.startsWith('video/') || /\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(f.name))
    const subs = dropped.find((f) => /\.(srt|vtt)$/i.test(f.name))
    if (video) pickFile(video)
    if (subs) setSubtitles(subs)
    if (!video && !subs) setError('Suelta un archivo de vídeo (mp4, mov, mkv, webm…).')
  }

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (opts.min_duration >= opts.max_duration) {
      setError('La duración mínima debe ser menor que la máxima.')
      return
    }
    if (mode === 'file') {
      if (!file) return setError('Elige un vídeo primero.')
      onSubmit({ file, subtitles: subtitles ?? undefined, options: opts })
    } else {
      if (!/^https?:\/\//i.test(url.trim())) return setError('Pega una URL que empiece por http:// o https://')
      onSubmit({ url: url.trim(), subtitles: subtitles ?? undefined, options: opts })
    }
  }

  return (
    <form onSubmit={submit} className="card p-6 sm:p-8">
      <div className="flex gap-2 mb-6">
        {(['file', 'url'] as const).map((m) => (
          <button
            key={m} type="button" onClick={() => setMode(m)}
            className={`btn flex-1 ${mode === m ? 'bg-accent text-ink-900' : 'bg-white/[0.06] text-slate-300 hover:bg-white/[0.1]'}`}
          >
            {m === 'file' ? <IconUpload /> : <IconLink />}
            {m === 'file' ? 'Subir vídeo' : 'Desde una URL'}
          </button>
        ))}
      </div>

      {mode === 'file' ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInput.current?.click()}
          className={`rounded-2xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors
            ${dragging ? 'border-accent bg-accent/5' : 'border-white/15 hover:border-white/30 hover:bg-white/[0.02]'}`}
        >
          <input
            ref={fileInput} type="file" accept="video/*,.mp4,.mov,.mkv,.webm,.avi,.m4v"
            className="hidden" onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <div className="flex items-center justify-center gap-3">
              <IconFilm className="w-5 h-5 text-accent" />
              <div className="text-left">
                <p className="font-semibold text-sm">{file.name}</p>
                <p className="text-xs text-slate-400">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
              </div>
              <button
                type="button" className="btn-ghost btn-sm ml-2"
                onClick={(e) => { e.stopPropagation(); setFile(null) }}
              ><IconX className="w-3 h-3" /></button>
            </div>
          ) : (
            <>
              <IconUpload className="w-8 h-8 mx-auto mb-3 text-slate-500" />
              <p className="font-semibold text-sm">Arrastra tu vídeo aquí o haz clic para elegirlo</p>
              <p className="text-xs text-slate-500 mt-1.5">
                mp4, mov, mkv, webm · hasta {maxMb >= 1024 ? `${(maxMb / 1024).toFixed(0)} GB` : `${maxMb} MB`}
              </p>
            </>
          )}
        </div>
      ) : (
        <div>
          <input
            className="field" placeholder="https://www.youtube.com/watch?v=…"
            value={url} onChange={(e) => setUrl(e.target.value)} autoComplete="off"
          />
          <p className="text-xs text-slate-500 mt-2">
            YouTube, Vimeo, Twitch y cualquier otra fuente que soporte yt-dlp.
          </p>
        </div>
      )}

      {needsSubtitles && (
        <div className="mt-4 rounded-xl bg-accent/[0.07] border border-accent/20 p-3.5">
          <p className="text-xs text-accent-soft leading-relaxed">
            <strong>No hay transcripción automática configurada.</strong> Sin ella los clips
            se eligen sólo por la energía del audio y salen sin subtítulos. Añade una clave de
            Groq u OpenAI, instala <code className="font-mono">faster-whisper</code>, o sube
            aquí los subtítulos del vídeo.
          </p>
        </div>
      )}

      <div className="mt-4 flex items-center gap-3 flex-wrap">
        <input
          ref={subsInput} type="file" accept=".srt,.vtt" className="hidden"
          onChange={(e) => setSubtitles(e.target.files?.[0] ?? null)}
        />
        <button type="button" className="btn-ghost btn-sm" onClick={() => subsInput.current?.click()}>
          {subtitles ? `Subtítulos: ${subtitles.name}` : 'Añadir subtítulos .srt / .vtt (opcional)'}
        </button>
        {subtitles && (
          <button type="button" className="btn-ghost btn-sm" onClick={() => setSubtitles(null)}>
            <IconX className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* Ajustes rápidos */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6">
        <div>
          <label className="label">Nº de clips</label>
          <input
            type="number" min={1} max={30} className="field"
            value={opts.clip_count}
            onChange={(e) => set('clip_count', Math.min(30, Math.max(1, Number(e.target.value) || 1)))}
          />
        </div>
        <div>
          <label className="label">Mín. (s)</label>
          <input
            type="number" min={5} max={180} className="field"
            value={opts.min_duration}
            onChange={(e) => set('min_duration', Number(e.target.value) || 5)}
          />
        </div>
        <div>
          <label className="label">Máx. (s)</label>
          <input
            type="number" min={10} max={300} className="field"
            value={opts.max_duration}
            onChange={(e) => set('max_duration', Number(e.target.value) || 60)}
          />
        </div>
        <div>
          <label className="label">Formato</label>
          <select className="field" value={opts.aspect} onChange={(e) => set('aspect', e.target.value)}>
            <option value="9:16">9:16 vertical</option>
            <option value="4:5">4:5 feed</option>
            <option value="1:1">1:1 cuadrado</option>
            <option value="16:9">16:9 horizontal</option>
          </select>
        </div>
      </div>

      {/* Encuadre */}
      <div className="mt-5">
        <label className="label">Encuadre</label>
        <div className="grid sm:grid-cols-3 gap-2">
          {(['fill', 'blur', 'split'] as Layout[]).map((l) => (
            <button
              key={l} type="button" onClick={() => set('layout', l)}
              className={`text-left rounded-xl border p-3 transition
                ${opts.layout === l ? 'border-accent/60 bg-accent/[0.08]' : 'border-white/10 hover:border-white/25 bg-white/[0.02]'}`}
            >
              <p className="text-sm font-semibold">{LAYOUT_INFO[l].name}</p>
              <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">{LAYOUT_INFO[l].desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Audio */}
      <div className="mt-5">
        <label className="label">Audio</label>
        <div className="grid sm:grid-cols-3 gap-2">
          {(Object.keys(AUDIO_INFO) as AudioMode[]).map((m) => {
            const blocked = m === 'voiceover' && capabilities?.voice.enabled === false
            return (
              <button
                key={m} type="button" disabled={blocked}
                onClick={() => set('audio_mode', m)}
                title={blocked ? 'Requiere ELEVENLABS_API_KEY en el servidor' : undefined}
                className={`text-left rounded-xl border p-3 transition disabled:opacity-40
                  ${opts.audio_mode === m
                    ? 'border-accent/60 bg-accent/[0.08]'
                    : 'border-white/10 hover:border-white/25 bg-white/[0.02]'}`}
              >
                <p className="text-sm font-semibold">{AUDIO_INFO[m].name}</p>
                <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                  {AUDIO_INFO[m].desc}
                </p>
              </button>
            )
          })}
        </div>

        {opts.audio_mode === 'voiceover' && (
          <div className="mt-3 space-y-3 rise">
            <VoicePicker value={opts.voice_id} onChange={(v) => set('voice_id', v)} />
            <div>
              <label className="label">
                Audio original de fondo: {Math.round(opts.background_volume * 100)}%
              </label>
              <input
                type="range" min={0} max={60} step={5}
                value={Math.round(opts.background_volume * 100)}
                onChange={(e) => set('background_volume', Number(e.target.value) / 100)}
                className="w-full accent-accent"
              />
              <p className="text-[11px] text-slate-500 mt-1">
                En 0% la locución sustituye al sonido original por completo.
              </p>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              La locución lee la transcripción de cada clip. Los subtítulos se
              resincronizan con la voz nueva, no con el audio sustituido.
            </p>
          </div>
        )}
      </div>

      {/* Subtítulos */}
      <div className="mt-5">
        <label className="label">Estilo de subtítulos</label>
        <div className="flex flex-wrap gap-2">
          {(Object.keys(CAPTION_INFO) as CaptionStyle[]).map((c) => (
            <button
              key={c} type="button" onClick={() => set('caption_style', c)}
              className={`btn btn-sm ${opts.caption_style === c ? 'bg-accent text-ink-900' : 'bg-white/[0.06] text-slate-300 hover:bg-white/[0.1]'}`}
            >{CAPTION_INFO[c]}</button>
          ))}
        </div>
      </div>

      <button
        type="button" onClick={() => setAdvanced((a) => !a)}
        className="mt-5 text-xs text-slate-400 hover:text-slate-200 transition"
      >
        {advanced ? '− Ocultar ajustes avanzados' : '+ Ajustes avanzados'}
      </button>

      {advanced && (
        <div className="grid sm:grid-cols-2 gap-3 mt-3 rise">
          <div>
            <label className="label">Tema a priorizar</label>
            <input
              className="field" placeholder="p. ej. inversión, inmobiliaria"
              value={opts.keywords ?? ''}
              onChange={(e) => set('keywords', e.target.value || null)}
            />
          </div>
          <div>
            <label className="label">Idioma del audio</label>
            <select
              className="field" value={opts.language ?? ''}
              onChange={(e) => set('language', e.target.value || null)}
            >
              <option value="">Detectar automáticamente</option>
              <option value="es">Español</option>
              <option value="en">Inglés</option>
              <option value="pt">Portugués</option>
              <option value="fr">Francés</option>
              <option value="it">Italiano</option>
              <option value="de">Alemán</option>
            </select>
          </div>
          <div>
            <label className="label">Resolución</label>
            <select
              className="field" value={opts.resolution}
              onChange={(e) => set('resolution', Number(e.target.value))}
            >
              <option value={720}>720p (rápido)</option>
              <option value={1080}>1080p (recomendado)</option>
              <option value={1440}>1440p</option>
            </select>
          </div>
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input
                type="checkbox" checked={opts.normalize_audio}
                onChange={(e) => set('normalize_audio', e.target.checked)}
                className="w-4 h-4 rounded accent-accent"
              />
              <span className="text-sm text-slate-300">Normalizar volumen a −14 LUFS</span>
            </label>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-4 text-sm text-coral bg-coral/10 border border-coral/20 rounded-xl px-3.5 py-2.5">
          {error}
        </p>
      )}

      <button type="submit" disabled={busy} className="btn-primary w-full mt-6 py-3">
        <IconSparkles />
        {busy ? 'Subiendo…' : 'Generar clips'}
      </button>
    </form>
  )
}
