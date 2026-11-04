import type { Clip } from '../lib/api'
import { formatTimestamp } from '../lib/api'
import { IconPlay, IconWarning } from './Icons'
import ScoreRing from './ScoreRing'

interface Props {
  clip: Clip
  index: number
  onOpen: () => void
}

export default function ClipCard({ clip, index, onOpen }: Props) {
  const busy = clip.status === 'rendering' || clip.status === 'pending'
  const failed = clip.status === 'failed'

  return (
    <button
      onClick={onOpen}
      disabled={failed}
      style={{ animationDelay: `${index * 45}ms` }}
      className="card rise overflow-hidden text-left group hover:border-white/20 transition-all
                 hover:-translate-y-0.5 disabled:cursor-not-allowed"
    >
      <div className="relative aspect-[9/16] bg-ink-900 overflow-hidden">
        {clip.thumb_url ? (
          <img
            src={clip.thumb_url} alt={clip.title} loading="lazy"
            className="w-full h-full object-cover group-hover:scale-[1.03] transition-transform duration-300"
          />
        ) : (
          <div className="absolute inset-0 grid place-items-center">
            {failed ? (
              <IconWarning className="w-7 h-7 text-coral" />
            ) : (
              <div className="flex flex-col items-center gap-2 text-slate-500">
                <div className="w-6 h-6 rounded-full border-2 border-accent/30 border-t-accent animate-spin" />
                <span className="text-[11px]">{busy ? 'Montando…' : 'En cola'}</span>
              </div>
            )}
          </div>
        )}

        {clip.thumb_url && (
          <>
            <div className="absolute inset-0 bg-gradient-to-t from-ink-900 via-ink-900/10 to-transparent" />
            <div className="absolute inset-0 grid place-items-center opacity-0 group-hover:opacity-100 transition-opacity">
              <span className="w-12 h-12 rounded-full bg-accent/90 grid place-items-center">
                <IconPlay className="w-5 h-5 text-ink-900 ml-0.5" />
              </span>
            </div>
          </>
        )}

        <div className="absolute top-2.5 left-2.5">
          <ScoreRing score={clip.score} size={44} />
        </div>
        <div className="absolute top-2.5 right-2.5 chip bg-ink-900/80">
          {clip.duration.toFixed(0)}s
        </div>
        <div className="absolute bottom-2.5 left-2.5 right-2.5">
          <p className="text-[13px] font-semibold leading-snug line-clamp-2">{clip.title}</p>
          <p className="text-[10px] text-slate-400 mt-1 font-mono">
            {formatTimestamp(clip.start)} – {formatTimestamp(clip.end)}
          </p>
        </div>
      </div>

      {failed && (
        <p className="px-3 py-2 text-[11px] text-coral line-clamp-2">{clip.error}</p>
      )}
    </button>
  )
}
