import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Post } from '../lib/api'
import { relative, seconds } from '../lib/format'
import { useSession } from '../lib/session'
import { IconCompass, IconHeart, IconPlay, IconWand } from '../components/Icons'
import {
  Badge, EmptyState, Modal, SearchInput, Segmented, useAsync,
  useDebounced, useToast,
} from '../components/ui'

const QUICK = [
  { label: 'Texto a vídeo', family: 'video', mode: 't2v' },
  { label: 'Imagen a vídeo', family: 'video', mode: 'i2v' },
  { label: 'Efectos virales', family: 'video', mode: 't2v', preset: 'squish' },
  { label: 'Foto que habla', family: 'speak', mode: 'speak' },
  { label: 'Retrato Soul', family: 'image', mode: 't2i', style: 'soul-realism' },
  { label: 'Música', family: 'audio', mode: 'music' },
]

export default function Explore() {
  const navigate = useNavigate()
  const { user, caps } = useSession()
  const toast = useToast()
  const [sort, setSort] = useState<'reciente' | 'populares' | 'destacados'>('reciente')
  const [kind, setKind] = useState('')
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search, 300)
  const [open, setOpen] = useState<Post | null>(null)
  const { data, loading, reload } = useAsync(
    () => api.feed({ sort, kind, search: debounced, limit: 60 }), [sort, kind, debounced])

  const like = async (post: Post) => {
    try {
      const result = await api.likePost(post.id)
      reload()
      if (open?.id === post.id) setOpen({ ...open, ...result })
    } catch (e: any) { toast(e.message, 'error') }
  }

  const remix = async (post: Post) => {
    try {
      const preset = await api.remix(post.id)
      navigate('/crear', { state: { family: post.media.kind === 'image' ? 'image' : 'video', ...preset } })
    } catch (e: any) { toast(e.message, 'error') }
  }

  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <section className="card p-6 sm:p-8 mb-6 relative overflow-hidden">
        <div className="absolute -right-24 -top-24 w-80 h-80 rounded-full bg-brand/10 blur-3xl" />
        <div className="relative">
          <p className="text-xs font-bold tracking-[0.2em] text-brand uppercase mb-2">
            Hola{user?.name ? `, ${user.name.split(' ')[0]}` : ''}
          </p>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight max-w-2xl leading-[1.1]">
            Escribe una idea. Sal con un plano de cine.
          </h1>
          <p className="text-sm text-zinc-400 mt-3 max-w-xl">
            {caps?.demo_mode
              ? 'Esta instancia genera en local con ffmpeg para que puedas probarlo todo gratis. Con una clave de proveedor pasa a modelos reales sin tocar nada más.'
              : 'Elige un modelo, un movimiento de cámara y deja que trabaje.'}
          </p>
          <div className="flex flex-wrap gap-2 mt-5">
            {QUICK.map((q) => (
              <button key={q.label} onClick={() => navigate('/crear', { state: q })}
                      className="btn-ghost btn-sm">{q.label}</button>
            ))}
          </div>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <h2 className="text-lg font-black tracking-tight mr-auto">Galería de la comunidad</h2>
        <div className="w-56"><SearchInput value={search} onChange={setSearch} placeholder="Buscar…" /></div>
        <Segmented value={sort} onChange={setSort} size="sm"
                   options={[{ value: 'reciente', label: 'Reciente' },
                             { value: 'populares', label: 'Popular' },
                             { value: 'destacados', label: 'Destacados' }]} />
        <Segmented value={kind} onChange={setKind} size="sm"
                   options={[{ value: '', label: 'Todo' },
                             { value: 'video', label: 'Vídeo' },
                             { value: 'image', label: 'Imagen' }]} />
      </div>

      {loading ? (
        <div className="columns-2 md:columns-3 xl:columns-4 gap-3 space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="skeleton rounded-2xl" style={{ height: 180 + (i % 3) * 70 }} />
          ))}
        </div>
      ) : (data?.posts.length ?? 0) === 0 ? (
        <EmptyState icon={<IconCompass className="w-12 h-12" />}
                    title="Todavía no hay nada publicado"
                    hint="Genera algo y publícalo desde la biblioteca para estrenar la galería."
                    action={<button onClick={() => navigate('/crear')} className="btn-primary btn-sm">
                      Crear lo primero</button>} />
      ) : (
        <div className="columns-2 md:columns-3 xl:columns-4 gap-3 space-y-3">
          {data!.posts.map((post) => (
            <PostCard key={post.id} post={post} onOpen={() => setOpen(post)} onLike={() => like(post)} />
          ))}
        </div>
      )}

      <Modal open={!!open} onClose={() => setOpen(null)} wide title={open?.title || 'Publicación'}>
        {open && (
          <div className="grid lg:grid-cols-[minmax(0,1fr),280px] gap-5">
            <div className="rounded-xl overflow-hidden bg-black max-h-[70vh] flex items-center">
              {open.media.kind === 'video'
                ? <video src={open.media.url} controls autoPlay loop className="w-full max-h-[70vh]" />
                : <img src={open.media.url} alt="" className="w-full max-h-[70vh] object-contain" />}
            </div>
            <div className="space-y-4">
              <div className="flex items-center gap-2.5">
                <span className="w-9 h-9 rounded-full bg-gradient-to-br from-iris to-aqua
                                 grid place-items-center text-ink-950 font-black text-sm">
                  {(open.author.name || '?').slice(0, 1).toUpperCase()}
                </span>
                <div>
                  <p className="text-sm font-semibold">{open.author.name}</p>
                  <p className="text-[11px] text-zinc-500">{relative(open.created_at)}</p>
                </div>
              </div>
              <div>
                <p className="label">Prompt</p>
                <p className="text-sm text-zinc-300 leading-relaxed">{open.prompt || '—'}</p>
              </div>
              <div className="flex gap-1.5 flex-wrap">
                {open.model && <Badge>{open.model}</Badge>}
                {open.preset && <Badge tone="iris">{open.preset}</Badge>}
                <Badge tone="brand">{open.likes} me gusta</Badge>
              </div>
              <div className="grid gap-2">
                <button onClick={() => remix(open)} className="btn-primary btn-sm">
                  <IconWand className="w-4 h-4" />Remezclar
                </button>
                <button onClick={() => like(open)} className="btn-ghost btn-sm">
                  <IconHeart className={`w-4 h-4 ${open.liked ? 'fill-current text-flame' : ''}`} />
                  {open.liked ? 'Quitar me gusta' : 'Me gusta'}
                </button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

function PostCard({ post, onOpen, onLike }: {
  post: Post; onOpen: () => void; onLike: () => void
}) {
  const [hover, setHover] = useState(false)
  const ratio = post.media.width && post.media.height
    ? `${post.media.width} / ${post.media.height}` : '16 / 9'
  return (
    <div className="break-inside-avoid card card-hover overflow-hidden cursor-pointer group"
         onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
         onClick={onOpen}>
      <div className="relative bg-ink-900" style={{ aspectRatio: ratio }}>
        {post.media.kind === 'video' && hover ? (
          <video src={post.media.url} autoPlay loop muted playsInline className="w-full h-full object-cover" />
        ) : post.media.thumb_url ? (
          <img src={post.media.thumb_url} alt="" loading="lazy" className="w-full h-full object-cover" />
        ) : <div className="w-full h-full skeleton" />}

        {post.media.kind === 'video' && !hover && (
          <span className="absolute inset-0 grid place-items-center pointer-events-none">
            <span className="w-10 h-10 rounded-full bg-black/55 backdrop-blur grid place-items-center">
              <IconPlay className="w-4 h-4 translate-x-[1px]" />
            </span>
          </span>
        )}
        {post.media.duration ? (
          <span className="absolute bottom-2 right-2 text-[10px] font-semibold px-1.5 py-0.5
                           rounded bg-black/65 tabular-nums">{seconds(post.media.duration)}</span>
        ) : null}
        <button onClick={(e) => { e.stopPropagation(); onLike() }}
                className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 rounded-lg
                           bg-black/55 backdrop-blur text-[11px] font-semibold opacity-0
                           group-hover:opacity-100 transition-opacity">
          <IconHeart className={`w-3.5 h-3.5 ${post.liked ? 'fill-current text-flame' : ''}`} />
          {post.likes}
        </button>
      </div>
      <div className="p-2.5">
        <p className="text-[11px] text-zinc-400 line-clamp-2 leading-snug">
          {post.title || post.prompt}
        </p>
        <p className="text-[10px] text-zinc-600 mt-1">{post.author.name} · {post.model}</p>
      </div>
    </div>
  )
}
