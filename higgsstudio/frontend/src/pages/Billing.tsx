import { api } from '../lib/api'
import { bytes, relative } from '../lib/format'
import { useSession } from '../lib/session'
import { Badge, EmptyState, Spinner, useAsync, useToast } from '../components/ui'
import { IconCheck, IconCoins } from '../components/Icons'

export default function Billing() {
  const toast = useToast()
  const { refreshUser, user } = useSession()
  const { data, loading, reload } = useAsync(() => api.billing(), [])
  const transactions = useAsync(() => api.transactions(), [])

  const changePlan = async (planId: string) => {
    try {
      const result = await api.changePlan(planId)
      toast(`Plan ${result.plan.name}: +${result.granted} créditos`, 'ok')
      refreshUser(); reload(); transactions.reload()
    } catch (e: any) { toast(e.message, 'error') }
  }

  const buyPack = async (packId: string) => {
    try {
      const result = await api.buyPack(packId)
      toast(`+${result.pack.credits} créditos`, 'ok')
      refreshUser(); reload(); transactions.reload()
    } catch (e: any) { toast(e.message, 'error') }
  }

  if (loading) return <div className="grid place-items-center py-24"><Spinner className="w-6 h-6" /></div>

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-7">
      <div>
        <h1 className="text-2xl font-black tracking-tight">Créditos y plan</h1>
        <p className="text-sm text-zinc-500">
          Cada generación cuesta créditos. Si algo falla, se devuelven solos.
        </p>
      </div>

      <div className="grid sm:grid-cols-4 gap-3">
        <Stat label="Saldo" value={data.balance} accent />
        <Stat label="Gastado en total" value={data.spent_total} />
        <Stat label="Generaciones" value={data.jobs_total} />
        <Stat label="Almacenamiento" value={bytes(data.storage.bytes)} />
      </div>

      <div className="card p-4 border-l-2 border-l-iris">
        <p className="text-sm text-zinc-300">
          Esta instancia <b>no cobra nada</b>: no hay pasarela de pago conectada.
          Cambiar de plan o «comprar» un paquete ajusta tus límites y te da los
          créditos al momento. Si la publicas de verdad, conecta antes un cobro real.
        </p>
      </div>

      <section>
        <h2 className="font-bold mb-3">Planes</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {data.plans.map((plan: any) => {
            const current = plan.id === user?.plan
            return (
              <div key={plan.id}
                   className={`card p-4 flex flex-col ${current ? 'ring-1 ring-brand' : ''}`}>
                <div className="flex items-center justify-between">
                  <p className="font-bold">{plan.name}</p>
                  {plan.badge && <Badge tone="brand">{plan.badge}</Badge>}
                </div>
                <p className="text-2xl font-black mt-1 tabular-nums">
                  {plan.price_eur ? `${plan.price_eur} €` : 'Gratis'}
                  {plan.price_eur ? <span className="text-xs text-zinc-500 font-normal">/mes</span> : null}
                </p>
                <p className="text-xs text-brand font-semibold mt-1">
                  {plan.monthly_credits.toLocaleString('es-ES')} créditos al mes
                </p>
                <ul className="space-y-1.5 mt-3 flex-1">
                  {plan.features.map((feature: string) => (
                    <li key={feature} className="flex gap-2 text-[11px] text-zinc-400">
                      <IconCheck className="w-3.5 h-3.5 text-brand flex-shrink-0 mt-0.5" />
                      {feature}
                    </li>
                  ))}
                </ul>
                <button onClick={() => changePlan(plan.id)} disabled={current}
                        className={`${current ? 'btn-ghost' : 'btn-primary'} btn-sm w-full mt-4`}>
                  {current ? 'Tu plan actual' : 'Cambiar a este'}
                </button>
              </div>
            )
          })}
        </div>
      </section>

      <section>
        <h2 className="font-bold mb-3">Paquetes de créditos</h2>
        <div className="grid sm:grid-cols-4 gap-3">
          {data.packs.map((pack: any) => (
            <button key={pack.id} onClick={() => buyPack(pack.id)}
                    className="card card-hover p-4 text-left">
              <div className="flex items-center justify-between">
                <IconCoins className="w-5 h-5 text-brand" />
                {pack.badge && <Badge tone="brand">{pack.badge}</Badge>}
              </div>
              <p className="text-xl font-black mt-2 tabular-nums">
                {pack.credits.toLocaleString('es-ES')}
              </p>
              <p className="text-xs text-zinc-500">{pack.price_eur} €</p>
            </button>
          ))}
        </div>
      </section>

      {data.by_type?.length > 0 && (
        <section>
          <h2 className="font-bold mb-3">En qué se te van</h2>
          <div className="card divide-y divide-white/[0.06]">
            {data.by_type.map((row: any) => (
              <div key={row.type} className="flex items-center justify-between px-4 py-2.5 text-sm">
                <span className="text-zinc-300 capitalize">{row.type.replace(/_/g, ' ')}</span>
                <span className="text-zinc-500">
                  {row.jobs} generaciones · <b className="text-zinc-300">{row.credits} cr.</b>
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="font-bold mb-3">Movimientos</h2>
        {(transactions.data?.transactions.length ?? 0) === 0 ? (
          <EmptyState title="Sin movimientos todavía" />
        ) : (
          <div className="card divide-y divide-white/[0.06] max-h-96 overflow-y-auto">
            {transactions.data!.transactions.map((tx: any) => (
              <div key={tx.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="text-zinc-300 truncate">{tx.reason || tx.kind}</p>
                  <p className="text-[11px] text-zinc-600">{relative(tx.created_at)}</p>
                </div>
                <span className={`font-bold tabular-nums ${tx.amount > 0 ? 'text-brand' : 'text-zinc-400'}`}>
                  {tx.amount > 0 ? '+' : ''}{tx.amount}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: React.ReactNode; accent?: boolean }) {
  return (
    <div className="card p-4">
      <p className="label !mb-1">{label}</p>
      <p className={`text-2xl font-black tabular-nums ${accent ? 'text-brand' : ''}`}>{value}</p>
    </div>
  )
}
