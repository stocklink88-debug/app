import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type Asset, type Model, type Preset, type Style } from '../lib/api'
import { ASPECT_RATIO } from '../lib/format'
import { IconCheck, IconClose, IconPlus, IconUpload, IconWand } from './Icons'
import {
  Badge, EmptyState, Modal, SearchInput, Segmented, Spinner, useAsync,
  useDebounced, useToast,
} from './ui'

/* ------------------------------- modelos ------------------------------- */

export function ModelPicker({ models, value, onChange, mode }: {
  models: Model[]; value: string; onChange: (id: string) => void; mode?: string
}) {
  const [open, setOpen] = useState(false)
  const usable = useMemo(
    () => (mode ? models.filter((m) => m.modes.includes(mode)) : models),
    [models, mode])
  const current = models.find((m) => m.id === value)

  return (
    <>
      <button onClick={() => setOpen(true)}
              className="w-full card card-hover p-3 flex items-center gap-3 text-left">
        <span className="w-9 h-9 rounded-lg bg-gradient-to-br from-iris to-aqua grid place-items-center
                         text-ink-950 font-black text-xs flex-shrink-0">
          {(current?.name || '?').slice(0, 2).toUpperCase()}
        </span>
        <span className="flex-1 min-w-0">
          <span className="flex items-center gap-2">
            <span className="font-semibold text-sm truncate">{current?.name || 'Elegir modelo'}</span>
            {current?.badge && <Badge tone="brand">{current.badge}</Badge>}
          </span>
          <span className="block text-[11px] text-zinc-500 truncate">
            {current ? `${current.vendor} · ${current.credits_base} cr. base` : 'Ninguno seleccionado'}
          </span>
        </span>
        <span className="text-xs text-zinc-500">Cambiar</span>
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="Elegir modelo" wide>
        <div className="grid sm:grid-cols-2 gap-2.5">
          {usable.map((model) => (
            <button key={model.id}
                    onClick={() => { onChange(model.id); setOpen(false) }}
                    className={`card card-hover p-3.5 text-left ${
                      model.id === value ? 'ring-1 ring-brand' : ''}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-semibold text-sm flex items-center gap-2">
                    {model.name}
                    {model.badge && <Badge tone="brand">{model.badge}</Badge>}
                  </p>
                  <p className="text-[11px] text-zinc-500">{model.vendor}</p>
                </div>
                {model.id === value && <IconCheck className="w-4 h-4 text-brand flex-shrink-0" />}
              </div>
              <p className="text-xs text-zinc-400 mt-2 leading-relaxed">{model.description}</p>
              <div className="flex flex-wrap gap-1 mt-2.5">
                {model.durations?.length ? <Badge>{model.durations.join('/')} s</Badge> : null}
                {model.resolutions?.slice(0, 3).map((r) => <Badge key={r}>{r}</Badge>)}
                {(model.supports as any)?.audio ? <Badge tone="aqua">audio</Badge> : null}
                {(model.supports as any)?.camera_control ? <Badge tone="iris">cámara</Badge> : null}
                <Badge tone="brand">
                  {model.credits_per_second
                    ? `${model.credits_base}+${model.credits_per_second}/s`
                    : `${model.credits_base} cr.`}
                </Badge>
              </div>
            </button>
          ))}
        </div>
        {usable.length === 0 && (
          <EmptyState title="Ningún modelo admite este modo"
                      hint="Cambia de modo o elige otra familia de modelos." />
        )}
      </Modal>
    </>
  )
}

/* -------------------------------- presets -------------------------------- */

export function PresetPicker({ value, onChange, compact }: {
  value: string | null; onChange: (id: string | null) => void; compact?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [category, setCategory] = useState('todas')
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search, 250)
  const { data } = useAsync(() => api.presets(category, debounced), [category, debounced])
  const all = useAsync(() => api.presets(), [])
  const current = all.data?.presets.find((p) => p.id === value)

  return (
    <>
      <button onClick={() => setOpen(true)}
              className={`w-full card card-hover p-3 flex items-center gap-3 text-left ${
                compact ? '!py-2' : ''}`}>
        <span className="w-9 h-9 rounded-lg bg-ink-700 grid place-items-center flex-shrink-0">
          <IconWand className="w-4 h-4 text-brand" />
        </span>
        <span className="flex-1 min-w-0">
          <span className="block font-semibold text-sm truncate">
            {current?.name || 'Sin preset de cámara'}
          </span>
          <span className="block text-[11px] text-zinc-500 truncate">
            {current ? current.prompt : `${all.data?.total ?? 0} movimientos y efectos`}
          </span>
        </span>
        {value && (
          <span onClick={(e) => { e.stopPropagation(); onChange(null) }}
                className="btn-ghost btn-xs !p-1.5" role="button">
            <IconClose className="w-3.5 h-3.5" />
          </span>
        )}
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="Presets de cámara y efectos" wide>
        <div className="space-y-3 sticky -top-4 bg-ink-800 pt-2 pb-3 z-10 -mx-5 px-5 -mt-4">
          <SearchInput value={search} onChange={setSearch} placeholder="Buscar: zoom, órbita, derretir…" />
          <div className="flex gap-1.5 overflow-x-auto scroll-x pb-1">
            {[{ id: 'todas', name: 'Todas' }, ...(all.data?.categories || [])].map((c) => (
              <button key={c.id} onClick={() => setCategory(c.id)}
                      className={`chip whitespace-nowrap ${category === c.id ? 'chip-active' : ''}`}>
                {c.name}
              </button>
            ))}
          </div>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 mt-1">
          {(data?.presets || []).map((preset) => (
            <PresetTile key={preset.id} preset={preset} active={preset.id === value}
                        onPick={() => { onChange(preset.id); setOpen(false) }} />
          ))}
        </div>
        {data && data.presets.length === 0 && (
          <EmptyState title="Nada con esa búsqueda" hint="Prueba con otra palabra o cambia de categoría." />
        )}
      </Modal>
    </>
  )
}

export function PresetTile({ preset, active, onPick }: {
  preset: Preset; active?: boolean; onPick: () => void
}) {
  const hue = useMemo(() => {
    let h = 0
    for (const ch of preset.id) h = (h * 31 + ch.charCodeAt(0)) % 360
    return h
  }, [preset.id])

  return (
    <button onClick={onPick}
            className={`card card-hover overflow-hidden text-left group ${active ? 'ring-1 ring-brand' : ''}`}>
      <div className="relative h-20 overflow-hidden"
           style={{ background: `linear-gradient(135deg, hsl(${hue} 55% 22%), hsl(${(hue + 50) % 360} 60% 12%))` }}>
        <span className="absolute inset-0 grid place-items-center">
          <span className="text-[11px] font-mono text-white/55 tracking-widest uppercase
                           group-hover:scale-110 transition-transform">
            {preset.motion.replace(/_/g, ' ')}
          </span>
        </span>
        {preset.badge && (
          <span className="absolute top-1.5 right-1.5"><Badge tone="brand">{preset.badge}</Badge></span>
        )}
        {preset.needs_image && (
          <span className="absolute bottom-1.5 left-1.5"><Badge tone="iris">necesita foto</Badge></span>
        )}
      </div>
      <div className="p-2.5">
        <p className="font-semibold text-xs truncate">{preset.name}</p>
        <p className="text-[10px] text-zinc-500 line-clamp-2 leading-snug mt-0.5">{preset.prompt}</p>
      </div>
    </button>
  )
}

/* -------------------------------- estilos -------------------------------- */

export function StylePicker({ value, onChange }: {
  value: string | null; onChange: (id: string | null) => void
}) {
  const { data } = useAsync(() => api.styles(), [])
  const [group, setGroup] = useState('foto')
  const styles = (data?.styles || []).filter((s: Style) => s.group === group)

  return (
    <div className="space-y-2">
      <div className="flex gap-1.5 overflow-x-auto scroll-x">
        {(data?.groups || []).map((g) => (
          <button key={g.id} onClick={() => setGroup(g.id)}
                  className={`chip whitespace-nowrap ${group === g.id ? 'chip-active' : ''}`}>
            {g.name}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 max-h-52 overflow-y-auto pr-1">
        {styles.map((style) => (
          <button key={style.id}
                  onClick={() => onChange(style.id === value ? null : style.id)}
                  className={`card card-hover p-2 text-left ${style.id === value ? 'ring-1 ring-brand' : ''}`}>
            <p className="text-xs font-semibold truncate">{style.name}</p>
            <p className="text-[10px] text-zinc-500 line-clamp-2 leading-snug">{style.prompt}</p>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------ assets/subida ------------------------------ */

export function AssetSlot({ label, asset, onPick, onClear, kind = 'image', hint }: {
  label: string; asset: Asset | null; onPick: (asset: Asset) => void
  onClear: () => void; kind?: 'image' | 'video' | 'audio'; hint?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <div>
        <p className="label">{label}</p>
        {asset ? (
          <div className="relative card overflow-hidden group">
            <div className="h-24 bg-ink-900">
              {asset.thumb_url
                ? <img src={asset.thumb_url} alt="" className="w-full h-full object-cover" />
                : <div className="w-full h-full grid place-items-center text-xs text-zinc-500">
                    {asset.kind}
                  </div>}
            </div>
            <button onClick={onClear}
                    className="absolute top-1.5 right-1.5 btn-ghost btn-xs !p-1.5 bg-black/60">
              <IconClose className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <button onClick={() => setOpen(true)}
                  className="w-full h-24 card card-hover border-dashed grid place-items-center
                             text-zinc-500 hover:text-zinc-300">
            <span className="flex flex-col items-center gap-1.5">
              <IconPlus className="w-5 h-5" />
              <span className="text-[11px]">Elegir o subir</span>
            </span>
          </button>
        )}
        {hint && <p className="text-[11px] text-zinc-500 mt-1.5">{hint}</p>}
      </div>
      <AssetBrowser open={open} onClose={() => setOpen(false)} kind={kind}
                    onPick={(a) => { onPick(a); setOpen(false) }} />
    </>
  )
}

export function AssetBrowser({ open, onClose, onPick, kind, multiple, onPickMany }: {
  open: boolean; onClose: () => void; onPick?: (asset: Asset) => void
  kind?: string; multiple?: boolean; onPickMany?: (assets: Asset[]) => void
}) {
  const [tab, setTab] = useState<'biblioteca' | 'subir'>('biblioteca')
  const [selected, setSelected] = useState<Asset[]>([])
  const { data, loading, reload } = useAsync(
    () => api.assets({ kind, limit: 60 }), [kind, open])

  useEffect(() => { if (open) setSelected([]) }, [open])

  return (
    <Modal open={open} onClose={onClose} title="Material" wide
           footer={multiple ? (
             <div className="flex items-center justify-between">
               <span className="text-xs text-zinc-500">{selected.length} seleccionados</span>
               <button disabled={!selected.length}
                       onClick={() => { onPickMany?.(selected); onClose() }}
                       className="btn-primary btn-sm">Usar selección</button>
             </div>
           ) : undefined}>
      <div className="mb-3">
        <Segmented value={tab} onChange={setTab} size="sm"
                   options={[{ value: 'biblioteca', label: 'Mi biblioteca' },
                             { value: 'subir', label: 'Subir archivo' }]} />
      </div>

      {tab === 'subir' ? (
        <Uploader onUploaded={(asset) => {
          reload()
          if (multiple) setSelected((prev) => [...prev, asset])
          else { onPick?.(asset); onClose() }
        }} />
      ) : loading ? (
        <div className="grid place-items-center py-16"><Spinner className="w-6 h-6" /></div>
      ) : (data?.assets.length ?? 0) === 0 ? (
        <EmptyState title="Tu biblioteca está vacía"
                    hint="Sube una imagen o genera algo primero." />
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-2">
          {data!.assets.map((asset) => {
            const isSelected = selected.some((a) => a.id === asset.id)
            return (
              <button key={asset.id}
                      onClick={() => {
                        if (multiple) {
                          setSelected((prev) => isSelected
                            ? prev.filter((a) => a.id !== asset.id)
                            : [...prev, asset])
                        } else { onPick?.(asset) }
                      }}
                      className={`relative card overflow-hidden ${isSelected ? 'ring-2 ring-brand' : ''}`}>
                <div className="bg-ink-900" style={{ aspectRatio: asset.width && asset.height
                  ? `${asset.width} / ${asset.height}` : '1 / 1' }}>
                  {asset.thumb_url
                    ? <img src={asset.thumb_url} alt="" loading="lazy" className="w-full h-full object-cover" />
                    : <div className="w-full h-full grid place-items-center text-[10px] text-zinc-500">
                        {asset.kind}
                      </div>}
                </div>
                {isSelected && (
                  <span className="absolute top-1 right-1 w-5 h-5 rounded-full bg-brand
                                   text-ink-950 grid place-items-center">
                    <IconCheck className="w-3 h-3" />
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </Modal>
  )
}

export function Uploader({ onUploaded, accept = 'image/*,video/*,audio/*', compact }: {
  onUploaded: (asset: Asset) => void; accept?: string; compact?: boolean
}) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const toast = useToast()

  const send = async (files: FileList | File[]) => {
    setBusy(true)
    try {
      for (const file of Array.from(files).slice(0, 12)) {
        const { asset } = await api.upload(file)
        onUploaded(asset)
      }
      toast('Subida completada', 'ok')
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  return (
    <div onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
         onDragLeave={() => setDragging(false)}
         onDrop={(e) => { e.preventDefault(); setDragging(false); send(e.dataTransfer.files) }}
         onClick={() => input.current?.click()}
         className={`card card-hover border-dashed grid place-items-center cursor-pointer
                     ${compact ? 'py-6' : 'py-14'} ${dragging ? 'border-brand bg-brand/5' : ''}`}>
      <input ref={input} type="file" accept={accept} multiple hidden
             onChange={(e) => e.target.files && send(e.target.files)} />
      <div className="text-center px-6">
        {busy ? <Spinner className="w-6 h-6 mx-auto text-brand" />
              : <IconUpload className="w-7 h-7 mx-auto text-zinc-600" />}
        <p className="text-sm text-zinc-300 mt-2.5 font-medium">
          {busy ? 'Subiendo…' : 'Arrastra aquí o haz clic'}
        </p>
        <p className="text-[11px] text-zinc-500 mt-1">Imagen, vídeo o audio</p>
      </div>
    </div>
  )
}

/* ------------------------------ formato/aspect ------------------------------ */

export function AspectPicker({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: string[]
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((aspect) => (
        <button key={aspect} onClick={() => onChange(aspect)}
                className={`flex flex-col items-center gap-1 px-2.5 py-2 rounded-lg border transition-colors
                  ${value === aspect
                    ? 'border-brand bg-brand/10 text-brand'
                    : 'border-white/10 text-zinc-400 hover:border-white/25'}`}>
          <span className="border border-current rounded-sm"
                style={{ aspectRatio: ASPECT_RATIO[aspect] || '16 / 9',
                         width: aspect === '9:16' || aspect === '3:4' || aspect === '2:3' || aspect === '4:5' ? 11 : 22 }} />
          <span className="text-[10px] font-semibold">{aspect}</span>
        </button>
      ))}
    </div>
  )
}
