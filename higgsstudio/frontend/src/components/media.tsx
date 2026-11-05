import { useEffect, useState } from 'react'
import { api, type Asset, type Virality } from '../lib/api'
import { ASPECT_RATIO, bytes, copy, relative, seconds } from '../lib/format'
import {
  IconDownload, IconHeart, IconPlay, IconSpark, IconStar, IconTrash, IconWand,
} from './Icons'
import { Badge, Modal, Spinner, useToast } from './ui'

/** Vista previa que funciona con vídeo, imagen, audio o malla 3D. */
export function MediaPreview({ asset, autoPlay = false, controls = true, className = '' }: {
  asset: Asset; autoPlay?: boolean; controls?: boolean; className?: string
}) {
  if (asset.kind === 'video') {
    return (
      <video src={asset.url} poster={asset.thumb_url || undefined}
             controls={controls} autoPlay={autoPlay} loop muted={autoPlay} playsInline
             className={`w-full h-full object-contain bg-black ${className}`} />
    )
  }
  if (asset.kind === 'audio') {
    return (
      <div className={`w-full h-full grid place-items-center bg-ink-900 p-6 ${className}`}>
        <div className="w-full max-w-md text-center">
          <div className="flex items-end justify-center gap-1 h-20 mb-5">
            {Array.from({ length: 28 }).map((_, i) => (
              <span key={i} className="w-1.5 rounded-full bg-gradient-to-t from-brand/30 to-brand"
                    style={{ height: `${25 + Math.abs(Math.sin(i * 1.7)) * 70}%` }} />
            ))}
          </div>
          <audio src={asset.url} controls className="w-full" />
        </div>
      </div>
    )
  }
  if (asset.kind === 'model3d') {
    return (
      <div className={`w-full h-full grid place-items-center bg-ink-900 text-center p-8 ${className}`}>
        <div>
          <p className="text-sm text-zinc-400 mb-3">Malla 3D lista para descargar (GLB).</p>
          <a href={asset.download_url} className="btn-primary btn-sm">Descargar modelo</a>
        </div>
      </div>
    )
  }
  return <img src={asset.url} alt={asset.prompt} className={`w-full h-full object-contain ${className}`} />
}

