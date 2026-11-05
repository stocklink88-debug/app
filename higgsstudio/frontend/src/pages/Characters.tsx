import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Asset, type Character } from '../lib/api'
import { useJobWatcher, useSession } from '../lib/session'
import { AssetBrowser } from '../components/pickers'
import { AssetViewer } from '../components/media'
import {
  Badge, EmptyState, Field, Modal, Segmented, Spinner, useAsync, useToast,
} from '../components/ui'
import { IconPlus, IconSpark, IconTrash, IconUser } from '../components/Icons'

export default function Characters() {
  const navigate = useNavigate()
  const { plan } = useSession()
  const [kind, setKind] = useState<'' | 'soul_id' | 'influencer'>('')
  const [creating, setCreating] = useState(false)
  const [open, setOpen] = useState<Character | null>(null)
  const { data, loading, reload } = useAsync(() => api.characters(kind || undefined), [kind])

  const limit = data?.limit ?? 0

  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="mr-auto">
          <h1 className="text-2xl font-black tracking-tight">Personajes</h1>
          <p className="text-sm text-zinc-500">
            Soul ID e influencers de IA: la misma cara en todas tus tomas.
          </p>
        </div>
        <Segmented value={kind} onChange={setKind} size="sm"
                   options={[{ value: '', label: 'Todos' },
                             { value: 'soul_id', label: 'Soul ID' },
                             { value: 'influencer', label: 'Influencers' }]} />
        <button onClick={() => setCreating(true)} className="btn-primary btn-sm">
          <IconPlus className="w-4 h-4" />Nuevo
        </button>
      </div>

      {limit === 0 && (
        <div className="card p-4 mb-5 border-l-2 border-l-brand">
          <p className="text-sm">
            Tu plan ({plan?.name}) no incluye personajes guardados.{' '}
            <button onClick={() => navigate('/creditos')} className="text-brand font-semibold hover:underline">
              Sube de plan
            </button>{' '}
            para crear hasta {`${5}`} identidades reutilizables.
          </p>
        </div>
      )}

      {loading ? (
        <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-56 rounded-2xl" />)}
        </div>
      ) : (data?.characters.length ?? 0) === 0 ? (
        <EmptyState icon={<IconUser className="w-12 h-12" />} title="Aún no hay personajes"
                    hint="Crea uno, sube de 4 a 20 fotos de referencia y entrénalo." />
      ) : (
        <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {data!.characters.map((character) => (
            <button key={character.id} onClick={() => setOpen(character)}
                    className="card card-hover overflow-hidden text-left">
              <div className="h-44 bg-ink-900">
                {character.cover?.thumb_url
                  ? <img src={character.cover.thumb_url} alt="" className="w-full h-full object-cover" />
                  : <div className="w-full h-full grid place-items-center text-zinc-700">
                      <IconUser className="w-10 h-10" />
                    </div>}
              </div>
              <div className="p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-sm truncate">{character.name}</p>
                  <Badge tone={character.status === 'listo' ? 'brand' : 'default'}>
                    {character.status}
                  </Badge>
                </div>
                <p className="text-[11px] text-zinc-500 line-clamp-2 mt-1">
                  {character.description || 'Sin descripción'}
                </p>
              </div>
            </button>
          ))}
        </div>
      )}

      <CreateCharacter open={creating} onClose={() => setCreating(false)}
                       presets={data?.avatar_presets || []} onDone={reload} />
      <CharacterDetail character={open} onClose={() => setOpen(null)} onChanged={reload} />
    </div>
  )
}

function CreateCharacter({ open, onClose, onDone, presets }: {
  open: boolean; onClose: () => void; onDone: () => void; presets: any[]
}) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [kind, setKind] = useState<'soul_id' | 'influencer'>('soul_id')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)

  const create = async () => {
    if (!name.trim()) return
    setBusy(true)
    try {
      await api.createCharacter({ name, kind, description })
      toast('Personaje creado', 'ok')
      onDone()
      onClose()
      setName(''); setDescription('')
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Nuevo personaje"
           footer={<button onClick={create} disabled={busy || !name.trim()}
                           className="btn-primary btn-sm w-full">
             {busy && <Spinner />}Crear</button>}>
      <div className="space-y-4">
        <Field label="Nombre">
          <input value={name} onChange={(e) => setName(e.target.value)} className="field"
                 placeholder="Nora Vidal" autoFocus />
        </Field>
        <Field label="Tipo">
          <Segmented value={kind} onChange={setKind}
                     options={[{ value: 'soul_id', label: 'Soul ID (desde fotos)' },
                               { value: 'influencer', label: 'Influencer (inventado)' }]} />
        </Field>
        <Field label="Descripción"
               hint="Cuanto más concreto, más coherente sale después.">
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
                    className="field resize-none"
                    placeholder="Mujer de 32 años, pelo castaño ondulado, pecas, estilo minimalista" />
        </Field>
        {kind === 'influencer' && presets.length > 0 && (
          <Field label="O parte de una plantilla">
            <div className="grid grid-cols-2 gap-1.5">
              {presets.slice(0, 8).map((preset: any) => (
                <button key={preset.id} onClick={() => setDescription(preset.prompt)}
                        className="card card-hover p-2 text-left text-[11px]">
                  {preset.name}
                </button>
              ))}
            </div>
          </Field>
        )}
      </div>
    </Modal>
  )
}

