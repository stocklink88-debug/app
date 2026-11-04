/** Cliente de la API de ViralClips. */

export type Layout = 'fill' | 'blur' | 'split'
export type CaptionStyle = 'none' | 'pop' | 'karaoke' | 'boxed' | 'minimal'
export type AudioMode = 'original' | 'mute' | 'voiceover'

export interface Voice {
  voice_id: string
  name: string
  category: string | null
  description: string | null
  preview_url: string | null
  labels: Record<string, string>
}

export interface VoicePreview {
  generated_voice_id: string
  audio_data_url: string
  duration_secs: number
}

export interface ProjectOptions {
  clip_count: number
  min_duration: number
  max_duration: number
  layout: Layout
  caption_style: CaptionStyle
  aspect: string
  language: string | null
  output_language: string | null
  keywords: string | null
  normalize_audio: boolean
  resolution: number
  audio_mode: AudioMode
  voice_id: string | null
  background_volume: number
}

export interface Clip {
  id: string
  project_id: string
  index: number
  start: number
  end: number
  duration: number
  title: string
  hook: string
  summary: string
  score: number
  score_breakdown: Record<string, number | null>
  reasons: string[]
  keywords: string[]
  transcript: string
  caption: string
  hashtags: string[]
  layout: Layout
  caption_style: CaptionStyle
  aspect: string
  audio_mode: AudioMode
  voice_id: string | null
  voiceover_text: string
  status: 'pending' | 'rendering' | 'ready' | 'failed'
  error: string | null
  video_url: string | null
  thumb_url: string | null
}

export interface Project {
  id: string
  title: string
  source_type: string
  source_url: string | null
  status: 'queued' | 'running' | 'done' | 'failed'
  stage: string
  stage_label: string
  progress: number
  message: string
  error: string | null
  duration: number | null
  width: number | null
  height: number | null
  created_at: string
  updated_at: string
  options: Partial<ProjectOptions>
  language: string | null
  has_transcript: boolean
  clips: Clip[]
}

export interface Capabilities {
  auth_required?: boolean
  transcription: {
    provider: string
    has_text: boolean
    openai: boolean
    groq: boolean
    faster_whisper: boolean
  }
  llm: { enabled: boolean; model: string | null }
  voice: { enabled: boolean; model: string | null; default_voice_id: string | null }
  face_tracking: boolean
  audio_modes?: AudioMode[]
  defaults: ProjectOptions
  cost_per_hour_usd: number
  layouts: Layout[]
  caption_styles: CaptionStyle[]
  max_upload_mb: number
}

export interface ProgressEvent {
  project_id: string
  stage: string
  stage_label: string
  progress: number
  message: string
  status: string
  error?: string | null
}

/* ---------- Acceso protegido por contraseña (opcional) ---------- */

const TOKEN_KEY = 'viralclips.token'

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* modo privado del navegador: se queda sólo en memoria */
  }
}

/** Las etiquetas <video>/<img> y EventSource no mandan cabeceras: va en la URL. */
export function withToken(url: string): string {
  const token = getToken()
  if (!token) return url
  return `${url}${url.includes('?') ? '&' : '?'}access_token=${encodeURIComponent(token)}`
}

/** Se lanza cuando la contraseña falta o no es válida. */
export class UnauthorizedError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const headers = new Headers(init?.headers)
  if (token) headers.set('X-Access-Token', token)

  const res = await fetch(path, { ...init, headers })
  if (res.status === 401) throw new UnauthorizedError('Contraseña incorrecta o ausente.')
  if (!res.ok) {
    let detail = `Error ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const api = {
  authStatus: () => request<{ required: boolean }>('/api/auth/status'),

  capabilities: () => request<Capabilities>('/api/capabilities'),

  listProjects: () => request<Project[]>('/api/projects'),

  getProject: (id: string) => request<Project>(`/api/projects/${id}`),

  deleteProject: (id: string) =>
    request<{ ok: boolean }>(`/api/projects/${id}`, { method: 'DELETE' }),

  retryProject: (id: string) =>
    request<Project>(`/api/projects/${id}/retry`, { method: 'POST' }),

  createProject: (data: {
    file?: File
    subtitles?: File
    url?: string
    title?: string
    options: ProjectOptions
  }) => {
    const form = new FormData()
    if (data.file) form.append('file', data.file)
    if (data.subtitles) form.append('subtitles', data.subtitles)
    if (data.url) form.append('url', data.url)
    if (data.title) form.append('title', data.title)
    form.append('options', JSON.stringify(data.options))
    return request<Project>('/api/projects', { method: 'POST', body: form })
  },

  listVoices: () =>
    request<{ enabled: boolean; voices: Voice[]; default_voice_id?: string | null }>(
      '/api/voices',
    ),

  designVoice: (description: string, sampleText?: string) =>
    request<{ previews: VoicePreview[] }>('/api/voices/design', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description, sample_text: sampleText || null }),
    }),

  saveVoice: (data: { name: string; description: string; generated_voice_id: string }) =>
    request<Voice>('/api/voices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  updateClip: (
    id: string,
    data: Partial<Pick<Clip, 'title' | 'caption' | 'hashtags' | 'voiceover_text'>>,
  ) =>
    request<Clip>(`/api/clips/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  rerenderClip: (
    id: string,
    data: {
      layout?: Layout
      caption_style?: CaptionStyle
      aspect?: string
      start?: number
      end?: number
      audio_mode?: AudioMode
      voice_id?: string | null
      voiceover_text?: string
      background_volume?: number
    },
  ) =>
    request<Clip>(`/api/clips/${id}/rerender`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  getClip: (id: string) => request<Clip>(`/api/clips/${id}`),
}

/** Suscripción al progreso del proyecto vía Server-Sent Events. */
export function subscribeProgress(
  projectId: string,
  onEvent: (e: ProgressEvent) => void,
): () => void {
  const source = new EventSource(withToken(`/api/projects/${projectId}/events`))
  source.addEventListener('progress', (ev) => {
    try {
      onEvent(JSON.parse((ev as MessageEvent).data))
    } catch {
      /* evento malformado: se ignora */
    }
  })
  source.onerror = () => source.close()
  return () => source.close()
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return '—'
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
