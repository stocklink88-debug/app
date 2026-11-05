import { useState } from 'react'
import { api, type Asset, type Job } from '../lib/api'
import { STATUS_COLOR, STATUS_LABEL, TYPE_LABEL, relative } from '../lib/format'
import { useSession } from '../lib/session'
import { AssetViewer } from '../components/media'
import { Badge, EmptyState, Segmented, Spinner, useAsync, useToast } from '../components/ui'
import { IconBolt, IconRefresh, IconTrash } from '../components/Icons'

export default function Jobs() {
  const toast = useToast()
  const { jobs: live } = useSession()
  const [status, setStatus] = useState('')
  const [viewing, setViewing] = useState<Asset | null>(null)
  const { data, loading, reload } = useAsync(
    () => api.jobs({ status: status || undefined, limit: 80 }), [status, live.length])

  // Mezclamos los trabajos en vivo con los que vienen del servidor.
  const merged: Job[] = (() => {
    const map = new Map<string, Job>()
    for (const job of data?.jobs || []) map.set(job.id, job)
    for (const job of live) if (!status || job.status === status) map.set(job.id, job)
    return [...map.values()].sort((a, b) => b.created_at.localeCompare(a.created_at))
  })()

  const cancel = async (job: Job) => {
    try { await api.cancelJob(job.id); toast('Cancelado', 'ok'); reload() }
    catch (e: any) { toast(e.message, 'error') }
  }

  const retry = async (job: Job) => {
    try { await api.retryJob(job.id); toast('Reintentando', 'ok'); reload() }
    catch (e: any) { toast(e.message, 'error') }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="mr-auto">
          <h1 className="text-2xl font-black tracking-tight">Trabajos</h1>
          <p className="text-sm text-zinc-500">Todo lo que has mandado generar.</p>
        </div>
        <Segmented value={status} onChange={setStatus} size="sm"
                   options={[{ value: '', label: 'Todos' },
                             { value: 'queued,running', label: 'En curso' },
                             { value: 'succeeded', label: 'Listos' },
                             { value: 'failed', label: 'Fallidos' }]} />
      </div>

      {loading && merged.length === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-20 rounded-2xl" />)}
        </div>
      ) : merged.length === 0 ? (
        <EmptyState icon={<IconBolt className="w-12 h-12" />} title="Nada por aquí todavía" />
      ) : (
        <div className="space-y-2">
          {merged.map((job) => {
            const assets = job.result?.assets || []
            const running = job.status === 'queued' || job.status === 'running'
            return (
              <div key={job.id} className="card p-3.5">
                <div className="flex items-center gap-3">
                  {assets[0]?.thumb_url ? (
                    <img src={assets[0].thumb_url} alt=""
                         onClick={() => setViewing(assets[0])}
                         className="w-16 h-16 rounded-lg object-cover bg-ink-900 cursor-pointer flex-shrink-0" />
                  ) : (
                    <div className="w-16 h-16 rounded-lg bg-ink-900 grid place-items-center flex-shrink-0">
                      {running ? <Spinner className="w-4 h-4 text-brand" />
                               : <IconBolt className="w-5 h-5 text-zinc-700" />}
                    </div>
                  )}

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`pill ${STATUS_COLOR[job.status]}`}>
                        {STATUS_LABEL[job.status]}
                      </span>
                      <Badge>{TYPE_LABEL[job.type] || job.type}</Badge>
                      <Badge>{job.model}</Badge>
                      {job.cost_credits > 0 && (
                        <Badge tone={job.refunded ? 'aqua' : 'default'}>
                          {job.refunded ? `${job.cost_credits} devueltos` : `${job.cost_credits} cr.`}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-zinc-400 mt-1.5 line-clamp-1">
                      {job.params?.prompt || job.message}
                    </p>
                    {running && (
                      <div className="h-1 rounded-full bg-ink-600 overflow-hidden mt-2 max-w-xs">
                        <div className="h-full bg-brand transition-all"
                             style={{ width: `${Math.max(job.progress * 100, 5)}%` }} />
                      </div>
                    )}
                    {job.error && (
                      <p className="text-[11px] text-flame mt-1.5 line-clamp-2">{job.error}</p>
                    )}
                  </div>

                  <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                    <span className="text-[11px] text-zinc-600">{relative(job.created_at)}</span>
                    <div className="flex gap-1">
                      {running && (
                        <button onClick={() => cancel(job)} className="btn-ghost btn-xs">
                          <IconTrash className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {job.status === 'failed' && (
                        <button onClick={() => retry(job)} className="btn-ghost btn-xs">
                          <IconRefresh className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {assets.length > 1 && (
                  <div className="flex gap-1.5 mt-3 overflow-x-auto scroll-x">
                    {assets.slice(1).map((asset: Asset) => (
                      <img key={asset.id} src={asset.thumb_url || ''} alt=""
                           onClick={() => setViewing(asset)}
                           className="w-12 h-12 rounded object-cover bg-ink-900 cursor-pointer flex-shrink-0" />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <AssetViewer asset={viewing} onClose={() => setViewing(null)} />
    </div>
  )
}
