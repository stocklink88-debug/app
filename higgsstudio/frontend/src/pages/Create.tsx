import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, type Asset, type GenerateParams, type Job, type Model, type Quote } from '../lib/api'
import { TYPE_LABEL } from '../lib/format'
import { useJobWatcher, useSession } from '../lib/session'
import {
  AspectPicker, AssetBrowser, AssetSlot, ModelPicker, PresetPicker, StylePicker,
} from '../components/pickers'
import { AssetCard, AssetViewer, MediaPreview } from '../components/media'
import {
  Badge, EmptyState, Field, Segmented, Select, Slider, Spinner, Tabs, Toggle,
  useAsync, useToast,
} from '../components/ui'
import {
  IconBolt, IconImage, IconMic, IconSpark, IconVideo, IconWave,
} from '../components/Icons'

type Family = 'video' | 'image' | 'speak' | 'audio'

const FAMILY_TABS: { value: Family; label: string }[] = [
  { value: 'video', label: 'Vídeo' },
  { value: 'image', label: 'Imagen' },
  { value: 'speak', label: 'Hablar' },
  { value: 'audio', label: 'Audio' },
]

const MODE_OPTIONS: Record<Family, { value: string; label: string }[]> = {
  video: [
    { value: 't2v', label: 'Texto → vídeo' },
    { value: 'i2v', label: 'Imagen → vídeo' },
    { value: 'frames', label: 'Primer/último fotograma' },
    { value: 'motion', label: 'Transferir movimiento' },
  ],
  image: [
    { value: 't2i', label: 'Texto → imagen' },
    { value: 'i2i', label: 'Imagen → imagen' },
    { value: 'edit', label: 'Editar' },
    { value: 'soul_id', label: 'Con personaje' },
  ],
  speak: [
    { value: 'speak', label: 'Foto que habla' },
    { value: 'lipsync', label: 'Sincronizar labios' },
  ],
  audio: [
    { value: 'tts', label: 'Locución' },
    { value: 'music', label: 'Música' },
    { value: 'sfx', label: 'Efectos' },
    { value: 'v2a', label: 'Sonido para vídeo' },
    { value: 'dubbing', label: 'Doblaje' },
    { value: 'voice_change', label: 'Cambiar voz' },
  ],
}

const DEFAULT_MODEL: Record<Family, string> = {
  video: 'higgs-dop-turbo', image: 'soul-2', speak: 'higgs-speak-v2', audio: 'voice-v3',
}

const AUDIO_MODEL_FOR_MODE: Record<string, string> = {
  tts: 'voice-v3', music: 'music-v1', sfx: 'sfx-v1',
  v2a: 'mmaudio-v2', dubbing: 'dubbing-v1', voice_change: 'voice-changer',
}

export default function Create() {
  const location = useLocation()
  const navigate = useNavigate()
  const preload = (location.state || {}) as Record<string, any>
  const [family, setFamily] = useState<Family>(preload.family || 'video')

  useEffect(() => {
    if (preload.family) setFamily(preload.family)
  }, [preload.family])

  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <div className="flex items-center justify-between gap-4 mb-5">
        <div>
          <h1 className="text-2xl font-black tracking-tight">Crear</h1>
          <p className="text-sm text-zinc-500">Elige qué quieres generar y afina los ajustes.</p>
        </div>
      </div>

      <Tabs value={family} onChange={(v) => { setFamily(v); navigate('/crear', { replace: true }) }}
            tabs={FAMILY_TABS} />

      <div className="mt-5">
        <Composer key={family} family={family} preload={preload} />
      </div>
    </div>
  )
}

