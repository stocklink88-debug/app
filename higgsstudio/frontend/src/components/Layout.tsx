import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useSession } from '../lib/session'
import { STATUS_COLOR, STATUS_LABEL, TYPE_LABEL, relative } from '../lib/format'
import {
  IconBolt, IconCoins, IconCog, IconCompass, IconFilm, IconGrid, IconLayers,
  IconMegaphone, IconMenu, IconClose, IconSpark, IconTool, IconUser, IconWand,
} from './Icons'
import { Spinner } from './ui'

const NAV = [
  { to: '/', label: 'Explorar', icon: IconCompass, end: true },
  { to: '/crear', label: 'Crear', icon: IconSpark },
  { to: '/efectos', label: 'Efectos', icon: IconWand },
  { to: '/herramientas', label: 'Herramientas', icon: IconTool },
  { to: '/biblioteca', label: 'Biblioteca', icon: IconGrid },
  { to: '/proyectos', label: 'Proyectos', icon: IconLayers },
  { to: '/personajes', label: 'Personajes', icon: IconUser },
  { to: '/anuncios', label: 'Anuncios', icon: IconMegaphone },
  { to: '/voces', label: 'Voces', icon: IconFilm },
]

const BOTTOM = [
  { to: '/trabajos', label: 'Trabajos', icon: IconBolt },
  { to: '/creditos', label: 'Créditos', icon: IconCoins },
  { to: '/ajustes', label: 'Ajustes', icon: IconCog },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, caps, jobs, logout } = useSession()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'running')

  const nav = (
    <nav className="flex flex-col gap-1 flex-1 overflow-y-auto">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
                 className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}>
          <Icon className="w-[18px] h-[18px]" />{label}
        </NavLink>
      ))}
      <div className="h-px bg-white/[0.07] my-3" />
      {BOTTOM.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} onClick={() => setOpen(false)}
                 className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}>
          <Icon className="w-[18px] h-[18px]" />
          <span className="flex-1">{label}</span>
          {to === '/trabajos' && active.length > 0 && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-aqua/20 text-aqua">
              {active.length}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  )

  return (
    <div className="min-h-screen flex">
      {/* barra lateral en escritorio */}
      <aside className="hidden lg:flex w-[232px] flex-col gap-4 p-4 border-r border-white/[0.06]
                        bg-ink-900/60 backdrop-blur sticky top-0 h-screen">
        <Brand />
        {nav}
        <Footer caps={caps} />
      </aside>

      {/* cajón en móvil */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-black/70" onClick={() => setOpen(false)} />
          <aside className="relative w-[260px] flex flex-col gap-4 p-4 bg-ink-900 border-r border-white/[0.07]">
            <div className="flex items-center justify-between">
              <Brand />
              <button onClick={() => setOpen(false)} className="btn-ghost btn-sm !p-2">
                <IconClose className="w-4 h-4" />
              </button>
            </div>
            {nav}
            <Footer caps={caps} />
          </aside>
        </div>
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 px-4 sm:px-6 h-14
                           border-b border-white/[0.06] bg-ink-950/85 backdrop-blur">
          <button onClick={() => setOpen(true)} className="lg:hidden btn-ghost btn-sm !p-2">
            <IconMenu className="w-5 h-5" />
          </button>
          <div className="lg:hidden"><Brand small /></div>

          <div className="flex-1" />

          {active.length > 0 && (
            <NavLink to="/trabajos"
                     className="hidden sm:flex items-center gap-2 pill bg-aqua/12 text-aqua">
              <Spinner className="w-3.5 h-3.5" />
              {active.length === 1
                ? `${TYPE_LABEL[active[0].type] || active[0].type} · ${Math.round(active[0].progress * 100)}%`
                : `${active.length} generando`}
            </NavLink>
          )}

          <NavLink to="/creditos" className="pill bg-white/[0.07] hover:bg-white/[0.12] text-zinc-200">
            <IconCoins className="w-4 h-4 text-brand" />
            <span className="tabular-nums font-bold">{user?.credits ?? 0}</span>
          </NavLink>

          <div className="relative group">
            <button className="w-9 h-9 rounded-full bg-gradient-to-br from-brand to-aqua
                               text-ink-950 font-black text-sm grid place-items-center">
              {(user?.name || user?.email || '?').slice(0, 1).toUpperCase()}
            </button>
            <div className="absolute right-0 top-full mt-2 w-52 card p-1.5 opacity-0 invisible
                            group-hover:opacity-100 group-hover:visible transition-all z-50">
              <div className="px-3 py-2 border-b border-white/[0.07] mb-1">
                <p className="text-sm font-semibold truncate">{user?.name}</p>
                <p className="text-[11px] text-zinc-500 truncate">{user?.email}</p>
              </div>
              <NavLink to="/ajustes" className="nav-item !py-2 text-sm">Ajustes</NavLink>
              <NavLink to="/creditos" className="nav-item !py-2 text-sm">Plan y créditos</NavLink>
              <button onClick={logout} className="nav-item !py-2 text-sm w-full text-left text-flame">
                Cerrar sesión
              </button>
            </div>
          </div>
        </header>

        <main key={location.pathname} className="flex-1 min-w-0 animate-rise">{children}</main>
      </div>
    </div>
  )
}

function Brand({ small }: { small?: boolean }) {
  return (
    <NavLink to="/" className="flex items-center gap-2.5 px-1">
      <span className="w-8 h-8 rounded-xl bg-brand grid place-items-center text-ink-950 font-black">H</span>
      {!small && (
        <span className="font-black tracking-tight text-[15px]">
          Higgs<span className="text-brand">Studio</span>
        </span>
      )}
    </NavLink>
  )
}

function Footer({ caps }: { caps: ReturnType<typeof useSession>['caps'] }) {
  if (!caps) return null
  return (
    <div className="text-[10px] text-zinc-600 px-2 leading-relaxed">
      {caps.demo_mode ? (
        <>
          <span className="text-brand font-semibold">Modo demostración.</span>{' '}
          Se genera en local con ffmpeg. Añade una clave de proveedor en
          <code className="mx-1 text-zinc-500">.env</code> para usar modelos reales.
        </>
      ) : (
        <>Vídeo: {caps.video.provider} · Imagen: {caps.image.provider} · Audio: {caps.audio.provider}</>
      )}
    </div>
  )
}

export function JobChip({ job }: { job: { status: string; type: string; progress: number; created_at: string } }) {
  return (
    <span className={`pill ${STATUS_COLOR[job.status]}`}>
      {job.status === 'running' ? `${Math.round(job.progress * 100)}%` : STATUS_LABEL[job.status]}
      <span className="opacity-60">· {relative(job.created_at)}</span>
    </span>
  )
}
