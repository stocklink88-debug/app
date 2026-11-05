import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type Asset } from '../lib/api'
import { STATUS_COLOR, STATUS_LABEL, TYPE_LABEL, relative } from '../lib/format'
import { AssetCard, AssetViewer } from '../components/media'
import { AssetBrowser } from '../components/pickers'
import {
  EmptyState, Field, Modal, Spinner, useAsync, useToast,
} from '../components/ui'
import { IconLayers, IconPlus, IconScissors, IconTrash } from '../components/Icons'

export default function Projects() {
  const navigate = useNavigate()
  const toast = useToast()
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const { data, loading } = useAsync(() => api.projects(), [])

  const create = async () => {
    if (!title.trim()) return
    const { project } = await api.createProject({ title })
    setCreating(false)
    setTitle('')
    toast('Proyecto creado', 'ok')
    navigate(`/proyectos/${project.id}`)
  }

  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <div className="flex items-center gap-3 mb-5">
        <div className="mr-auto">
          <h1 className="text-2xl font-black tracking-tight">Proyectos</h1>
          <p className="text-sm text-zinc-500">Agrupa tomas, móntalas y ten el guion a mano.</p>
        </div>
        <button onClick={() => setCreating(true)} className="btn-primary btn-sm">
          <IconPlus className="w-4 h-4" />Nuevo
        </button>
      </div>

      {loading ? (
        <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-40 rounded-2xl" />)}
        </div>
      ) : (data?.projects.length ?? 0) === 0 ? (
        <EmptyState icon={<IconLayers className="w-12 h-12" />} title="Todavía no hay proyectos"
                    hint="Un proyecto junta todas las tomas de una misma pieza."
                    action={<button onClick={() => setCreating(true)} className="btn-primary btn-sm">
                      Crear el primero</button>} />
      ) : (
        <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {data!.projects.map((project) => (
            <button key={project.id} onClick={() => navigate(`/proyectos/${project.id}`)}
                    className="card card-hover overflow-hidden text-left">
              <div className="h-32 bg-ink-900">
                {project.cover?.thumb_url
                  ? <img src={project.cover.thumb_url} alt="" className="w-full h-full object-cover" />
                  : <div className="w-full h-full grid place-items-center text-zinc-700">
                      <IconLayers className="w-8 h-8" />
                    </div>}
              </div>
              <div className="p-3">
                <p className="font-semibold text-sm truncate">{project.title}</p>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {project.asset_count} elementos · {relative(project.updated_at)}
                </p>
              </div>
            </button>
          ))}
        </div>
      )}

      <Modal open={creating} onClose={() => setCreating(false)} title="Nuevo proyecto"
             footer={<button onClick={create} className="btn-primary btn-sm w-full">Crear</button>}>
        <Field label="Título">
          <input value={title} onChange={(e) => setTitle(e.target.value)} className="field"
                 placeholder="Campaña de primavera" autoFocus
                 onKeyDown={(e) => e.key === 'Enter' && create()} />
        </Field>
      </Modal>
    </div>
  )
}

export function ProjectDetail() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [viewing, setViewing] = useState<Asset | null>(null)
  const [adding, setAdding] = useState(false)
  const [montaging, setMontaging] = useState(false)
  const { data, loading, reload } = useAsync(() => api.project(id), [id])

  const attach = async (assets: Asset[]) => {
    for (const asset of assets) await api.patchAsset(asset.id, { project_id: id })
    reload()
    toast(`${assets.length} elementos añadidos`, 'ok')
  }

  const montage = async () => {
    const clips = (data?.assets || []).filter((a) => a.kind === 'video')
    if (clips.length < 2) { toast('Hacen falta al menos dos vídeos', 'error'); return }
    setMontaging(true)
    try {
      await api.runTool('stitch', {
        clip_asset_ids: clips.map((c) => c.id),
        project_id: id, aspect: '9:16', transition: 'fundido',
      })
      toast('Montaje en cola', 'ok')
      setTimeout(reload, 1500)
    } catch (e: any) { toast(e.message, 'error') } finally { setMontaging(false) }
  }

  const remove = async () => {
    if (!confirm('¿Borrar el proyecto? El material se conserva en la biblioteca.')) return
    await api.deleteProject(id)
    navigate('/proyectos')
  }

  if (loading) return <div className="grid place-items-center py-24"><Spinner className="w-6 h-6" /></div>
  if (!data) return <EmptyState title="No encuentro ese proyecto" />

  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <button onClick={() => navigate('/proyectos')} className="btn-ghost btn-xs mb-4">← Proyectos</button>

      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="mr-auto">
          <h1 className="text-2xl font-black tracking-tight">{data.project.title}</h1>
          <p className="text-sm text-zinc-500">
            {data.assets.length} elementos · {data.jobs.length} generaciones
          </p>
        </div>
        <button onClick={() => setAdding(true)} className="btn-ghost btn-sm">
          <IconPlus className="w-4 h-4" />Añadir material
        </button>
        <button onClick={montage} disabled={montaging} className="btn-ghost btn-sm">
          {montaging ? <Spinner /> : <IconScissors className="w-4 h-4" />}Montar tomas
        </button>
        <button onClick={() => navigate('/crear', { state: { project_id: id } })}
                className="btn-primary btn-sm">Generar aquí</button>
        <button onClick={remove} className="btn-danger btn-sm !p-2"><IconTrash className="w-4 h-4" /></button>
      </div>

      {data.jobs.length > 0 && (
        <div className="card p-3 mb-5">
          <p className="label mb-2">Generaciones del proyecto</p>
          <div className="flex flex-wrap gap-2">
            {data.jobs.slice(0, 12).map((job) => (
              <span key={job.id} className={`pill ${STATUS_COLOR[job.status]}`}>
                {TYPE_LABEL[job.type] || job.type} · {STATUS_LABEL[job.status]}
              </span>
            ))}
          </div>
        </div>
      )}

      {data.assets.length === 0 ? (
        <EmptyState icon={<IconLayers className="w-12 h-12" />} title="El proyecto está vacío"
                    hint="Añade material de la biblioteca o genera directamente dentro del proyecto." />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {data.assets.map((asset) => (
            <AssetCard key={asset.id} asset={asset} onOpen={() => setViewing(asset)} />
          ))}
        </div>
      )}

      <AssetBrowser open={adding} onClose={() => setAdding(false)} multiple onPickMany={attach} />
      <AssetViewer asset={viewing} onClose={() => setViewing(null)} onChanged={reload} />
    </div>
  )
}
