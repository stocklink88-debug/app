import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Asset } from '../lib/api'
import { bytes } from '../lib/format'
import { AssetCard, AssetViewer } from '../components/media'
import { Uploader } from '../components/pickers'
import {
  Badge, EmptyState, Modal, SearchInput, Segmented, useAsync, useDebounced, useToast,
} from '../components/ui'
import { IconGrid, IconPlus, IconUpload } from '../components/Icons'

export default function Library() {
  const navigate = useNavigate()
  const toast = useToast()
  const [kind, setKind] = useState('')
  const [search, setSearch] = useState('')
  const [favorite, setFavorite] = useState(false)
  const [collection, setCollection] = useState<string>('')
  const debounced = useDebounced(search, 300)
  const [viewing, setViewing] = useState<Asset | null>(null)
  const [uploading, setUploading] = useState(false)

  const list = useAsync(
    () => collection
      ? api.collectionItems(collection).then((d) => ({ assets: d.assets, total: d.assets.length, usage: null }))
      : api.assets({ kind, search: debounced, favorite: favorite || undefined, limit: 120 }),
    [kind, debounced, favorite, collection])
  const collections = useAsync(() => api.collections(), [])

  const newCollection = async () => {
    const name = prompt('Nombre de la colección')
    if (!name) return
    await api.createCollection(name)
    collections.reload()
    toast('Colección creada', 'ok')
  }

  const remix = (asset: Asset) => {
    navigate('/crear', {
      state: {
        family: asset.kind === 'image' ? 'image' : asset.kind === 'audio' ? 'audio' : 'video',
        prompt: asset.prompt, model: asset.model, preset: asset.preset,
        aspect: asset.params?.aspect, resolution: asset.params?.resolution,
        duration: asset.params?.duration, style: asset.params?.style,
      },
    })
  }

  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="mr-auto">
          <h1 className="text-2xl font-black tracking-tight">Biblioteca</h1>
          <p className="text-sm text-zinc-500">
            {list.data?.total ?? 0} elementos
            {list.data?.usage ? ` · ${bytes(list.data.usage.bytes)}` : ''}
          </p>
        </div>
        <button onClick={() => setUploading(true)} className="btn-ghost btn-sm">
          <IconUpload className="w-4 h-4" />Subir
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="w-full sm:w-60"><SearchInput value={search} onChange={setSearch}
                                                     placeholder="Buscar por prompt…" /></div>
        <Segmented value={kind} onChange={(v) => { setKind(v); setCollection('') }} size="sm"
                   options={[{ value: '', label: 'Todo' },
                             { value: 'video', label: 'Vídeo' },
                             { value: 'image', label: 'Imagen' },
                             { value: 'audio', label: 'Audio' }]} />
        <button onClick={() => setFavorite(!favorite)}
                className={`chip ${favorite ? 'chip-active' : ''}`}>Favoritos</button>
        <div className="flex items-center gap-1.5 overflow-x-auto scroll-x">
          {(collections.data?.collections || []).map((c: any) => (
            <button key={c.id} onClick={() => setCollection(collection === c.id ? '' : c.id)}
                    className={`chip whitespace-nowrap ${collection === c.id ? 'chip-active' : ''}`}>
              {c.name} <span className="opacity-60">{c.items}</span>
            </button>
          ))}
          <button onClick={newCollection} className="chip whitespace-nowrap">
            <IconPlus className="w-3 h-3" />Colección
          </button>
        </div>
      </div>

      {list.loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="skeleton aspect-[4/5] rounded-2xl" />
          ))}
        </div>
      ) : (list.data?.assets.length ?? 0) === 0 ? (
        <EmptyState icon={<IconGrid className="w-12 h-12" />} title="No hay nada aquí todavía"
                    hint="Genera algo o sube material para empezar tu biblioteca."
                    action={<button onClick={() => navigate('/crear')} className="btn-primary btn-sm">
                      Ir a crear</button>} />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {list.data!.assets.map((asset) => (
            <AssetCard key={asset.id} asset={asset} onOpen={() => setViewing(asset)} />
          ))}
        </div>
      )}

      {list.data?.usage && (
        <div className="flex flex-wrap gap-2 mt-6">
          {Object.entries(list.data.usage.by_kind as Record<string, any>).map(([k, v]) => (
            <Badge key={k}>{k}: {v.count} · {bytes(v.bytes)}</Badge>
          ))}
        </div>
      )}

      <Modal open={uploading} onClose={() => setUploading(false)} title="Subir material">
        <Uploader onUploaded={() => { list.reload() }} />
      </Modal>

      <AssetViewer asset={viewing} onClose={() => setViewing(null)}
                   onChanged={() => list.reload()} onRemix={remix} />
    </div>
  )
}
