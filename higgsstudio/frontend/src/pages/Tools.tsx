import { useState } from 'react'
import { api, type Asset } from '../lib/api'
import { useJobWatcher, useSession } from '../lib/session'
import { AssetBrowser, AssetSlot } from '../components/pickers'
import { AssetViewer, MediaPreview } from '../components/media'
import {
  Badge, EmptyState, Field, Select, Slider, Spinner, useAsync, useToast,
} from '../components/ui'
import {
  IconCube, IconFilm, IconImage, IconScissors, IconSpark, IconTool, IconVideo,
} from '../components/Icons'

type ToolId = 'upscale_video' | 'upscale_image' | 'interpolate' | 'reframe'
            | 'outpaint' | 'bg_remove' | 'extend' | 'stitch' | 'to_3d'

interface ToolDef {
  id: ToolId; name: string; description: string; icon: any
  input: 'video' | 'image' | 'any' | 'clips'
}

const TOOLS: ToolDef[] = [
  { id: 'upscale_video', name: 'Upscale de vídeo', input: 'video', icon: IconVideo,
    description: 'Sube la resolución y recupera detalle. Opcionalmente también los fps.' },
  { id: 'upscale_image', name: 'Upscale de imagen', input: 'image', icon: IconImage,
    description: 'Multiplica la resolución hasta 8× manteniendo los bordes limpios.' },
  { id: 'interpolate', name: 'Cámara lenta', input: 'video', icon: IconFilm,
    description: 'Interpola fotogramas para slow motion suave o más fps.' },
  { id: 'reframe', name: 'Reencuadrar', input: 'any', icon: IconScissors,
    description: 'Pasa de 16:9 a 9:16 (o al revés) sin cortar lo importante.' },
  { id: 'outpaint', name: 'Expandir lienzo', input: 'any', icon: IconSpark,
    description: 'Amplía la imagen generando lo que falta alrededor.' },
  { id: 'bg_remove', name: 'Quitar fondo', input: 'any', icon: IconTool,
    description: 'Deja el sujeto recortado con transparencia.' },
  { id: 'extend', name: 'Extender vídeo', input: 'video', icon: IconVideo,
    description: 'Continúa el plano unos segundos más a partir del final.' },
  { id: 'stitch', name: 'Montar tomas', input: 'clips', icon: IconFilm,
    description: 'Une varias tomas con transiciones y música. Gratis, se hace en local.' },
  { id: 'to_3d', name: 'Imagen a 3D', input: 'image', icon: IconCube,
    description: 'Convierte una foto en una malla 3D texturizada (GLB).' },
]

export default function Tools() {
  const [tool, setTool] = useState<ToolDef>(TOOLS[0])
  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <div className="mb-5">
        <h1 className="text-2xl font-black tracking-tight">Herramientas</h1>
        <p className="text-sm text-zinc-500">Posproducción sobre lo que ya tienes.</p>
      </div>

      <div className="grid sm:grid-cols-3 lg:grid-cols-5 gap-2.5 mb-6">
        {TOOLS.map((t) => (
          <button key={t.id} onClick={() => setTool(t)}
                  className={`card card-hover p-3.5 text-left ${
                    tool.id === t.id ? 'ring-1 ring-brand' : ''}`}>
            <t.icon className="w-5 h-5 text-brand mb-2" />
            <p className="font-semibold text-sm">{t.name}</p>
            <p className="text-[11px] text-zinc-500 leading-snug mt-1 line-clamp-2">{t.description}</p>
          </button>
        ))}
      </div>

      <ToolRunner key={tool.id} tool={tool} />
    </div>
  )
}

