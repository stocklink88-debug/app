import { useState } from 'react'
import { api } from '../lib/api'
import { useSession } from '../lib/session'
import { Field, Spinner, useToast } from '../components/ui'

const CLAIMS = [
  'Más de 140 presets de cámara y efectos virales',
  'Texto a vídeo, imagen a vídeo y primer/último fotograma',
  'Soul ID: tu personaje coherente en cada toma',
  'Avatares que hablan, música, doblaje y voces',
  'Estudio de anuncios con guion y montaje automático',
]

export default function Auth() {
  const { setUser, caps } = useSession()
  const toast = useToast()
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [invite, setInvite] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      const data = mode === 'login'
        ? await api.login({ email, password })
        : await api.signup({ email, password, name, invite_code: invite || undefined })
      setUser(data.user)
      toast(mode === 'login' ? 'Hola de nuevo' : '¡Cuenta creada! Tienes créditos para empezar.', 'ok')
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between p-12 border-r border-white/[0.06]
                      bg-gradient-to-br from-ink-900 to-ink-950">
        <div className="flex items-center gap-3">
          <span className="w-10 h-10 rounded-xl bg-brand grid place-items-center
                           text-ink-950 font-black text-lg">H</span>
          <span className="font-black text-xl tracking-tight">Higgs<span className="text-brand">Studio</span></span>
        </div>
        <div>
          <h1 className="text-5xl font-black leading-[1.05] tracking-tight">
            Haz vídeo<br />como un<br /><span className="text-brand">director</span>.
          </h1>
          <ul className="mt-8 space-y-2.5">
            {CLAIMS.map((claim) => (
              <li key={claim} className="flex items-start gap-2.5 text-sm text-zinc-400">
                <span className="w-1.5 h-1.5 rounded-full bg-brand mt-[7px] flex-shrink-0" />
                {claim}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-zinc-600 max-w-sm leading-relaxed">
          {caps?.demo_mode
            ? 'Esta instancia funciona en modo demostración: genera en local con ffmpeg, sin coste. Añade una clave de fal.ai, Replicate o ElevenLabs para usar modelos reales.'
            : `Generando con ${caps?.video.provider} · ${caps?.image.provider} · ${caps?.audio.provider}.`}
        </p>
      </div>

      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <span className="w-9 h-9 rounded-xl bg-brand grid place-items-center
                             text-ink-950 font-black">H</span>
            <span className="font-black text-lg">Higgs<span className="text-brand">Studio</span></span>
          </div>

          <div>
            <h2 className="text-2xl font-black tracking-tight">
              {mode === 'login' ? 'Entra en tu estudio' : 'Crea tu cuenta'}
            </h2>
            <p className="text-sm text-zinc-500 mt-1">
              {mode === 'login'
                ? 'Tus generaciones te están esperando.'
                : 'Empiezas con créditos suficientes para varias pruebas.'}
            </p>
          </div>

          {mode === 'signup' && (
            <Field label="Cómo te llamas">
              <input value={name} onChange={(e) => setName(e.target.value)}
                     className="field" placeholder="Ana García" autoComplete="name" />
            </Field>
          )}

          <Field label="Correo">
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                   className="field" placeholder="tu@correo.com" autoComplete="email" />
          </Field>

          <Field label="Contraseña" hint={mode === 'signup' ? 'Mínimo 8 caracteres.' : undefined}>
            <input type="password" required minLength={8} value={password}
                   onChange={(e) => setPassword(e.target.value)} className="field"
                   placeholder="••••••••"
                   autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
          </Field>

          {mode === 'signup' && caps?.invite_required && (
            <Field label="Código de invitación">
              <input value={invite} onChange={(e) => setInvite(e.target.value)}
                     className="field" placeholder="Te lo da quien administra la instancia" />
            </Field>
          )}

          <button type="submit" disabled={busy} className="btn-primary w-full">
            {busy && <Spinner />}
            {mode === 'login' ? 'Entrar' : 'Crear cuenta'}
          </button>

          {caps?.allow_signup !== false && (
            <p className="text-sm text-zinc-500 text-center">
              {mode === 'login' ? '¿Todavía no tienes cuenta?' : '¿Ya tienes cuenta?'}{' '}
              <button type="button" onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
                      className="text-brand font-semibold hover:underline">
                {mode === 'login' ? 'Regístrate' : 'Entra'}
              </button>
            </p>
          )}
        </form>
      </div>
    </div>
  )
}
