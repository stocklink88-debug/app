import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { IconCheck, IconChevron, IconClose, IconSearch } from './Icons'

/* --------------------------------- avisos --------------------------------- */

type Toast = { id: number; text: string; tone: 'ok' | 'error' | 'info' }
const ToastCtx = createContext<(text: string, tone?: Toast['tone']) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastHost({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((text: string, tone: Toast['tone'] = 'info') => {
    const id = Date.now() + Math.random()
    setItems((prev) => [...prev, { id, text, tone }])
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 5200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 max-w-[min(26rem,calc(100vw-2.5rem))]">
        {items.map((t) => (
          <div key={t.id}
               className={`card px-4 py-3 text-sm shadow-2xl animate-rise border-l-2 ${
                 t.tone === 'ok' ? 'border-l-brand' : t.tone === 'error' ? 'border-l-flame' : 'border-l-iris'
               }`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

/* --------------------------------- básicos --------------------------------- */

export function Spinner({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin`} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity=".2" />
      <path d="M21 12a9 9 0 00-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

export function Badge({ children, tone = 'default' }: { children: React.ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    default: 'bg-white/[0.08] text-zinc-300',
    brand: 'bg-brand/15 text-brand',
    iris: 'bg-iris/20 text-iris',
    flame: 'bg-flame/15 text-flame',
    aqua: 'bg-aqua/15 text-aqua',
  }
  return <span className={`pill text-[10px] uppercase tracking-wide ${tones[tone] || tones.default}`}>{children}</span>
}

export function EmptyState({ icon, title, hint, action }: {
  icon?: React.ReactNode; title: string; hint?: string; action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6">
      {icon && <div className="mb-4 text-zinc-600">{icon}</div>}
      <p className="text-zinc-300 font-semibold">{title}</p>
      {hint && <p className="text-sm text-zinc-500 mt-1.5 max-w-md">{hint}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/* ---------------------------------- modal ---------------------------------- */

export function Modal({ open, onClose, title, children, wide, footer }: {
  open: boolean; onClose: () => void; title?: React.ReactNode
  children: React.ReactNode; wide?: boolean; footer?: React.ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-6"
         onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" />
      <div className={`relative w-full ${wide ? 'max-w-5xl' : 'max-w-xl'} max-h-[92vh]
                       flex flex-col animate-rise bg-ink-800 border border-white/[0.09]
                       rounded-2xl rounded-b-none sm:rounded-2xl shadow-2xl`}>
        {title && (
          <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-white/[0.07]">
            <h3 className="font-bold text-lg">{title}</h3>
            <button onClick={onClose} className="btn-ghost btn-sm !p-2" aria-label="Cerrar">
              <IconClose className="w-4 h-4" />
            </button>
          </div>
        )}
        <div className="overflow-y-auto px-5 py-4 flex-1">{children}</div>
        {footer && <div className="px-5 py-4 border-t border-white/[0.07]">{footer}</div>}
      </div>
    </div>
  )
}

/* -------------------------------- formulario -------------------------------- */

export function Field({ label, hint, children, right }: {
  label?: string; hint?: string; children: React.ReactNode; right?: React.ReactNode
}) {
  return (
    <div>
      {(label || right) && (
        <div className="flex items-center justify-between">
          {label && <label className="label">{label}</label>}
          {right}
        </div>
      )}
      {children}
      {hint && <p className="text-[11px] text-zinc-500 mt-1.5">{hint}</p>}
    </div>
  )
}

export function Select<T extends string>({ value, onChange, options, className = '' }: {
  value: T; onChange: (v: T) => void
  options: { value: T; label: string; disabled?: boolean }[]; className?: string
}) {
  return (
    <div className={`relative ${className}`}>
      <select value={value} onChange={(e) => onChange(e.target.value as T)}
              className="field appearance-none pr-9 cursor-pointer">
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
        ))}
      </select>
      <IconChevron className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 rotate-90 text-zinc-500 pointer-events-none" />
    </div>
  )
}

export function Segmented<T extends string>({ value, onChange, options, size = 'md' }: {
  value: T; onChange: (v: T) => void
  options: { value: T; label: string; icon?: React.ReactNode }[]
  size?: 'sm' | 'md'
}) {
  return (
    <div className="inline-flex gap-1 p-1 rounded-xl bg-ink-900/70 border border-white/[0.07] overflow-x-auto scroll-x max-w-full">
      {options.map((o) => (
        <button key={o.value} onClick={() => onChange(o.value)}
                className={`flex items-center gap-1.5 rounded-lg font-semibold whitespace-nowrap transition-colors
                  ${size === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm'}
                  ${value === o.value ? 'bg-brand text-ink-950' : 'text-zinc-400 hover:text-zinc-100'}`}>
          {o.icon}{o.label}
        </button>
      ))}
    </div>
  )
}

export function Slider({ value, onChange, min, max, step = 1, suffix = '' }: {
  value: number; onChange: (v: number) => void
  min: number; max: number; step?: number; suffix?: string
}) {
  return (
    <div className="flex items-center gap-3">
      <input type="range" min={min} max={max} step={step} value={value}
             onChange={(e) => onChange(Number(e.target.value))} className="flex-1" />
      <span className="text-xs font-mono text-zinc-400 w-14 text-right tabular-nums">
        {value}{suffix}
      </span>
    </div>
  )
}

export function Toggle({ checked, onChange, label, hint }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string
}) {
  return (
    <button type="button" onClick={() => onChange(!checked)}
            className="flex items-start gap-3 w-full text-left group">
      <span className={`mt-0.5 w-9 h-5 rounded-full flex-shrink-0 transition-colors relative
                        ${checked ? 'bg-brand' : 'bg-ink-600'}`}>
        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-ink-950 transition-transform
                          ${checked ? 'translate-x-[1.1rem]' : 'translate-x-0.5'}`} />
      </span>
      <span className="flex-1">
        <span className="text-sm font-medium text-zinc-200 group-hover:text-white">{label}</span>
        {hint && <span className="block text-[11px] text-zinc-500 mt-0.5">{hint}</span>}
      </span>
    </button>
  )
}

export function SearchInput({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder?: string
}) {
  return (
    <div className="relative">
      <IconSearch className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
      <input value={value} onChange={(e) => onChange(e.target.value)}
             placeholder={placeholder} className="field pl-9" />
    </div>
  )
}

export function Tabs<T extends string>({ value, onChange, tabs }: {
  value: T; onChange: (v: T) => void; tabs: { value: T; label: string; badge?: number }[]
}) {
  return (
    <div className="flex gap-1 border-b border-white/[0.07] overflow-x-auto scroll-x">
      {tabs.map((t) => (
        <button key={t.value} onClick={() => onChange(t.value)}
                className={`px-4 py-2.5 text-sm font-semibold whitespace-nowrap border-b-2 -mb-px transition-colors
                  ${value === t.value
                    ? 'border-brand text-zinc-50'
                    : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>
          {t.label}
          {t.badge !== undefined && t.badge > 0 && (
            <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-white/10">{t.badge}</span>
          )}
        </button>
      ))}
    </div>
  )
}

export function Checkbox({ checked, onChange, label }: {
  checked: boolean; onChange: (v: boolean) => void; label: React.ReactNode
}) {
  return (
    <button type="button" onClick={() => onChange(!checked)}
            className="flex items-center gap-2.5 text-sm text-zinc-300 hover:text-white">
      <span className={`w-[18px] h-[18px] rounded-md border flex items-center justify-center transition-colors
                        ${checked ? 'bg-brand border-brand text-ink-950' : 'border-white/20'}`}>
        {checked && <IconCheck className="w-3 h-3" />}
      </span>
      {label}
    </button>
  )
}

/* --------------------------------- datos --------------------------------- */

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const alive = useRef(true)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    return fnRef.current()
      .then((value) => { if (alive.current) setData(value) ; return value })
      .catch((err) => { if (alive.current) setError(err.message || 'Algo ha fallado') })
      .finally(() => { if (alive.current) setLoading(false) })
  }, [])

  useEffect(() => {
    alive.current = true
    reload()
    return () => { alive.current = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return useMemo(() => ({ data, loading, error, reload, setData }),
                 [data, loading, error, reload])
}

export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return debounced
}
