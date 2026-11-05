/** Cliente de la API de HiggsStudio. */

export interface User {
  id: string; email: string; name: string; avatar_url: string | null
  plan: string; credits: number; is_admin: boolean
  prefs: Record<string, unknown>; created_at: string
}

export interface Plan {
  id: string; name: string; price_eur: number; monthly_credits: number
  badge?: string; features: string[]; limits: Record<string, unknown>
}

export interface Model {
  id: string; name: string; vendor: string; family: string; tier: string
  badge: string | null; description: string; modes: string[]
  durations?: number[]; resolutions?: string[]; aspects?: string[]
  max_duration?: number; credits_base: number; credits_per_second?: number
  credits_per_image?: number; supports: Record<string, unknown>
  providers: Record<string, string>
}

export interface Preset {
  id: string; name: string; category: string; motion: string; prompt: string
  badge: string | null; duration: number; aspect: string; kind: string
  intensity: number; tags: string[]; needs_image: boolean
  credits_mult: number; favorite?: boolean
}

export interface Style { id: string; name: string; group: string; prompt: string; badge: string | null }

export interface Asset {
  id: string; kind: 'video' | 'image' | 'audio' | 'model3d'
  url: string; thumb_url: string | null; download_url: string
  width: number | null; height: number | null; duration: number | null
  fps: number | null; size_bytes: number; prompt: string; model: string
  preset: string | null; params: Record<string, any>; source: string
  favorite: boolean; tags: string[]; seed: number | null
  project_id: string | null; folder_id: string | null; job_id: string | null
  created_at: string
}

export interface Job {
  id: string; type: string; model: string; provider: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
  progress: number; stage: string; message: string; error: string | null
  params: Record<string, any>; result: { assets?: Asset[]; [k: string]: any }
  cost_credits: number; refunded: boolean; batch_id: string | null
  project_id: string | null; created_at: string
  started_at: string | null; finished_at: string | null
}

export interface Project {
  id: string; title: string; kind: string; description: string
  folder_id: string | null; cover_asset_id: string | null; cover?: Asset | null
  canvas: { nodes: any[]; edges: any[] }; timeline: { tracks: any[] }
  archived: number; asset_count?: number; created_at: string; updated_at: string
}

export interface Character {
  id: string; name: string; kind: string; status: string; description: string
  traits: Record<string, any>; ref_asset_ids: string[]; sheet_asset_ids: string[]
  cover_asset_id: string | null; voice_id: string | null; trigger_word: string
  sheet: Asset[]; references: Asset[]; cover?: Asset | null
  created_at: string; updated_at: string
}

export interface Voice {
  id: string; name: string; provider: string; provider_voice_id: string
  kind: string; description: string; labels: Record<string, any>
  preview_url?: string | null
}

export interface Brand {
  id: string; name: string; website: string; description: string; tone: string
  palette: string[]; fonts: string[]; logo_asset_id: string | null
  logo?: Asset | null; product_count?: number
}

export interface Product {
  id: string; brand_id: string | null; name: string; description: string
  category: string; price: string; url: string; asset_ids: string[]; images: Asset[]
}

export interface Post {
  id: string; title: string; prompt: string; model: string; preset: string | null
  likes: number; views: number; liked: boolean; featured: boolean
  remix_of: string | null; created_at: string
  author: { id: string; name: string; avatar_url: string | null }
  media: { kind: string; url: string; thumb_url: string | null
           width: number | null; height: number | null; duration: number | null }
}

export interface Quote {
  credits: number; model: string; model_name: string
  detail: Record<string, any>; balance?: number; affordable?: boolean
}

export interface Capabilities {
  video: { provider: string; real: boolean }
  image: { provider: string; real: boolean }
  audio: { provider: string; real: boolean }
  prompt_enhance: boolean; voice_cloning: boolean; demo_mode: boolean
  allow_signup: boolean; invite_required: boolean; max_upload_mb: number
  providers_configured: Record<string, boolean>
  providers_available: string[]; version: string
}

