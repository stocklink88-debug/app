import { useState } from 'react'
import { api, setToken, UnauthorizedError } from '../lib/api'
import { IconSparkles } from './Icons'

interface Props {
  onUnlocked: () => void
}

/** Pantalla de acceso, sólo visible si el servidor tiene ACCESS_PASSWORD. */
export default function LoginScreen({ onUnlocked }: Props) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!password.trim()) return
    setChecking(true)
    setError(null)
    setToken(password.trim())
    try {
      await api.capabilities()      // valida la contraseña contra la API
      onUnlocked()
    } catch (err) {
      setToken('')
      setError(
        err instanceof UnauthorizedError
          ? 'Contraseña incorrecta.'
          : 'No se pudo contactar con el servidor.',
      )
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <form onSubmit={submit} className="card p-7 w-full max-w-sm">
        <div className="flex items-center gap-2.5 mb-5">
          <span className="w-8 h-8 rounded-xl bg-accent grid place-items-center shrink-0">
            <IconSparkles className="w-4 h-4 text-ink-900" />
          </span>
          <span className="font-extrabold tracking-tight text-lg">ViralClips</span>
        </div>

        <label className="label" htmlFor="pw">Contraseña de acceso</label>
        <input
          id="pw" type="password" className="field" autoFocus autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)}
        />

        {error && <p className="text-sm text-coral mt-3">{error}</p>}

        <button type="submit" disabled={checking} className="btn-primary w-full mt-5">
          {checking ? 'Comprobando…' : 'Entrar'}
        </button>

        <p className="text-[11px] text-slate-500 mt-4 leading-relaxed">
          Es la contraseña definida en <code className="font-mono">ACCESS_PASSWORD</code> en
          el servidor.
        </p>
      </form>
    </div>
  )
}