function Composer({ family, preload }: { family: Family; preload: Record<string, any> }) {
  const toast = useToast()
  const { refreshUser, caps } = useSession()
  const [mode, setMode] = useState<string>(preload.mode || MODE_OPTIONS[family][0].value)
  const [modelId, setModelId] = useState(preload.model || DEFAULT_MODEL[family])
  const [prompt, setPrompt] = useState(preload.prompt || '')
  const [negative, setNegative] = useState('')
  const [preset, setPreset] = useState<string | null>(preload.preset ?? null)
  const [style, setStyle] = useState<string | null>(preload.style ?? null)
  const [aspect, setAspect] = useState(preload.aspect || (family === 'image' ? '3:4' : '16:9'))
  const [resolution, setResolution] = useState(preload.resolution || (family === 'image' ? '1k' : '720p'))
  const [duration, setDuration] = useState<number>(preload.duration || 5)
  const [fps, setFps] = useState(24)
  const [count, setCount] = useState(1)
  const [seed, setSeed] = useState<string>('')
  const [withAudio, setWithAudio] = useState(false)
  const [enhance, setEnhance] = useState(false)
  const [characterId, setCharacterId] = useState<string | null>(preload.character_id ?? null)
  const [voiceId, setVoiceId] = useState<string | null>(null)
  const [emotion, setEmotion] = useState('neutral')
  const [language, setLanguage] = useState('es')
  const [script, setScript] = useState('')
  const [startImage, setStartImage] = useState<Asset | null>(null)
  const [endImage, setEndImage] = useState<Asset | null>(null)
  const [refImages, setRefImages] = useState<Asset[]>([])
  const [video, setVideo] = useState<Asset | null>(null)
  const [audio, setAudio] = useState<Asset | null>(null)
  const [quote, setQuote] = useState<Quote | null>(null)
  const [busy, setBusy] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [viewing, setViewing] = useState<Asset | null>(null)
  const [browsingRefs, setBrowsingRefs] = useState(false)

  const job = useJobWatcher(jobId)
  const models = useAsync(() => api.models(family), [family])
  const voices = useAsync(() => api.voices(), [])
  const characters = useAsync(() => api.characters(), [])
  const options = useAsync(() => api.options(), [])
  const recent = useAsync(() => api.assets({ limit: 12 }), [job?.status])

  const model: Model | undefined = models.data?.models.find((m) => m.id === modelId)

  // Al cambiar de modo en audio, cambia también el modelo que toca.
  useEffect(() => {
    if (family === 'audio' && AUDIO_MODEL_FOR_MODE[mode]) setModelId(AUDIO_MODEL_FOR_MODE[mode])
  }, [family, mode])

  // Ajusta formato y resolución a lo que el modelo admite.
  useEffect(() => {
    if (!model) return
    if (model.aspects?.length && !model.aspects.includes(aspect)) setAspect(model.aspects[0])
    if (model.resolutions?.length && !model.resolutions.includes(resolution)) {
      setResolution(model.resolutions[Math.min(1, model.resolutions.length - 1)])
    }
    if (model.durations?.length && !model.durations.includes(duration)) setDuration(model.durations[0])
  }, [model?.id])

  // Un preset trae su duración y formato recomendados.
  useEffect(() => {
    if (!preset) return
    api.presets().then(({ presets }) => {
      const found = presets.find((p) => p.id === preset)
      if (!found) return
      if (model?.durations?.includes(found.duration)) setDuration(found.duration)
      if (model?.aspects?.includes(found.aspect)) setAspect(found.aspect)
    }).catch(() => {})
  }, [preset])

  const params = useMemo<GenerateParams>(() => ({
    model: modelId,
    mode,
    prompt: family === 'audio' && mode !== 'tts' ? prompt : prompt,
    negative_prompt: negative,
    duration, aspect, resolution, fps, count,
    seed: seed === '' ? null : Number(seed),
    preset, style, character_id: characterId, voice_id: voiceId,
    image_asset_ids: [
      ...(startImage ? [startImage.id] : []),
      ...refImages.map((a) => a.id),
    ],
    end_image_asset_id: endImage?.id ?? null,
    video_asset_id: video?.id ?? null,
    audio_asset_id: audio?.id ?? null,
    with_audio: withAudio,
    enhance_prompt: enhance,
    extra: { script: script || undefined, emotion, language },
  }), [modelId, mode, prompt, negative, duration, aspect, resolution, fps, count, seed,
       preset, style, characterId, voiceId, startImage, endImage, refImages, video,
       audio, withAudio, enhance, script, emotion, language, family])

  // Presupuesto en vivo.
  useEffect(() => {
    let alive = true
    const timer = setTimeout(() => {
      api.quote({ ...params, type: family })
        .then((q) => alive && setQuote(q))
        .catch(() => alive && setQuote(null))
    }, 320)
    return () => { alive = false; clearTimeout(timer) }
  }, [params, family])

  const runEnhance = async () => {
    if (!prompt.trim()) return
    setBusy(true)
    try {
      const result = await api.enhancePrompt({ prompt, kind: family, style: style || '', preset: preset || '' })
      setPrompt(result.prompt)
      toast(result.source === 'claude' ? 'Prompt mejorado con Claude' : 'Prompt enriquecido', 'ok')
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const generate = async () => {
    setBusy(true)
    try {
      const call = family === 'video' ? api.generateVideo
                 : family === 'image' ? api.generateImage
                 : family === 'speak' ? api.generateSpeak
                 : api.generateAudio
      const { job: created } = await call(params)
      setJobId(created.id)
      refreshUser()
      toast('En cola. Te aviso cuando esté.', 'ok')
    } catch (e: any) {
      toast(e.message, 'error')
    } finally { setBusy(false) }
  }

  const needsStart = ['i2v', 'frames', 'i2i', 'edit', 'style', 'speak'].includes(mode)
  const needsVideo = ['motion', 'lipsync', 'v2a', 'dubbing'].includes(mode)
  const needsAudio = mode === 'voice_change'
  const isAudioOnly = family === 'audio'
  const supports = (model?.supports || {}) as Record<string, any>

  return (
    <div className="grid lg:grid-cols-[minmax(0,420px),minmax(0,1fr)] gap-5 items-start">
      {/* ---------------- panel de ajustes ---------------- */}
      <div className="space-y-4">
        <Segmented value={mode} onChange={setMode} size="sm" options={MODE_OPTIONS[family]} />

        <ModelPicker models={models.data?.models || []} value={modelId}
                     onChange={setModelId} mode={mode} />

        {!(isAudioOnly && ['v2a', 'voice_change'].includes(mode)) && (
          <Field label={isAudioOnly && mode === 'tts' ? 'Texto a leer'
                        : isAudioOnly ? 'Describe el sonido' : 'Prompt'}
                 right={caps?.prompt_enhance || true ? (
                   <button onClick={runEnhance} disabled={busy || !prompt.trim()}
                           className="btn-ghost btn-xs">
                     <IconSpark className="w-3.5 h-3.5" />Mejorar
                   </button>
                 ) : undefined}>
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
                      rows={isAudioOnly && mode === 'tts' ? 5 : 4}
                      className="field resize-none leading-relaxed"
                      placeholder={placeholderFor(family, mode)} />
          </Field>
        )}

        {family === 'video' && (
          <PresetPicker value={preset} onChange={setPreset} />
        )}

        {family === 'image' && (
          <Field label="Estilo"><StylePicker value={style} onChange={setStyle} /></Field>
        )}

        {/* entradas de material */}
        <div className="grid grid-cols-2 gap-3">
          {needsStart && (
            <AssetSlot label={mode === 'frames' ? 'Primer fotograma' : 'Imagen de partida'}
                       asset={startImage} onPick={setStartImage}
                       onClear={() => setStartImage(null)} />
          )}
          {mode === 'frames' && (
            <AssetSlot label="Último fotograma" asset={endImage} onPick={setEndImage}
                       onClear={() => setEndImage(null)} />
          )}
          {needsVideo && (
            <AssetSlot label="Vídeo" kind="video" asset={video} onPick={setVideo}
                       onClear={() => setVideo(null)} />
          )}
          {(needsAudio || family === 'speak') && (
            <AssetSlot label={family === 'speak' ? 'Audio (opcional)' : 'Audio'} kind="audio"
                       asset={audio} onPick={setAudio} onClear={() => setAudio(null)}
                       hint={family === 'speak' ? 'Si lo dejas vacío, se genera con la voz elegida.' : undefined} />
          )}
          {mode === 'motion' && (
            <AssetSlot label="Imagen a animar" asset={startImage} onPick={setStartImage}
                       onClear={() => setStartImage(null)} />
          )}
        </div>

        {/* referencias extra */}
        {Number(supports.references || 0) > 1 && (
          <Field label={`Referencias (${refImages.length}/${supports.references})`}
                 hint="Imágenes que guían estilo, personaje o composición.">
            <button onClick={() => setBrowsingRefs(true)} className="btn-ghost btn-sm w-full">
              Elegir referencias
            </button>
            {refImages.length > 0 && (
              <div className="grid grid-cols-4 gap-1.5 mt-2">
                {refImages.map((asset) => (
                  <button key={asset.id}
                          onClick={() => setRefImages(refImages.filter((a) => a.id !== asset.id))}
                          className="card overflow-hidden aspect-square relative group">
                    {asset.thumb_url && (
                      <img src={asset.thumb_url} alt="" className="w-full h-full object-cover" />
                    )}
                    <span className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100
                                     grid place-items-center text-[10px] font-semibold">quitar</span>
                  </button>
                ))}
              </div>
            )}
          </Field>
        )}

        {/* voz y guion */}
        {(family === 'speak' || (isAudioOnly && ['tts', 'dubbing', 'voice_change'].includes(mode))) && (
          <>
            <Field label="Voz">
              <Select value={voiceId || ''} onChange={(v) => setVoiceId(v || null)}
                      options={[{ value: '', label: 'Elegir voz…' },
                                ...(voices.data?.voices || []).map((v) => ({
                                  value: v.id,
                                  label: `${v.name}${v.labels?.accent ? ` · ${v.labels.accent}` : ''}`,
                                }))]} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Emoción">
                <Select value={emotion} onChange={setEmotion}
                        options={(options.data?.emotions || [{ id: 'neutral', name: 'Neutral' }])
                          .map((e: any) => ({ value: e.id, label: e.name }))} />
              </Field>
              <Field label="Idioma">
                <Select value={language} onChange={setLanguage}
                        options={(options.data?.languages || [{ id: 'es', name: 'Español' }])
                          .map((l: any) => ({ value: l.id, label: l.name }))} />
              </Field>
            </div>
            {family === 'speak' && !audio && (
              <Field label="Qué dice" hint="Se convierte en voz con la voz elegida.">
                <textarea value={script} onChange={(e) => setScript(e.target.value)} rows={3}
                          className="field resize-none" placeholder="Hola, hoy te enseño…" />
              </Field>
            )}
          </>
        )}

        {/* personaje */}
        {(family === 'image' && mode === 'soul_id') || family === 'video' ? (
          (characters.data?.characters.length ?? 0) > 0 && (
            <Field label="Personaje (Soul ID)">
              <Select value={characterId || ''} onChange={(v) => setCharacterId(v || null)}
                      options={[{ value: '', label: 'Ninguno' },
                                ...(characters.data?.characters || []).map((c) => ({
                                  value: c.id, label: `${c.name} · ${c.status}`,
                                }))]} />
            </Field>
          )
        ) : null}

        {/* formato */}
        {!isAudioOnly && (
          <Field label="Formato">
            <AspectPicker value={aspect} onChange={setAspect}
                          options={model?.aspects || ['16:9', '9:16', '1:1']} />
          </Field>
        )}

        <div className="grid grid-cols-2 gap-3">
          {!isAudioOnly && (
            <Field label="Resolución">
              <Select value={resolution} onChange={setResolution}
                      options={(model?.resolutions || ['720p']).map((r) => ({ value: r, label: r }))} />
            </Field>
          )}
          {(family === 'video' || family === 'speak' || isAudioOnly) && (
            <Field label="Duración">
              {model?.durations?.length ? (
                <Select value={String(duration)} onChange={(v) => setDuration(Number(v))}
                        options={model.durations.map((d) => ({ value: String(d), label: `${d} s` }))} />
              ) : (
                <Slider value={duration} onChange={setDuration} min={3}
                        max={isAudioOnly && mode === 'music' ? 180 : 60} step={1} suffix="s" />
              )}
            </Field>
          )}
        </div>

        <details className="card p-3.5">
          <summary className="text-xs font-semibold text-zinc-400 cursor-pointer select-none">
            Ajustes avanzados
          </summary>
          <div className="space-y-3.5 mt-3.5">
            {supports.negative_prompt && (
              <Field label="Prompt negativo" hint="Qué no quieres ver.">
                <textarea value={negative} onChange={(e) => setNegative(e.target.value)} rows={2}
                          className="field resize-none" placeholder="borroso, manos deformes…" />
              </Field>
            )}
            {supports.seed && (
              <Field label="Semilla" hint="Deja vacío para que sea aleatoria. La misma semilla repite el resultado.">
                <input value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ''))}
                       className="field" placeholder="aleatoria" inputMode="numeric" />
              </Field>
            )}
            {!isAudioOnly && (
              <Field label={`Cuántas versiones: ${count}`}>
                <Slider value={count} onChange={setCount} min={1} max={family === 'image' ? 8 : 4} />
              </Field>
            )}
            {family === 'video' && (
              <Field label={`FPS: ${fps}`}>
                <Slider value={fps} onChange={setFps} min={12} max={30} step={2} />
              </Field>
            )}
            {supports.audio && (
              <Toggle checked={withAudio} onChange={setWithAudio} label="Generar con sonido"
                      hint="Este modelo puede crear audio junto al vídeo." />
            )}
            <Toggle checked={enhance} onChange={setEnhance} label="Mejorar el prompt al generar"
                    hint="Añade óptica, luz y color antes de enviarlo al modelo." />
          </div>
        </details>

        {/* acción */}
        <div className="card p-3.5 space-y-3 sticky bottom-3 shadow-2xl shadow-black/60 !bg-ink-800">
          <div className="flex items-center justify-between text-sm">
            <span className="text-zinc-400">Coste</span>
            <span className="font-bold tabular-nums">
              {quote ? `${quote.credits} créditos` : '—'}
            </span>
          </div>
          {quote && quote.affordable === false && (
            <p className="text-[11px] text-flame">
              No te llegan los créditos. Tienes {quote.balance}.
            </p>
          )}
          <button onClick={generate}
                  disabled={busy || (job?.status === 'running') || (job?.status === 'queued')}
                  className="btn-primary w-full !py-3">
            {busy ? <Spinner /> : <IconBolt className="w-4 h-4" />}
            Generar
          </button>
        </div>
      </div>

      {/* ---------------- panel de resultado ---------------- */}
      <div className="space-y-4">
        <ResultPanel job={job} onOpen={setViewing} family={family} />

        <div>
          <div className="flex items-center justify-between mb-2.5">
            <h3 className="text-sm font-bold text-zinc-300">Lo último que has hecho</h3>
          </div>
          {recent.loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="skeleton aspect-video rounded-2xl" />
              ))}
            </div>
          ) : (recent.data?.assets.length ?? 0) === 0 ? (
            <EmptyState icon={<IconVideo className="w-10 h-10" />}
                        title="Aún no has generado nada"
                        hint="Escribe un prompt, elige un preset de cámara y dale a generar." />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {recent.data!.assets.map((asset) => (
                <AssetCard key={asset.id} asset={asset} onOpen={() => setViewing(asset)} compact />
              ))}
            </div>
          )}
        </div>
      </div>

      <AssetBrowser open={browsingRefs} onClose={() => setBrowsingRefs(false)} kind="image"
                    multiple onPickMany={(assets) =>
                      setRefImages(assets.slice(0, Number(supports.references || 4)))} />

      <AssetViewer asset={viewing} onClose={() => setViewing(null)}
                   onChanged={() => recent.reload()} />
    </div>
  )
}