export interface Virality {
  score: number; breakdown: Record<string, number>
  platforms: Record<string, number>; tips: string[]; best_platform: string
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData
  const response = await fetch(path, {
    credentials: 'include',
    ...init,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...(init.headers || {}),
    },
  })
  if (!response.ok) {
    let detail = `Error ${response.status}`
    try {
      const data = await response.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch { /* respuesta sin cuerpo JSON */ }
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const get = <T,>(path: string) => request<T>(path)
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
const del = <T,>(path: string) => request<T>(path, { method: 'DELETE' })

export interface GenerateParams {
  model?: string; mode?: string; prompt?: string; negative_prompt?: string
  duration?: number; aspect?: string; resolution?: string; fps?: number
  seed?: number | null; count?: number; preset?: string | null; style?: string | null
  character_id?: string | null; voice_id?: string | null
  project_id?: string | null; folder_id?: string | null
  image_asset_ids?: string[]; end_image_asset_id?: string | null
  video_asset_id?: string | null; audio_asset_id?: string | null
  clip_asset_ids?: string[]; music_asset_id?: string | null
  with_audio?: boolean; enhance_prompt?: boolean; provider?: string | null
  // parámetros propios de las herramientas de posproducción
  factor?: number; target_fps?: number; slow_factor?: number
  target_aspect?: string; fill?: string; extra_seconds?: number
  transition?: string; language?: string; emotion?: string
  extra?: Record<string, unknown>
}

export const api = {
  // --- cuenta ---
  signup: (b: { email: string; password: string; name?: string; invite_code?: string }) =>
    post<{ user: User; token: string }>('/api/auth/signup', b),
  login: (b: { email: string; password: string }) =>
    post<{ user: User; token: string }>('/api/auth/login', b),
  logout: () => post<{ ok: boolean }>('/api/auth/logout'),
  me: () => get<{ user: User; plan: Plan; credits: number }>('/api/auth/me'),
  updateMe: (b: Partial<Pick<User, 'name' | 'avatar_url'>> & { prefs?: Record<string, unknown> }) =>
    patch<{ user: User }>('/api/auth/me', b),
  changePassword: (b: { current_password: string; new_password: string }) =>
    post<{ ok: boolean }>('/api/auth/password', b),

  // --- catálogo ---
  capabilities: () => get<Capabilities>('/api/capabilities'),
  models: (family?: string, mode?: string) => {
    const q = new URLSearchParams()
    if (family) q.set('family', family)
    if (mode) q.set('mode', mode)
    return get<{ models: Model[]; aspects: string[]; resolutions: string[] }>(
      `/api/models?${q}`)
  },
  presets: (category?: string, search?: string) => {
    const q = new URLSearchParams()
    if (category) q.set('category', category)
    if (search) q.set('search', search)
    return get<{ presets: Preset[]; categories: { id: string; name: string; description: string }[]; total: number }>(
      `/api/presets?${q}`)
  },
  togglePresetFavorite: (id: string) => post<{ favorite: boolean }>(`/api/presets/${id}/favorite`),
  styles: () => get<{ styles: Style[]; groups: { id: string; name: string }[] }>('/api/styles'),
  options: () => get<any>('/api/options'),
  plans: () => get<{ plans: Plan[]; packs: any[] }>('/api/plans'),

  // --- generar ---
  quote: (b: GenerateParams & { type: string }) => post<Quote>('/api/generate/quote', b),
  generateVideo: (b: GenerateParams) =>
    post<{ job: Job; quote: Quote; credits_left: number }>('/api/generate/video', b),
  generateImage: (b: GenerateParams) =>
    post<{ job: Job; quote: Quote; credits_left: number }>('/api/generate/image', b),
  generateSpeak: (b: GenerateParams) =>
    post<{ job: Job; quote: Quote; credits_left: number }>('/api/generate/speak', b),
  generateAudio: (b: GenerateParams) =>
    post<{ job: Job; quote: Quote; credits_left: number }>('/api/generate/audio', b),
  runTool: (tool: string, b: GenerateParams) =>
    post<{ job: Job; quote: Quote; credits_left: number }>(`/api/tools/${tool}`, b),
  generateBatch: (b: { type: string; base: GenerateParams; prompts?: string[]; presets?: string[]; seeds?: number[] }) =>
    post<{ batch_id: string; jobs: Job[]; total_credits: number }>('/api/generate/batch', b),
  generateAd: (b: Record<string, unknown>) =>
    post<{ job: Job; estimated_credits: number }>('/api/generate/ad', b),
  generateSheet: (b: Record<string, unknown>) =>
    post<{ job: Job; estimated_credits: number }>('/api/generate/character-sheet', b),
  enhancePrompt: (b: { prompt: string; kind?: string; style?: string; preset?: string }) =>
    post<{ prompt: string; enhanced: boolean; source: string }>('/api/prompt/enhance', b),
  promptVariations: (b: { prompt: string; count?: number }) =>
    post<{ variations: string[] }>('/api/prompt/variations', b),
  negativePrompt: (kind = 'video') =>
    get<{ negative_prompt: string }>(`/api/prompt/negative?kind=${kind}`),
  virality: (b: Record<string, unknown>) => post<Virality>('/api/analyze/virality', b),

  // --- trabajos ---
  jobs: (q: Record<string, string | number | undefined> = {}) => {
    const params = new URLSearchParams()
    Object.entries(q).forEach(([k, v]) => v !== undefined && params.set(k, String(v)))
    return get<{ jobs: Job[]; total: number }>(`/api/jobs?${params}`)
  },
  activeJobs: () => get<{ jobs: Job[] }>('/api/jobs/active'),
  job: (id: string) => get<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => del<Job>(`/api/jobs/${id}`),
  retryJob: (id: string) => post<{ job: Job }>(`/api/jobs/${id}/retry`),

  // --- biblioteca ---
  assets: (q: Record<string, string | number | boolean | undefined> = {}) => {
    const params = new URLSearchParams()
    Object.entries(q).forEach(([k, v]) => v !== undefined && v !== '' && params.set(k, String(v)))
    return get<{ assets: Asset[]; total: number; usage: any }>(`/api/assets?${params}`)
  },
  asset: (id: string) => get<{ asset: Asset }>(`/api/assets/${id}`),
  patchAsset: (id: string, b: Record<string, unknown>) =>
    patch<{ asset: Asset }>(`/api/assets/${id}`, b),
  deleteAsset: (id: string) => del<{ ok: boolean }>(`/api/assets/${id}`),
  upload: async (file: File, extra: Record<string, string> = {}) => {
    const form = new FormData()
    form.append('file', file)
    Object.entries(extra).forEach(([k, v]) => form.append(k, v))
    return request<{ asset: Asset }>('/api/assets/upload', { method: 'POST', body: form })
  },
  collections: () => get<{ collections: any[] }>('/api/assets/collections/list'),
  createCollection: (name: string) => post<{ collection: any }>('/api/assets/collections', { name }),
  addToCollection: (cid: string, aid: string) =>
    post<{ ok: boolean }>(`/api/assets/collections/${cid}/items/${aid}`),
  collectionItems: (cid: string) =>
    get<{ collection: any; assets: Asset[] }>(`/api/assets/collections/${cid}/items`),

  // --- proyectos ---
  projects: (archived = false) => get<{ projects: Project[] }>(`/api/projects?archived=${archived}`),
  project: (id: string) =>
    get<{ project: Project; assets: Asset[]; jobs: Job[] }>(`/api/projects/${id}`),
  createProject: (b: { title: string; kind?: string; description?: string }) =>
    post<{ project: Project }>('/api/projects', b),
  patchProject: (id: string, b: Record<string, unknown>) =>
    patch<{ project: Project }>(`/api/projects/${id}`, b),
  deleteProject: (id: string, purge = false) =>
    del<{ ok: boolean }>(`/api/projects/${id}?purge=${purge}`),
  folders: () => get<{ folders: any[] }>('/api/folders'),
  createFolder: (b: { name: string; color?: string }) => post<{ folder: any }>('/api/folders', b),
  deleteFolder: (id: string) => del<{ ok: boolean }>(`/api/folders/${id}`),

  // --- personajes ---
  characters: (kind?: string) =>
    get<{ characters: Character[]; limit: number; avatar_presets: any[] }>(
      `/api/characters${kind ? `?kind=${kind}` : ''}`),
  createCharacter: (b: Record<string, unknown>) =>
    post<{ character: Character }>('/api/characters', b),
  patchCharacter: (id: string, b: Record<string, unknown>) =>
    patch<{ character: Character }>(`/api/characters/${id}`, b),
  deleteCharacter: (id: string) => del<{ ok: boolean }>(`/api/characters/${id}`),
  trainCharacter: (id: string, b: Record<string, unknown>) =>
    post<{ job: Job; quote: Quote }>(`/api/characters/${id}/train`, b),

  // --- marcas y productos ---
  brands: () => get<{ brands: Brand[]; templates: any[] }>('/api/brands'),
  createBrand: (b: Record<string, unknown>) => post<{ brand: Brand }>('/api/brands', b),
  deleteBrand: (id: string) => del<{ ok: boolean }>(`/api/brands/${id}`),
  products: (brandId?: string) =>
    get<{ products: Product[] }>(`/api/products${brandId ? `?brand_id=${brandId}` : ''}`),
  createProduct: (b: Record<string, unknown>) => post<{ product: Product }>('/api/products', b),
  deleteProduct: (id: string) => del<{ ok: boolean }>(`/api/products/${id}`),

  // --- voces ---
  voices: () => get<{ voices: Voice[]; emotions: any[]; languages: any[]; cloning_available: boolean }>('/api/voices'),
  previewVoice: (b: { voice_id: string; text?: string }) =>
    post<{ preview_url: string; voice: Voice }>('/api/voices/preview', b),
  cloneVoice: async (name: string, files: File[], description = '') => {
    const form = new FormData()
    form.append('name', name)
    form.append('description', description)
    files.forEach((f) => form.append('files', f))
    return request<{ voice: Voice }>('/api/voices/clone', { method: 'POST', body: form })
  },
  deleteVoice: (id: string) => del<{ ok: boolean }>(`/api/voices/${id}`),

  // --- comunidad ---
  feed: (q: Record<string, string | number | undefined> = {}) => {
    const params = new URLSearchParams()
    Object.entries(q).forEach(([k, v]) => v !== undefined && v !== '' && params.set(k, String(v)))
    return get<{ posts: Post[] }>(`/api/community/feed?${params}`)
  },
  myPosts: () => get<{ posts: Post[] }>('/api/community/mine'),
  publish: (b: { asset_id: string; title?: string; visibility?: string }) =>
    post<{ post: Post }>('/api/community/publish', b),
  likePost: (id: string) => post<{ liked: boolean; likes: number }>(`/api/community/posts/${id}/like`),
  postDetail: (id: string) => get<{ post: Post; comments: any[] }>(`/api/community/posts/${id}`),
  commentPost: (id: string, body: string) =>
    post<{ comment: any }>(`/api/community/posts/${id}/comments`, { body }),
  remix: (id: string) => get<Record<string, any>>(`/api/community/posts/${id}/remix`),
  unpublish: (id: string) => del<{ ok: boolean }>(`/api/community/posts/${id}`),

  // --- créditos ---
  billing: () => get<any>('/api/billing/summary'),
  transactions: () => get<{ transactions: any[] }>('/api/billing/transactions'),
  changePlan: (plan_id: string) => post<any>('/api/billing/plan', { plan_id }),
  buyPack: (pack_id: string) => post<any>('/api/billing/packs', { pack_id }),

  // --- cuenta avanzada ---
  apiKeys: () => get<{ keys: any[] }>('/api/account/api-keys'),
  createApiKey: (name: string) => post<{ key: any; secret: string }>('/api/account/api-keys', { name }),
  revokeApiKey: (id: string) => del<{ ok: boolean }>(`/api/account/api-keys/${id}`),
  webhooks: () => get<{ webhooks: any[]; events: string[] }>('/api/account/webhooks'),
  createWebhook: (b: { url: string; events?: string[] }) =>
    post<{ webhook: any; secret: string }>('/api/account/webhooks', b),
  deleteWebhook: (id: string) => del<{ ok: boolean }>(`/api/account/webhooks/${id}`),
  usage: () => get<any>('/api/account/usage'),
}
