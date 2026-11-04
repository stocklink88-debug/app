import { useEffect, useRef, useState } from 'react'
import type { Voice, VoicePreview } from '../lib/api'
import { api } from '../lib/api'
import { IconPlay, IconSparkles, IconX } from './Icons'

interface Props {
  value: string | null
  onChange: (voiceId: string | null) => void
  disabled?: boolean
}

/** Selector de voz de ElevenLabs, con diseño de voces nuevas desde una descripción. */
export default function VoicePicker({ value, onChange, disabled }: Props) {
  const [voices, setVoices] = useState<Voice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [designing, setDesigning] = useState(false)

  useEffect(() => { load() }, [])

  async function load(selectId?: string) {
    setLoading(true)
    try {
      const data = await api.listVoices()
      setVoices(data.voices)
      setError(data.enabled ? null : 'Falta ELEVENLABS_API_KEY en el servidor.')
      if (selectId) onChange(selectId)
      else if (!value && data.default_voice_id) onChange(data.default_voice_id)
      else if (!value && data.voices.length) onChange(data.voices[0].voice_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar las voces.')
    } finally {
      setLoading(false)
    }
  }

  const selected = voices.find((v) => v.voice_id === value)

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="label mb-0">Voz</label>
        <button
          type="button" disabled={disabled}
          onClick={() => setDesigning(true)}
          className="btn-ghost btn-sm"
        >
          <IconSparkles className="w-3 h-3" /> Crear voz con IA
        </button>
      </div>

      {loading ? (
        <p className="text-xs text-slate-500 py-2">Cargando voces…</p>
      ) : (
        <div className="flex gap-2">
          <select
            className="field flex-1" value={value ?? ''} disabled={disabled || !voices.length}
            onChange={(e) => onChange(e.target.value || null)}
          >
            {!voices.length && <option value="">Sin voces disponibles</option>}
            {voices.map((v) => (
              <option key={v.voice_id} value={v.voice_id}>
                {v.name}{v.labels?.accent ? ` · ${v.labels.accent}` : ''}
              </option>
            ))}
          </select>
          {selected?.preview_url && (
            <PreviewButton url={selected.preview_url} title={`Escuchar ${selected.name}`} />
          )}
        </div>
      )}

      {error && <p className="text-xs text-coral mt-1.5">{error}</p>}

      {designing && (
        <DesignVoiceDialog
          onClose={() => setDesigning(false)}
          onSaved={(voiceId) => { setDesigning(false); load(voiceId) }}
        />
      )}
    </div>
  )
}

function PreviewButton({ url, title }: { url: string; title: string }) {
  const audio = useRef<HTMLAudioElement | null>(null)
  const [playing, setPlaying] = useState(false)

  function toggle() {
    if (!audio.current) {
      audio.current = new Audio(url)
      audio.current.onended = () => setPlaying(false)
    }
    if (playing) { audio.current.pause(); setPlaying(false) }
    else { audio.current.play().catch(() => setPlaying(false)); setPlaying(true) }
  }

  return (
    <button type="button" onClick={toggle} className="btn-ghost shrink-0" title={title}>
      {playing ? <IconX className="w-3.5 h-3.5" /> : <IconPlay className="w-3.5 h-3.5" />}
    </button>
  )
}

interface DialogProps {
  onClose: () => void
  onSaved: (voiceId: string) => void
}

function DesignVoiceDialog({ onClose, onSaved }: DialogProps) {
  const [description, setDescription] = useState('')
  const [name, setName] = useState('')
  const [previews, setPreviews] = useState<VoicePreview[]>([])
  const [chosen, setChosen] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function generate() {
    setBusy(true); setError(null); setPreviews([]); setChosen(null)
    try {
      const data = await api.designVoice(description)
      setPreviews(data.previews)
      setChosen(data.previews[0]?.generated_voice_id ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo diseñar la voz.')
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    if (!chosen) return
    setBusy(true); setError(null)
    try {
      const voice = await api.saveVoice({
        name: name.trim() || 'Voz personalizada',
        description,
        generated_voice_id: chosen,
      })
      onSaved(voice.voice_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar la voz.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] bg-ink-900/85 backdrop-blur-sm overflow-y-auto"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="min-h-full flex items-start justify-center p-4 sm:p-8">
        <div className="card w-full max-w-lg p-5 sm:p-6 rise">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold">Crear una voz con IA</h3>
            <button onClick={onClose} className="btn-ghost btn-sm"><IconX /></button>
          </div>

          <label className="label">Describe la voz</label>
          <textarea
            className="field min-h-[80px] resize-y"
            placeholder="Mujer joven española, tono cercano y enérgico, habla rápido y con entusiasmo, como una presentadora de vídeos cortos."
            value={description} onChange={(e) => setDescription(e.target.value)}
          />
          <p className="text-[11px] text-slate-500 mt-1.5">
            Cuanto más detalle (edad, acento, tono, ritmo, actitud), más se acerca el
            resultado. Mínimo 20 caracteres.
          </p>

          <button
            type="button" onClick={generate}
            disabled={busy || description.trim().length < 20}
            className="btn-ghost w-full mt-3"
          >
            {busy && !previews.length ? 'Generando voces…' : 'Generar propuestas'}
          </button>

          {previews.length > 0 && (
            <div className="mt-5">
              <label className="label">Elige la que más te guste</label>
              <div className="space-y-2">
                {previews.map((p, i) => (
                  <label
                    key={p.generated_voice_id}
                    className={`flex items-center gap-3 rounded-xl border p-3 cursor-pointer transition
                      ${chosen === p.generated_voice_id
                        ? 'border-accent/60 bg-accent/[0.08]'
                        : 'border-white/10 hover:border-white/25'}`}
                  >
                    <input
                      type="radio" name="preview" className="accent-accent"
                      checked={chosen === p.generated_voice_id}
                      onChange={() => setChosen(p.generated_voice_id)}
                    />
                    <span className="text-sm flex-1">Opción {i + 1}</span>
                    <audio src={p.audio_data_url} controls className="h-8 max-w-[180px]" />
                  </label>
                ))}
              </div>

              <label className="label mt-4">Nombre para guardarla</label>
              <input
                className="field" placeholder="Mi voz de shorts"
                value={name} onChange={(e) => setName(e.target.value)}
              />

              <button
                type="button" onClick={save} disabled={busy || !chosen}
                className="btn-primary w-full mt-3"
              >
                {busy ? 'Guardando…' : 'Guardar y usar esta voz'}
              </button>
            </div>
          )}

          {error && <p className="text-sm text-coral mt-3">{error}</p>}
        </div>
      </div>
    </div>
  )
}
