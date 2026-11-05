import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Voice } from '../lib/api'
import { Badge, EmptyState, Field, Modal, Spinner, useAsync, useToast } from '../components/ui'
import { IconMic, IconPlay, IconPlus, IconTrash } from '../components/Icons'

export default function Voices() {
  const navigate = useNavigate()
  const toast = useToast()
  const { data, loading, reload } = useAsync(() => api.voices(), [])
  const [cloning, setCloning] = useState(false)
  const [previewing, setPreviewing] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const preview = async (voice: Voice) => {
    setPreviewing(voice.id)
    try {
      const { preview_url } = await api.previewVoice({ voice_id: voice.id })
      if (audioRef.current) {
        audioRef.current.src = preview_url
        await audioRef.current.play()
      }
    } catch (e: any) { toast(e.message, 'error') } finally { setPreviewing(null) }
  }

  return (
    <div className="max-w-[1500px] mx-auto px-4 sm:px-6 py-6">
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="mr-auto">
          <h1 className="text-2xl font-black tracking-tight">Voces</h1>
          <p className="text-sm text-zinc-500">
            Para locución, avatares que hablan y doblaje.
            {data && !data.cloning_available && ' Clonar voces necesita una clave de ElevenLabs.'}
          </p>
        </div>
        <button onClick={() => setCloning(true)} disabled={!data?.cloning_available}
                className="btn-ghost btn-sm">
          <IconPlus className="w-4 h-4" />Clonar una voz
        </button>
        <button onClick={() => navigate('/crear', { state: { family: 'audio', mode: 'tts' } })}
                className="btn-primary btn-sm">Generar locución</button>
      </div>

      {loading ? (
        <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-28 rounded-2xl" />)}
        </div>
      ) : (data?.voices.length ?? 0) === 0 ? (
        <EmptyState icon={<IconMic className="w-12 h-12" />} title="No hay voces" />
      ) : (
        <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {data!.voices.map((voice) => (
            <div key={voice.id} className="card p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-semibold truncate">{voice.name}</p>
                  <p className="text-[11px] text-zinc-500 truncate">
                    {voice.labels?.accent || voice.provider}
                  </p>
                </div>
                <Badge tone={voice.kind === 'cloned' ? 'iris' : 'default'}>{voice.kind}</Badge>
              </div>
              <p className="text-xs text-zinc-400 mt-2 line-clamp-2 min-h-[2rem]">
                {voice.description}
              </p>
              <div className="flex gap-2 mt-3">
                <button onClick={() => preview(voice)} disabled={previewing === voice.id}
                        className="btn-ghost btn-sm flex-1">
                  {previewing === voice.id ? <Spinner /> : <IconPlay className="w-3.5 h-3.5" />}
                  Escuchar
                </button>
                {voice.kind === 'cloned' && (
                  <button onClick={() => api.deleteVoice(voice.id).then(reload)}
                          className="btn-ghost btn-sm !px-2">
                    <IconTrash className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <audio ref={audioRef} hidden />
      <CloneVoice open={cloning} onClose={() => setCloning(false)} onDone={reload} />
    </div>
  )
}

function CloneVoice({ open, onClose, onDone }: {
  open: boolean; onClose: () => void; onDone: () => void
}) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!name.trim() || !files.length) return
    setBusy(true)
    try {
      await api.cloneVoice(name, files, description)
      toast('Voz clonada', 'ok')
      onDone()
      onClose()
      setName(''); setFiles([])
    } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Clonar una voz"
           footer={<button onClick={submit} disabled={busy || !name.trim() || !files.length}
                           className="btn-primary btn-sm w-full">
             {busy && <Spinner />}Clonar</button>}>
      <div className="space-y-3">
        <p className="text-xs text-zinc-500 leading-relaxed">
          Sube entre 1 y 25 grabaciones limpias de la misma persona. Clona solo voces
          sobre las que tengas permiso: es tu responsabilidad.
        </p>
        <Field label="Nombre">
          <input value={name} onChange={(e) => setName(e.target.value)} className="field" autoFocus />
        </Field>
        <Field label="Descripción">
          <input value={description} onChange={(e) => setDescription(e.target.value)}
                 className="field" placeholder="Voz grave, narración" />
        </Field>
        <Field label={`Muestras (${files.length})`}>
          <input type="file" accept="audio/*" multiple className="field !py-2"
                 onChange={(e) => setFiles(Array.from(e.target.files || []))} />
        </Field>
      </div>
    </Modal>
  )
}
