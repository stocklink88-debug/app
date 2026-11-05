import { useState } from 'react'
import { api } from '../lib/api'
import { copy, relative } from '../lib/format'
import { useSession } from '../lib/session'
import {
  Badge, EmptyState, Field, Modal, Spinner, Tabs, useAsync, useToast,
} from '../components/ui'
import { IconPlus, IconTrash } from '../components/Icons'

export default function Settings() {
  const [tab, setTab] = useState<'perfil' | 'api' | 'webhooks' | 'uso'>('perfil')
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-5">
        <h1 className="text-2xl font-black tracking-tight">Ajustes</h1>
      </div>
      <Tabs value={tab} onChange={setTab}
            tabs={[{ value: 'perfil', label: 'Perfil' },
                   { value: 'api', label: 'API' },
                   { value: 'webhooks', label: 'Webhooks' },
                   { value: 'uso', label: 'Uso' }]} />
      <div className="mt-5">
        {tab === 'perfil' ? <Profile /> : tab === 'api' ? <ApiKeys />
          : tab === 'webhooks' ? <Webhooks /> : <Usage />}
      </div>
    </div>
  )
}

function Profile() {
  const { user, caps, refreshUser } = useSession()
  const toast = useToast()
  const [name, setName] = useState(user?.name || '')
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [busy, setBusy] = useState(false)

  const saveName = async () => {
    setBusy(true)
    try { await api.updateMe({ name }); await refreshUser(); toast('Guardado', 'ok') }
    catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const savePassword = async () => {
    setBusy(true)
    try {
      await api.changePassword({ current_password: current, new_password: next })
      toast('Contraseña cambiada. Vuelve a entrar.', 'ok')
      setCurrent(''); setNext('')
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  return (
    <div className="space-y-5">
      <div className="card p-4 space-y-3">
        <Field label="Nombre">
          <input value={name} onChange={(e) => setName(e.target.value)} className="field" />
        </Field>
        <Field label="Correo">
          <input value={user?.email || ''} disabled className="field opacity-60" />
        </Field>
        <button onClick={saveName} disabled={busy} className="btn-primary btn-sm">
          {busy && <Spinner />}Guardar
        </button>
      </div>

      <div className="card p-4 space-y-3">
        <p className="font-bold text-sm">Cambiar contraseña</p>
        <Field label="Contraseña actual">
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)}
                 className="field" />
        </Field>
        <Field label="Contraseña nueva" hint="Mínimo 8 caracteres. Se cerrarán todas tus sesiones.">
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)}
                 className="field" />
        </Field>
        <button onClick={savePassword} disabled={busy || next.length < 8}
                className="btn-ghost btn-sm">Cambiar</button>
      </div>

      {caps && (
        <div className="card p-4">
          <p className="font-bold text-sm mb-3">Esta instancia</p>
          <dl className="text-xs grid grid-cols-2 gap-y-2 text-zinc-500">
            <dt>Vídeo</dt><dd className="text-zinc-300">{caps.video.provider}</dd>
            <dt>Imagen</dt><dd className="text-zinc-300">{caps.image.provider}</dd>
            <dt>Audio</dt><dd className="text-zinc-300">{caps.audio.provider}</dd>
            <dt>Mejora de prompts</dt>
            <dd className="text-zinc-300">{caps.prompt_enhance ? 'Claude' : 'heurística local'}</dd>
            <dt>Clonar voces</dt>
            <dd className="text-zinc-300">{caps.voice_cloning ? 'sí' : 'no (falta ElevenLabs)'}</dd>
            <dt>Subida máxima</dt><dd className="text-zinc-300">{caps.max_upload_mb} MB</dd>
            <dt>Versión</dt><dd className="text-zinc-300">{caps.version}</dd>
          </dl>
          {caps.demo_mode && (
            <p className="text-[11px] text-zinc-500 mt-3 leading-relaxed">
              Estás en modo demostración: el material se sintetiza en local con ffmpeg.
              Añade <code className="text-brand">FAL_API_KEY</code> o{' '}
              <code className="text-brand">REPLICATE_API_TOKEN</code> en el fichero{' '}
              <code>.env</code> y reinicia para usar modelos reales.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function ApiKeys() {
  const { data, loading, reload } = useAsync(() => api.apiKeys(), [])
  const [secret, setSecret] = useState<string | null>(null)

  const create = async () => {
    const name = prompt('Nombre de la clave') || 'Sin nombre'
    const result = await api.createApiKey(name)
    setSecret(result.secret)
    reload()
  }

  return (
    <div className="space-y-4">
      <div className="card p-4">
        <p className="text-sm text-zinc-400 leading-relaxed">
          Usa las claves para llamar a la API desde tus scripts:{' '}
          <code className="text-brand">Authorization: Bearer hs_…</code>.
          Tienen los mismos permisos que tu cuenta y gastan tus créditos.
        </p>
      </div>

      <button onClick={create} className="btn-primary btn-sm">
        <IconPlus className="w-4 h-4" />Nueva clave
      </button>

      {loading ? <Spinner /> : (data?.keys.length ?? 0) === 0 ? (
        <EmptyState title="Sin claves" hint="Crea una para automatizar generaciones." />
      ) : (
        <div className="card divide-y divide-white/[0.06]">
          {data!.keys.map((key: any) => (
            <div key={key.id} className="flex items-center justify-between px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">{key.name}</p>
                <p className="text-[11px] text-zinc-500 font-mono">
                  {key.prefix}… · {key.last_used_at ? `usada ${relative(key.last_used_at)}` : 'sin usar'}
                </p>
              </div>
              {key.revoked ? <Badge tone="flame">revocada</Badge> : (
                <button onClick={() => api.revokeApiKey(key.id).then(reload)}
                        className="btn-ghost btn-xs"><IconTrash className="w-3.5 h-3.5" /></button>
              )}
            </div>
          ))}
        </div>
      )}

      <Modal open={!!secret} onClose={() => setSecret(null)} title="Guarda esta clave">
        <p className="text-sm text-zinc-400 mb-3">
          No se vuelve a mostrar. Cópiala ahora.
        </p>
        <code className="block card p-3 text-xs font-mono break-all">{secret}</code>
        <button onClick={() => { copy(secret || ''); setSecret(null) }}
                className="btn-primary btn-sm w-full mt-3">Copiar y cerrar</button>
      </Modal>
    </div>
  )
}

function Webhooks() {
  const toast = useToast()
  const { data, loading, reload } = useAsync(() => api.webhooks(), [])
  const [url, setUrl] = useState('')

  const create = async () => {
    if (!url.trim()) return
    try {
      await api.createWebhook({ url })
      setUrl('')
      reload()
      toast('Webhook creado', 'ok')
    } catch (e: any) { toast(e.message, 'error') }
  }

  return (
    <div className="space-y-4">
      <div className="card p-4">
        <p className="text-sm text-zinc-400 leading-relaxed">
          Te avisamos cuando un trabajo termina o falla. Firmamos cada envío con
          HMAC-SHA256 en la cabecera <code className="text-brand">X-HiggsStudio-Signature</code>.
        </p>
      </div>

      <div className="flex gap-2">
        <input value={url} onChange={(e) => setUrl(e.target.value)} className="field"
               placeholder="https://tu-servidor.com/hooks/higgs" />
        <button onClick={create} className="btn-primary btn-sm whitespace-nowrap">Añadir</button>
      </div>

      {loading ? <Spinner /> : (data?.webhooks.length ?? 0) === 0 ? (
        <EmptyState title="Sin webhooks" />
      ) : (
        <div className="space-y-2">
          {data!.webhooks.map((hook: any) => (
            <div key={hook.id} className="card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-mono truncate">{hook.url}</p>
                  <p className="text-[11px] text-zinc-500 mt-1">
                    {hook.events.join(', ')} · secreto {hook.secret}
                  </p>
                </div>
                <button onClick={() => api.deleteWebhook(hook.id).then(reload)}
                        className="btn-ghost btn-xs"><IconTrash className="w-3.5 h-3.5" /></button>
              </div>
              {hook.recent?.length > 0 && (
                <div className="flex gap-1.5 mt-2 flex-wrap">
                  {hook.recent.map((d: any, i: number) => (
                    <Badge key={i} tone={d.status === 'sent' ? 'brand' : 'flame'}>
                      {d.event} {d.status_code || d.status}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Usage() {
  const { data, loading } = useAsync(() => api.usage(), [])
  if (loading) return <Spinner />
  const max = Math.max(1, ...(data?.daily || []).map((d: any) => d.credits))
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <p className="label">Créditos por día</p>
        <div className="flex items-end gap-1 h-28 mt-3">
          {[...(data?.daily || [])].reverse().map((day: any) => (
            <div key={day.day} className="flex-1 group relative">
              <div className="bg-brand/70 group-hover:bg-brand rounded-t transition-colors"
                   style={{ height: `${(day.credits / max) * 100}%`, minHeight: 2 }} />
              <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-1.5 py-0.5
                               rounded bg-ink-700 text-[10px] whitespace-nowrap opacity-0
                               group-hover:opacity-100 pointer-events-none">
                {day.day}: {day.credits}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="card divide-y divide-white/[0.06]">
        {(data?.recent_jobs || []).map((job: any) => (
          <div key={job.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
            <span className="text-zinc-300 truncate">{job.model}</span>
            <span className="text-[11px] text-zinc-500">
              {job.cost_credits} cr. · {relative(job.created_at)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
