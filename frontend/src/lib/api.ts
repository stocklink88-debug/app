/** Cliente de la API de ViralClips. */

export type Layout = 'fill' | 'blur' | 'split'
export type CaptionStyle = 'none' | 'pop' | 'karaoke' | 'boxed' | 'minimal'

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
  transcription: {
    provider: string
    has_text: boolean
    openai: boolean
    groq: boolean
    faster_whisper: boolean
  }
  llm: { enabled: boolean; model: string | null }
  face_tracking: boolean
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
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

  updateClip: (id: string, data: Partial<Pick<Clip, 'title' | 'caption' | 'hashtags'>>) =>
    request<Clip>(`/api/clips/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  rerenderClip: (
    id: string,
    data: { layout?: Layout; caption_style?: CaptionStyle; aspect?: string; start?: number; end?: number },
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
  const source = new EventSource(`/api/projects/${projectId}/events`)
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