export function AssetCard({ asset, onOpen, selected, onSelect, compact }: {
  asset: Asset; onOpen?: () => void
  selected?: boolean; onSelect?: () => void; compact?: boolean
}) {
  const [hovering, setHovering] = useState(false)
  const ratio = asset.width && asset.height
    ? `${asset.width} / ${asset.height}`
    : ASPECT_RATIO[asset.params?.aspect as string] || '16 / 9'

  return (
    <div className={`group relative card card-hover overflow-hidden cursor-pointer
                     ${selected ? 'ring-2 ring-brand' : ''}`}
         onMouseEnter={() => setHovering(true)} onMouseLeave={() => setHovering(false)}
         onClick={() => (onSelect ? onSelect() : onOpen?.())}>
      <div className="relative bg-ink-900 overflow-hidden" style={{ aspectRatio: ratio }}>
        {asset.kind === 'video' && hovering ? (
          <video src={asset.url} autoPlay loop muted playsInline
                 className="w-full h-full object-cover" />
        ) : asset.thumb_url ? (
          <img src={asset.thumb_url} alt="" loading="lazy"
               className="w-full h-full object-cover" />
        ) : asset.kind === 'audio' ? (
          <div className="w-full h-full grid place-items-center">
            <div className="flex items-end gap-0.5 h-10">
              {Array.from({ length: 16 }).map((_, i) => (
                <span key={i} className="w-1 rounded-full bg-brand/60"
                      style={{ height: `${25 + Math.abs(Math.sin(i * 1.9)) * 70}%` }} />
              ))}
            </div>
          </div>
        ) : (
          <div className="w-full h-full skeleton" />
        )}

        {asset.kind === 'video' && !hovering && (
          <span className="absolute inset-0 grid place-items-center pointer-events-none">
            <span className="w-11 h-11 rounded-full bg-black/55 backdrop-blur grid place-items-center">
              <IconPlay className="w-4 h-4 translate-x-[1px]" />
            </span>
          </span>
        )}
        {asset.duration ? (
          <span className="absolute bottom-2 right-2 text-[10px] font-semibold px-1.5 py-0.5
                           rounded bg-black/65 backdrop-blur tabular-nums">
            {seconds(asset.duration)}
          </span>
        ) : null}
        {asset.favorite && (
          <span className="absolute top-2 left-2 text-brand">
            <IconStar className="w-4 h-4 fill-current" />
          </span>
        )}
        {onOpen && onSelect && (
          <button onClick={(e) => { e.stopPropagation(); onOpen() }}
                  className="absolute top-2 right-2 btn-ghost btn-xs opacity-0 group-hover:opacity-100">
            Ver
          </button>
        )}
      </div>
      {!compact && (
        <div className="p-2.5">
          <p className="text-[11px] text-zinc-400 line-clamp-2 leading-snug min-h-[2rem]">
            {asset.prompt || 'Sin descripción'}
          </p>
          <div className="flex items-center justify-between mt-1.5">
            <span className="text-[10px] text-zinc-600 truncate">{asset.model || asset.source}</span>
            <span className="text-[10px] text-zinc-600">{relative(asset.created_at)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

export function AssetViewer({ asset, onClose, onChanged, onRemix }: {
  asset: Asset | null; onClose: () => void
  onChanged?: () => void; onRemix?: (asset: Asset) => void
}) {
  const toast = useToast()
  const [report, setReport] = useState<Virality | null>(null)
  const [busy, setBusy] = useState(false)
  const [favorite, setFavorite] = useState(asset?.favorite ?? false)

  useEffect(() => { setFavorite(asset?.favorite ?? false); setReport(null) }, [asset?.id])
  if (!asset) return null

  const toggleFavorite = async () => {
    setFavorite(!favorite)
    await api.patchAsset(asset.id, { favorite: !favorite }).catch(() => setFavorite(favorite))
    onChanged?.()
  }

  const publish = async () => {
    setBusy(true)
    try {
      await api.publish({ asset_id: asset.id, title: asset.prompt.slice(0, 120) })
      toast('Publicado en la galería', 'ok')
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const analyze = async () => {
    setBusy(true)
    try { setReport(await api.virality({ asset_id: asset.id })) }
    catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const remove = async () => {
    if (!confirm('¿Borrar este material de la biblioteca?')) return
    await api.deleteAsset(asset.id)
    toast('Borrado', 'ok')
    onChanged?.()
    onClose()
  }

  return (
    <Modal open wide onClose={onClose} title={null as unknown as React.ReactNode}>
      <div className="grid lg:grid-cols-[minmax(0,1fr),300px] gap-5 -m-1">
        <div className="rounded-xl overflow-hidden bg-black min-h-[300px] max-h-[70vh] flex">
          <MediaPreview asset={asset} autoPlay />
        </div>

        <div className="flex flex-col gap-4 min-w-0">
          <div className="flex flex-wrap gap-1.5">
            <Badge tone="brand">{asset.kind}</Badge>
            {asset.model && <Badge>{asset.model}</Badge>}
            {asset.preset && <Badge tone="iris">{asset.preset}</Badge>}
            {asset.seed !== null && <Badge>semilla {asset.seed}</Badge>}
          </div>

          <div>
            <p className="label">Prompt</p>
            <p className="text-sm text-zinc-300 leading-relaxed break-words">
              {asset.prompt || '—'}
            </p>
            {asset.prompt && (
              <button onClick={() => { copy(asset.prompt); toast('Prompt copiado', 'ok') }}
                      className="btn-ghost btn-xs mt-2">Copiar prompt</button>
            )}
          </div>

          <dl className="text-xs grid grid-cols-2 gap-y-1.5 text-zinc-500">
            {asset.width ? <><dt>Tamaño</dt><dd className="text-zinc-300">{asset.width}×{asset.height}</dd></> : null}
            {asset.duration ? <><dt>Duración</dt><dd className="text-zinc-300">{seconds(asset.duration)}</dd></> : null}
            {asset.fps ? <><dt>FPS</dt><dd className="text-zinc-300">{asset.fps}</dd></> : null}
            <dt>Peso</dt><dd className="text-zinc-300">{bytes(asset.size_bytes)}</dd>
            <dt>Creado</dt><dd className="text-zinc-300">{relative(asset.created_at)}</dd>
          </dl>

          {report && (
            <div className="card p-3 space-y-2">
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-brand tabular-nums">{report.score}</span>
                <span className="text-xs text-zinc-500">/100 · mejor en {report.best_platform}</span>
              </div>
              {Object.entries(report.breakdown).map(([k, v]) => (
                <div key={k} className="flex items-center gap-2">
                  <span className="text-[11px] w-20 text-zinc-500 capitalize">{k}</span>
                  <span className="flex-1 h-1.5 rounded-full bg-ink-600 overflow-hidden">
                    <span className="block h-full bg-brand rounded-full" style={{ width: `${v}%` }} />
                  </span>
                  <span className="text-[11px] tabular-nums w-7 text-right text-zinc-400">{v}</span>
                </div>
              ))}
              <ul className="text-[11px] text-zinc-400 list-disc pl-4 space-y-1 pt-1">
                {report.tips.map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 mt-auto">
            <a href={asset.download_url} className="btn-primary btn-sm col-span-2">
              <IconDownload className="w-4 h-4" />Descargar
            </a>
            {onRemix && (
              <button onClick={() => onRemix(asset)} className="btn-ghost btn-sm col-span-2">
                <IconWand className="w-4 h-4" />Usar estos ajustes
              </button>
            )}
            <button onClick={toggleFavorite} className="btn-ghost btn-sm">
              <IconHeart className={`w-4 h-4 ${favorite ? 'fill-current text-flame' : ''}`} />
              {favorite ? 'Quitar' : 'Favorito'}
            </button>
            <button onClick={analyze} disabled={busy} className="btn-ghost btn-sm">
              {busy ? <Spinner /> : <IconSpark className="w-4 h-4" />}Viralidad
            </button>
            <button onClick={publish} disabled={busy} className="btn-ghost btn-sm">Publicar</button>
            <button onClick={remove} className="btn-danger btn-sm">
              <IconTrash className="w-4 h-4" />Borrar
            </button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