function ResultPanel({ job, onOpen, family }: {
  job: Job | null; onOpen: (a: Asset) => void; family: Family
}) {
  const toast = useToast()
  if (!job) {
    return (
      <div className="card grid place-items-center min-h-[320px] border-dashed">
        <EmptyState
          icon={family === 'video' ? <IconVideo className="w-12 h-12" />
               : family === 'image' ? <IconImage className="w-12 h-12" />
               : family === 'speak' ? <IconMic className="w-12 h-12" />
               : <IconWave className="w-12 h-12" />}
          title="Aquí aparecerá tu generación"
          hint="Configura lo que quieras a la izquierda y pulsa Generar." />
      </div>
    )
  }

  if (job.status === 'queued' || job.status === 'running') {
    return (
      <div className="card p-6 min-h-[320px] flex flex-col items-center justify-center text-center">
        <Spinner className="w-8 h-8 text-brand" />
        <p className="font-semibold mt-4">{job.message || 'Preparando'}</p>
        <p className="text-xs text-zinc-500 mt-1">
          {TYPE_LABEL[job.type] || job.type} · {job.model}
        </p>
        <div className="w-full max-w-sm h-1.5 rounded-full bg-ink-600 overflow-hidden mt-5">
          <div className="h-full bg-brand rounded-full transition-all duration-500"
               style={{ width: `${Math.max(job.progress * 100, 6)}%` }} />
        </div>
        <button onClick={() => api.cancelJob(job.id).then(() => toast('Cancelado', 'ok'))}
                className="btn-ghost btn-sm mt-5">Cancelar</button>
      </div>
    )
  }

  if (job.status === 'failed') {
    return (
      <div className="card p-6 min-h-[200px] flex flex-col items-center justify-center text-center">
        <p className="font-semibold text-flame">No ha salido</p>
        <p className="text-sm text-zinc-400 mt-2 max-w-lg whitespace-pre-wrap">{job.error}</p>
        <p className="text-xs text-zinc-600 mt-3">
          Los créditos se te han devuelto automáticamente.
        </p>
        <button onClick={() => api.retryJob(job.id).then(() => toast('Reintentando', 'ok'))}
                className="btn-ghost btn-sm mt-4">Reintentar</button>
      </div>
    )
  }

  const assets = job.result?.assets || []
  if (!assets.length) {
    return (
      <div className="card p-6 min-h-[200px] grid place-items-center text-center">
        <div>
          <p className="font-semibold">Trabajo terminado</p>
          {job.result?.report && (
            <p className="text-sm text-zinc-400 mt-2">
              Puntuación de viralidad: <b className="text-brand">{job.result.report.score}</b>/100
            </p>
          )}
        </div>
      </div>
    )
  }

  const [first, ...rest] = assets
  return (
    <div className="space-y-3">
      <div className="card overflow-hidden">
        <div className="bg-black max-h-[62vh] flex items-center justify-center">
          <MediaPreview asset={first} autoPlay />
        </div>
        <div className="p-3 flex items-center justify-between gap-3">
          <div className="flex gap-1.5 flex-wrap">
            <Badge tone="brand">{job.provider || 'local'}</Badge>
            <Badge>{job.model}</Badge>
            <Badge>{job.cost_credits} cr.</Badge>
          </div>
          <div className="flex gap-2">
            <button onClick={() => onOpen(first)} className="btn-ghost btn-sm">Detalles</button>
            <a href={first.download_url} className="btn-primary btn-sm">Descargar</a>
          </div>
        </div>
      </div>
      {rest.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2.5">
          {rest.map((asset) => (
            <AssetCard key={asset.id} asset={asset} onOpen={() => onOpen(asset)} compact />
          ))}
        </div>
      )}
    </div>
  )
}

function placeholderFor(family: Family, mode: string): string {
  if (family === 'image') return 'una mujer con chaqueta roja en una azotea de Tokio, luz de neón'
  if (family === 'speak') return 'tono y actitud del personaje al hablar'
  if (mode === 'music') return 'lo-fi melancólico con piano y vinilo, 80 bpm'
  if (mode === 'sfx') return 'puerta metálica cerrándose de golpe con eco'
  if (mode === 'tts') return 'Escribe aquí lo que quieres que diga.'
  return 'un coche derrapando en una calle mojada de neón, cámara baja'
}