function CharacterDetail({ character, onClose, onChanged }: {
  character: Character | null; onClose: () => void; onChanged: () => void
}) {
  const navigate = useNavigate()
  const toast = useToast()
  const { refreshUser } = useSession()
  const [adding, setAdding] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [viewing, setViewing] = useState<Asset | null>(null)
  const [busy, setBusy] = useState(false)
  const job = useJobWatcher(jobId)

  if (!character) return null

  const addRefs = async (assets: Asset[]) => {
    const ids = [...character.ref_asset_ids, ...assets.map((a) => a.id)]
    await api.patchCharacter(character.id, { ref_asset_ids: ids })
    onChanged()
    toast('Referencias añadidas', 'ok')
  }

  const train = async () => {
    setBusy(true)
    try {
      const { job: created } = await api.trainCharacter(character.id, { model: 'soul-id' })
      setJobId(created.id)
      refreshUser()
      toast('Entrenando. Tardará un poco.', 'ok')
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const sheet = async () => {
    setBusy(true)
    try {
      const { job: created } = await api.generateSheet({
        character_id: character.id, description: character.description,
        traits: character.traits, count: 6,
      })
      setJobId(created.id)
      refreshUser()
      toast('Generando la hoja de poses', 'ok')
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const remove = async () => {
    if (!confirm(`¿Borrar a ${character.name}?`)) return
    await api.deleteCharacter(character.id)
    onChanged()
    onClose()
  }

  return (
    <>
      <Modal open onClose={onClose} wide title={character.name}>
        <div className="grid lg:grid-cols-[260px,minmax(0,1fr)] gap-5">
          <div className="space-y-3">
            <div className="card overflow-hidden h-48 bg-ink-900">
              {character.cover?.thumb_url
                ? <img src={character.cover.thumb_url} alt="" className="w-full h-full object-cover" />
                : <div className="w-full h-full grid place-items-center text-zinc-700">
                    <IconUser className="w-10 h-10" />
                  </div>}
            </div>
            <div className="flex gap-1.5 flex-wrap">
              <Badge tone="brand">{character.kind}</Badge>
              <Badge>{character.status}</Badge>
              {character.trigger_word && <Badge tone="iris">{character.trigger_word}</Badge>}
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed">{character.description}</p>
            {Object.keys(character.traits || {}).length > 0 && (
              <dl className="text-[11px] grid grid-cols-2 gap-y-1 text-zinc-500">
                {Object.entries(character.traits).slice(0, 8).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="capitalize">{k.replace(/_/g, ' ')}</dt>
                    <dd className="text-zinc-300 truncate">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            )}
            <div className="grid gap-2 pt-2">
              <button onClick={() => setAdding(true)} className="btn-ghost btn-sm">
                <IconPlus className="w-4 h-4" />Añadir referencias ({character.references.length})
              </button>
              <button onClick={train} disabled={busy || character.references.length < 4}
                      className="btn-ghost btn-sm">
                {busy ? <Spinner /> : <IconSpark className="w-4 h-4" />}Entrenar Soul ID
              </button>
              <button onClick={sheet} disabled={busy} className="btn-ghost btn-sm">
                Generar hoja de poses
              </button>
              <button onClick={() => navigate('/crear', {
                        state: { family: 'image', mode: 'soul_id', character_id: character.id } })}
                      className="btn-primary btn-sm">Usar en una generación</button>
              <button onClick={remove} className="btn-danger btn-sm">
                <IconTrash className="w-4 h-4" />Borrar
              </button>
            </div>
          </div>

          <div className="space-y-4">
            {job && (job.status === 'running' || job.status === 'queued') && (
              <div className="card p-4 flex items-center gap-3">
                <Spinner className="w-5 h-5 text-brand" />
                <div className="flex-1">
                  <p className="text-sm font-semibold">{job.message}</p>
                  <div className="h-1 rounded-full bg-ink-600 mt-2 overflow-hidden">
                    <div className="h-full bg-brand" style={{ width: `${job.progress * 100}%` }} />
                  </div>
                </div>
              </div>
            )}

            <div>
              <p className="label">Hoja de poses</p>
              {character.sheet.length === 0 ? (
                <EmptyState title="Sin poses todavía"
                            hint="Genera la hoja para fijar la identidad del personaje." />
              ) : (
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                  {character.sheet.map((asset) => (
                    <button key={asset.id} onClick={() => setViewing(asset)}
                            className="card overflow-hidden aspect-[3/4]">
                      {asset.thumb_url && <img src={asset.thumb_url} alt=""
                                               className="w-full h-full object-cover" />}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {character.references.length > 0 && (
              <div>
                <p className="label">Referencias</p>
                <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
                  {character.references.map((asset) => (
                    <div key={asset.id} className="card overflow-hidden aspect-square">
                      {asset.thumb_url && <img src={asset.thumb_url} alt=""
                                               className="w-full h-full object-cover" />}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </Modal>

      <AssetBrowser open={adding} onClose={() => setAdding(false)} kind="image" multiple
                    onPickMany={addRefs} />
      <AssetViewer asset={viewing} onClose={() => setViewing(null)} />
    </>
  )
}
