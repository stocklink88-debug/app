import { useState } from 'react'
import { api, type Asset, type Brand } from '../lib/api'
import { useJobWatcher, useSession } from '../lib/session'
import { AssetBrowser } from '../components/pickers'
import { AssetCard, AssetViewer } from '../components/media'
import {
  Badge, EmptyState, Field, Modal, Select, Spinner, Tabs, useAsync, useToast,
} from '../components/ui'
import { IconMegaphone, IconPlus, IconTrash } from '../components/Icons'

export default function Ads() {
  const [tab, setTab] = useState<'generar' | 'marcas' | 'productos'>('generar')
  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <div className="mb-5">
        <h1 className="text-2xl font-black tracking-tight">Estudio de anuncios</h1>
        <p className="text-sm text-zinc-500">
          Del producto al vídeo montado: guion, planos y transiciones en un solo paso.
        </p>
      </div>
      <Tabs value={tab} onChange={setTab}
            tabs={[{ value: 'generar', label: 'Generar anuncio' },
                   { value: 'marcas', label: 'Marcas' },
                   { value: 'productos', label: 'Productos' }]} />
      <div className="mt-5">
        {tab === 'generar' ? <AdGenerator /> : tab === 'marcas' ? <Brands /> : <Products />}
      </div>
    </div>
  )
}

