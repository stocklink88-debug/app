export function bytes(n: number): string {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1)
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`
}

export function seconds(n: number | null | undefined): string {
  if (!n && n !== 0) return '—'
  const total = Math.round(n)
  const m = Math.floor(total / 60)
  const s = total % 60
  return m ? `${m}:${String(s).padStart(2, '0')}` : `${total}s`
}

export function relative(iso: string | null | undefined): string {
  if (!iso) return ''
  const then = new Date(iso.endsWith('Z') ? iso : `${iso}Z`).getTime()
  const diff = Math.max(0, Date.now() - then) / 1000
  if (diff < 60) return 'hace un momento'
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`
  if (diff < 604800) return `hace ${Math.floor(diff / 86400)} d`
  return new Date(then).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

export const STATUS_LABEL: Record<string, string> = {
  queued: 'En cola',
  running: 'Generando',
  succeeded: 'Listo',
  failed: 'Error',
  canceled: 'Cancelado',
}

export const STATUS_COLOR: Record<string, string> = {
  queued: 'text-zinc-400 bg-white/[0.07]',
  running: 'text-aqua bg-aqua/15',
  succeeded: 'text-brand bg-brand/15',
  failed: 'text-flame bg-flame/15',
  canceled: 'text-zinc-500 bg-white/[0.05]',
}

export const TYPE_LABEL: Record<string, string> = {
  video: 'Vídeo',
  image: 'Imagen',
  speak: 'Avatar',
  audio: 'Audio',
  tool: 'Herramienta',
  train_character: 'Entrenamiento',
  ad_campaign: 'Anuncio',
  influencer_sheet: 'Personaje',
  virality: 'Análisis',
}

export const ASPECT_RATIO: Record<string, string> = {
  '16:9': '16 / 9', '9:16': '9 / 16', '1:1': '1 / 1', '4:3': '4 / 3',
  '3:4': '3 / 4', '4:5': '4 / 5', '21:9': '21 / 9', '2:3': '2 / 3', '3:2': '3 / 2',
}

export function copy(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text)
  const area = document.createElement('textarea')
  area.value = text
  document.body.appendChild(area)
  area.select()
  document.execCommand('copy')
  area.remove()
  return Promise.resolve()
}