function ToolRunner({ tool }: { tool: ToolDef }) {
  const toast = useToast()
  const { refreshUser } = useSession()
  const [source, setSource] = useState<Asset | null>(null)
  const [clips, setClips] = useState<Asset[]>([])
  const [music, setMusic] = useState<Asset | null>(null)
  const [browsing, setBrowsing] = useState(false)
  const [factor, setFactor] = useState(2)
  const [targetFps, setTargetFps] = useState(60)
  const [slow, setSlow] = useState(1)
  const [targetAspect, setTargetAspect] = useState('9:16')
  const [fill, setFill] = useState('blur')
  const [extraSeconds, setExtraSeconds] = useState(4)
  const [transition, setTransition] = useState('fundido')
  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [viewing, setViewing] = useState<Asset | null>(null)
  const job = useJobWatcher(jobId)
  const options = useAsync(() => api.options(), [])

  const run = async () => {
    setBusy(true)
    try {
      const body: Record<string, any> = { extra: {} }
      if (tool.input === 'clips') {
        body.clip_asset_ids = clips.map((c) => c.id)
        body.music_asset_id = music?.id ?? null
        body.transition = transition
        body.aspect = '9:16'
      } else if (tool.input === 'video' || (source?.kind === 'video')) {
        body.video_asset_id = source?.id
      } else {
        body.image_asset_ids = source ? [source.id] : []
      }
      if (tool.id === 'upscale_video' || tool.id === 'upscale_image') body.factor = factor
      if (tool.id === 'upscale_video') body.target_fps = targetFps
      if (tool.id === 'interpolate') { body.target_fps = targetFps; body.slow_factor = slow }
      if (tool.id === 'reframe') { body.target_aspect = targetAspect; body.fill = fill }
      if (tool.id === 'outpaint') body.target_aspect = targetAspect
      if (tool.id === 'extend') body.extra_seconds = extraSeconds

      const { job: created } = await api.runTool(tool.id, body)
      setJobId(created.id)
      refreshUser()
      toast('En cola', 'ok')
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const ready = tool.input === 'clips' ? clips.length >= 2 : !!source

  return (
    <div className="grid lg:grid-cols-[380px,minmax(0,1fr)] gap-5 items-start">
      <div className="card p-4 space-y-4">
        <div>
          <h2 className="font-bold">{tool.name}</h2>
          <p className="text-xs text-zinc-500 mt-1">{tool.description}</p>
        </div>

        {tool.input === 'clips' ? (
          <>
            <Field label={`Tomas (${clips.length})`}
                   hint="Se montan en el orden en que las elijas.">
              <button onClick={() => setBrowsing(true)} className="btn-ghost btn-sm w-full">
                Elegir tomas
              </button>
            </Field>
            {clips.length > 0 && (
              <div className="grid grid-cols-4 gap-1.5">
                {clips.map((clip, i) => (
                  <div key={clip.id} className="relative card overflow-hidden aspect-square">
                    {clip.thumb_url && <img src={clip.thumb_url} alt="" className="w-full h-full object-cover" />}
                    <span className="absolute top-1 left-1 text-[10px] font-bold px-1 rounded bg-black/70">
                      {i + 1}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <AssetSlot label="Música (opcional)" kind="audio" asset={music}
                       onPick={setMusic} onClear={() => setMusic(null)} />
            <Field label="Transición">
              <Select value={transition} onChange={setTransition}
                      options={(options.data?.transitions || ['fundido']).map((t: string) => ({
                        value: t, label: t }))} />
            </Field>
          </>
        ) : (
          <AssetSlot label="Material de partida"
                     kind={tool.input === 'video' ? 'video' : 'image'}
                     asset={source} onPick={setSource} onClear={() => setSource(null)} />
        )}

        {(tool.id === 'upscale_video' || tool.id === 'upscale_image') && (
          <Field label={`Factor: ×${factor}`}>
            <Slider value={factor} onChange={setFactor} min={2} max={tool.id === 'upscale_image' ? 8 : 4} step={2} />
          </Field>
        )}
        {(tool.id === 'interpolate' || tool.id === 'upscale_video') && (
          <Field label="FPS de salida">
            <Select value={String(targetFps)} onChange={(v) => setTargetFps(Number(v))}
                    options={[30, 60, 120].map((f) => ({ value: String(f), label: `${f} fps` }))} />
          </Field>
        )}
        {tool.id === 'interpolate' && (
          <Field label={`Ralentizar: ×${slow}`} hint="Con 2× el clip dura el doble.">
            <Slider value={slow} onChange={setSlow} min={1} max={4} step={0.5} />
          </Field>
        )}
        {(tool.id === 'reframe' || tool.id === 'outpaint') && (
          <Field label="Formato de destino">
            <Select value={targetAspect} onChange={setTargetAspect}
                    options={['9:16', '16:9', '1:1', '4:5', '21:9'].map((a) => ({ value: a, label: a }))} />
          </Field>
        )}
        {tool.id === 'reframe' && (
          <Field label="Relleno">
            <Select value={fill} onChange={setFill}
                    options={[{ value: 'blur', label: 'Fondo desenfocado' },
                              { value: 'crop', label: 'Recortar' },
                              { value: 'pad', label: 'Barras negras' }]} />
          </Field>
        )}
        {tool.id === 'extend' && (
          <Field label={`Segundos extra: ${extraSeconds}`}>
            <Slider value={extraSeconds} onChange={setExtraSeconds} min={2} max={10} suffix="s" />
          </Field>
        )}

        <button onClick={run} disabled={busy || !ready} className="btn-primary w-full">
          {busy ? <Spinner /> : <IconTool className="w-4 h-4" />}Ejecutar
        </button>
      </div>

      <div>
        {!job ? (
          <div className="card border-dashed min-h-[320px] grid place-items-center">
            <EmptyState icon={<tool.icon className="w-12 h-12" />} title={tool.name}
                        hint="Elige el material a la izquierda y ejecuta." />
          </div>
        ) : job.status === 'queued' || job.status === 'running' ? (
          <div className="card p-8 min-h-[320px] grid place-items-center text-center">
            <div>
              <Spinner className="w-8 h-8 text-brand mx-auto" />
              <p className="font-semibold mt-4">{job.message}</p>
              <div className="w-64 h-1.5 rounded-full bg-ink-600 overflow-hidden mt-4 mx-auto">
                <div className="h-full bg-brand rounded-full transition-all"
                     style={{ width: `${Math.max(job.progress * 100, 6)}%` }} />
              </div>
            </div>
          </div>
        ) : job.status === 'failed' ? (
          <div className="card p-8 text-center">
            <p className="font-semibold text-flame">No ha salido</p>
            <p className="text-sm text-zinc-400 mt-2">{job.error}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {(job.result?.assets || []).map((asset) => (
              <div key={asset.id} className="card overflow-hidden">
                <div className="bg-black max-h-[60vh] flex items-center justify-center">
                  <MediaPreview asset={asset} />
                </div>
                <div className="p-3 flex items-center justify-between">
                  <div className="flex gap-1.5">
                    <Badge tone="brand">{job.provider}</Badge>
                    <Badge>{job.cost_credits} cr.</Badge>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => setViewing(asset)} className="btn-ghost btn-sm">Detalles</button>
                    <a href={asset.download_url} className="btn-primary btn-sm">Descargar</a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <AssetBrowser open={browsing} onClose={() => setBrowsing(false)} kind="video" multiple
                    onPickMany={setClips} />
      <AssetViewer asset={viewing} onClose={() => setViewing(null)} />
    </div>
  )
}