function AdGenerator() {
  const toast = useToast()
  const { refreshUser } = useSession()
  const brands = useAsync(() => api.brands(), [])
  const products = useAsync(() => api.products(), [])
  const [template, setTemplate] = useState('ugc-testimonial')
  const [brandId, setBrandId] = useState('')
  const [productId, setProductId] = useState('')
  const [productName, setProductName] = useState('')
  const [benefit, setBenefit] = useState('')
  const [audience, setAudience] = useState('')
  const [tone, setTone] = useState('cercano')
  const [aspect, setAspect] = useState('9:16')
  const [shots, setShots] = useState(5)
  const [images, setImages] = useState<Asset[]>([])
  const [browsing, setBrowsing] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [viewing, setViewing] = useState<Asset | null>(null)
  const job = useJobWatcher(jobId)

  const templates = brands.data?.templates || []
  const chosen = templates.find((t: any) => t.id === template)

  const generate = async () => {
    setBusy(true)
    try {
      const { job: created } = await api.generateAd({
        template, brand_id: brandId || null, product_id: productId || null,
        product_name: productName, benefit, audience, tone, aspect,
        max_shots: shots, resolution: '720p',
        image_asset_ids: images.map((i) => i.id),
      })
      setJobId(created.id)
      refreshUser()
      toast('Anuncio en cola: escribo el guion y ruedo los planos.', 'ok')
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  return (
    <div className="grid lg:grid-cols-[400px,minmax(0,1fr)] gap-5 items-start">
      <div className="card p-4 space-y-4">
        <Field label="Plantilla">
          <Select value={template} onChange={setTemplate}
                  options={templates.map((t: any) => ({ value: t.id, label: t.name }))} />
        </Field>
        {chosen && (
          <div className="text-[11px] text-zinc-500 leading-relaxed">
            {chosen.description}
            <div className="flex flex-wrap gap-1 mt-2">
              {chosen.beats.map((beat: string) => <Badge key={beat}>{beat}</Badge>)}
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label="Marca">
            <Select value={brandId} onChange={setBrandId}
                    options={[{ value: '', label: 'Ninguna' },
                              ...(brands.data?.brands || []).map((b) => ({ value: b.id, label: b.name }))]} />
          </Field>
          <Field label="Producto">
            <Select value={productId} onChange={(v) => {
                      setProductId(v)
                      const p = products.data?.products.find((x) => x.id === v)
                      if (p) { setProductName(p.name); setBenefit(p.description) }
                    }}
                    options={[{ value: '', label: 'Ninguno' },
                              ...(products.data?.products || []).map((p) => ({ value: p.id, label: p.name }))]} />
          </Field>
        </div>

        <Field label="Producto (texto libre)">
          <input value={productName} onChange={(e) => setProductName(e.target.value)}
                 className="field" placeholder="Cafetera Aurora" />
        </Field>
        <Field label="Beneficio principal">
          <input value={benefit} onChange={(e) => setBenefit(e.target.value)}
                 className="field" placeholder="Café de especialidad en 40 segundos" />
        </Field>
        <Field label="Para quién es">
          <input value={audience} onChange={(e) => setAudience(e.target.value)}
                 className="field" placeholder="gente que sale de casa con prisa" />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Tono">
            <Select value={tone} onChange={setTone}
                    options={['cercano', 'directo', 'elegante', 'divertido', 'técnico']
                      .map((t) => ({ value: t, label: t }))} />
          </Field>
          <Field label="Formato">
            <Select value={aspect} onChange={setAspect}
                    options={['9:16', '16:9', '1:1', '4:5'].map((a) => ({ value: a, label: a }))} />
          </Field>
        </div>

        <Field label={`Planos: ${shots}`}>
          <input type="range" min={2} max={8} value={shots}
                 onChange={(e) => setShots(Number(e.target.value))} className="w-full" />
        </Field>

        <Field label={`Fotos del producto (${images.length})`}
               hint="Si las pones, los planos parten de ellas.">
          <button onClick={() => setBrowsing(true)} className="btn-ghost btn-sm w-full">
            Elegir imágenes
          </button>
        </Field>

        <button onClick={generate} disabled={busy || !productName.trim()}
                className="btn-primary w-full">
          {busy ? <Spinner /> : <IconMegaphone className="w-4 h-4" />}Generar anuncio
        </button>
      </div>

      <div className="space-y-4">
        {!job ? (
          <div className="card border-dashed min-h-[320px] grid place-items-center">
            <EmptyState icon={<IconMegaphone className="w-12 h-12" />}
                        title="Tu anuncio aparecerá aquí"
                        hint="Se escribe el guion, se ruedan los planos y se montan con transición." />
          </div>
        ) : job.status === 'queued' || job.status === 'running' ? (
          <div className="card p-8 min-h-[320px] grid place-items-center text-center">
            <div className="w-full max-w-sm">
              <Spinner className="w-8 h-8 text-brand mx-auto" />
              <p className="font-semibold mt-4">{job.message}</p>
              <div className="h-1.5 rounded-full bg-ink-600 overflow-hidden mt-4">
                <div className="h-full bg-brand transition-all"
                     style={{ width: `${Math.max(job.progress * 100, 5)}%` }} />
              </div>
            </div>
          </div>
        ) : job.status === 'failed' ? (
          <div className="card p-8 text-center">
            <p className="font-semibold text-flame">No ha salido</p>
            <p className="text-sm text-zinc-400 mt-2">{job.error}</p>
          </div>
        ) : (
          <>
            {job.result?.script && <ScriptCard script={job.result.script} />}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {(job.result?.assets || []).map((asset: Asset) => (
                <AssetCard key={asset.id} asset={asset} onOpen={() => setViewing(asset)} compact />
              ))}
            </div>
          </>
        )}
      </div>

      <AssetBrowser open={browsing} onClose={() => setBrowsing(false)} kind="image" multiple
                    onPickMany={setImages} />
      <AssetViewer asset={viewing} onClose={() => setViewing(null)} />
    </div>
  )
}

function ScriptCard({ script }: { script: any }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="label !mb-0">Guion</p>
        <Badge tone={script.source === 'claude' ? 'iris' : 'default'}>{script.source}</Badge>
      </div>
      <p className="font-semibold text-sm mb-3">{script.hook}</p>
      <ol className="space-y-2">
        {(script.shots || []).map((shot: any, i: number) => (
          <li key={i} className="flex gap-3 text-xs">
            <span className="w-5 h-5 rounded bg-white/[0.08] grid place-items-center
                             flex-shrink-0 font-bold text-[10px]">{i + 1}</span>
            <div className="min-w-0">
              <p className="text-zinc-300">{shot.visual}</p>
              {shot.voiceover && <p className="text-zinc-500 italic mt-0.5">«{shot.voiceover}»</p>}
            </div>
          </li>
        ))}
      </ol>
      {script.cta && <p className="text-xs text-brand font-semibold mt-3">{script.cta}</p>}
      {script.hashtags?.length > 0 && (
        <p className="text-[11px] text-zinc-500 mt-2">{script.hashtags.join(' ')}</p>
      )}
    </div>
  )
}

function Brands() {
  const toast = useToast()
  const { data, loading, reload } = useAsync(() => api.brands(), [])
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ name: '', website: '', description: '', tone: '' })

  const create = async () => {
    if (!form.name.trim()) return
    await api.createBrand(form)
    setForm({ name: '', website: '', description: '', tone: '' })
    setCreating(false)
    reload()
    toast('Marca creada', 'ok')
  }

  const remove = async (brand: Brand) => {
    if (!confirm(`¿Borrar ${brand.name}?`)) return
    await api.deleteBrand(brand.id)
    reload()
  }

  return (
    <div>
      <button onClick={() => setCreating(true)} className="btn-primary btn-sm mb-4">
        <IconPlus className="w-4 h-4" />Nueva marca
      </button>
      {loading ? <Spinner /> : (data?.brands.length ?? 0) === 0 ? (
        <EmptyState title="Sin marcas" hint="Una marca guarda tono, paleta y logotipo para reutilizarlos." />
      ) : (
        <div className="grid sm:grid-cols-3 gap-3">
          {data!.brands.map((brand) => (
            <div key={brand.id} className="card p-4">
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <p className="font-semibold truncate">{brand.name}</p>
                  <p className="text-[11px] text-zinc-500">{brand.product_count} productos</p>
                </div>
                <button onClick={() => remove(brand)} className="btn-ghost btn-xs !p-1.5">
                  <IconTrash className="w-3.5 h-3.5" />
                </button>
              </div>
              <p className="text-xs text-zinc-400 mt-2 line-clamp-3">{brand.description}</p>
              {brand.tone && <Badge>{brand.tone}</Badge>}
            </div>
          ))}
        </div>
      )}

      <Modal open={creating} onClose={() => setCreating(false)} title="Nueva marca"
             footer={<button onClick={create} className="btn-primary btn-sm w-full">Crear</button>}>
        <div className="space-y-3">
          <Field label="Nombre">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                   className="field" autoFocus />
          </Field>
          <Field label="Web">
            <input value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })}
                   className="field" placeholder="https://" />
          </Field>
          <Field label="Tono de voz">
            <input value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })}
                   className="field" placeholder="cercano pero preciso" />
          </Field>
          <Field label="Descripción">
            <textarea value={form.description} rows={3} className="field resize-none"
                      onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
        </div>
      </Modal>
    </div>
  )
}

