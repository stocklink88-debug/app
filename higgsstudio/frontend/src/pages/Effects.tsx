import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { PresetTile } from '../components/pickers'
import { EmptyState, SearchInput, useAsync, useDebounced } from '../components/ui'
import { IconWand } from '../components/Icons'

export default function Effects() {
  const navigate = useNavigate()
  const [category, setCategory] = useState('todas')
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search, 250)
  const { data, loading } = useAsync(() => api.presets(category, debounced), [category, debounced])
  const all = useAsync(() => api.presets(), [])

  const use = (presetId: string) =>
    navigate('/crear', { state: { family: 'video', mode: 't2v', preset: presetId } })

  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <div className="mb-5">
        <h1 className="text-2xl font-black tracking-tight">Efectos y movimientos de cámara</h1>
        <p className="text-sm text-zinc-500">
          {all.data?.total ?? 0} recetas listas: elige una y se aplica al prompt y a la cámara.
        </p>
      </div>

      <div className="sticky top-14 z-20 -mx-4 sm:-mx-6 px-4 sm:px-6 py-3 bg-ink-950/90 backdrop-blur
                      border-b border-white/[0.06] space-y-3">
        <div className="max-w-md">
          <SearchInput value={search} onChange={setSearch} placeholder="Buscar: bullet time, derretir, pasarela…" />
        </div>
        <div className="flex gap-1.5 overflow-x-auto scroll-x">
          {[{ id: 'todas', name: 'Todas' }, ...(all.data?.categories || [])].map((c) => (
            <button key={c.id} onClick={() => setCategory(c.id)}
                    className={`chip whitespace-nowrap ${category === c.id ? 'chip-active' : ''}`}>
              {c.name}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5">
        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
            {Array.from({ length: 15 }).map((_, i) => (
              <div key={i} className="skeleton h-36 rounded-2xl" />
            ))}
          </div>
        ) : (data?.presets.length ?? 0) === 0 ? (
          <EmptyState icon={<IconWand className="w-12 h-12" />} title="Nada con esa búsqueda"
                      hint="Prueba con otra palabra o cambia de categoría." />
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
            {data!.presets.map((preset) => (
              <PresetTile key={preset.id} preset={preset} onPick={() => use(preset.id)} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