function Products() {
  const toast = useToast()
  const { data, loading, reload } = useAsync(() => api.products(), [])
  const brands = useAsync(() => api.brands(), [])
  const [creating, setCreating] = useState(false)
  const [browsing, setBrowsing] = useState(false)
  const [images, setImages] = useState<Asset[]>([])
  const [form, setForm] = useState({ name: '', brand_id: '', description: '', price: '', url: '' })

  const create = async () => {
    if (!form.name.trim()) return
    await api.createProduct({ ...form, brand_id: form.brand_id || null,
                              asset_ids: images.map((i) => i.id) })
    setForm({ name: '', brand_id: '', description: '', price: '', url: '' })
    setImages([])
    setCreating(false)
    reload()
    toast('Producto creado', 'ok')
  }

  return (
    <div>
      <button onClick={() => setCreating(true)} className="btn-primary btn-sm mb-4">
        <IconPlus className="w-4 h-4" />Nuevo producto
      </button>
      {loading ? <Spinner /> : (data?.products.length ?? 0) === 0 ? (
        <EmptyState title="Sin productos"
                    hint="Guarda fotos y descripción para generar anuncios en un clic." />
      ) : (
        <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {data!.products.map((product) => (
            <div key={product.id} className="card overflow-hidden">
              <div className="h-32 bg-ink-900">
                {product.images[0]?.thumb_url
                  ? <img src={product.images[0].thumb_url} alt="" className="w-full h-full object-cover" />
                  : <div className="w-full h-full grid place-items-center text-zinc-700 text-xs">
                      sin foto</div>}
              </div>
              <div className="p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold text-sm truncate">{product.name}</p>
                  <button onClick={() => api.deleteProduct(product.id).then(reload)}
                          className="btn-ghost btn-xs !p-1">
                    <IconTrash className="w-3.5 h-3.5" />
                  </button>
                </div>
                <p className="text-[11px] text-zinc-500 line-clamp-2 mt-1">{product.description}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={creating} onClose={() => setCreating(false)} title="Nuevo producto"
             footer={<button onClick={create} className="btn-primary btn-sm w-full">Crear</button>}>
        <div className="space-y-3">
          <Field label="Nombre">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                   className="field" autoFocus />
          </Field>
          <Field label="Marca">
            <Select value={form.brand_id} onChange={(v) => setForm({ ...form, brand_id: v })}
                    options={[{ value: '', label: 'Ninguna' },
                              ...(brands.data?.brands || []).map((b) => ({ value: b.id, label: b.name }))]} />
          </Field>
          <Field label="Qué resuelve">
            <textarea value={form.description} rows={3} className="field resize-none"
                      onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
          <Field label={`Fotos (${images.length})`}>
            <button onClick={() => setBrowsing(true)} className="btn-ghost btn-sm w-full">
              Elegir imágenes
            </button>
          </Field>
        </div>
      </Modal>
      <AssetBrowser open={browsing} onClose={() => setBrowsing(false)} kind="image" multiple
                    onPickMany={setImages} />
    </div>
  )
}
