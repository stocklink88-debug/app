# ViralClips

Convierte vídeos largos (podcasts, charlas, directos, entrevistas) en clips
verticales listos para TikTok, Reels y Shorts. Es una alternativa autoalojada a
OpusClip: tú pones el vídeo y las claves de API, y los clips se generan en tu
propia máquina.

![pipeline](https://img.shields.io/badge/pipeline-transcribir%20→%20analizar%20→%20recortar%20→%20subtitular-FFD24A)

> **En este repositorio hay dos apps.** Esta es ViralClips. En
> [`higgsstudio/`](higgsstudio/) está **HiggsStudio**, un estudio de generación
> de vídeo e imagen con IA (presets de cámara, Soul ID, avatares que hablan,
> estudio de anuncios y posproducción), con su propio README y su propio
> despliegue.


## Qué hace exactamente

1. **Ingesta** el vídeo desde un archivo o desde una URL (YouTube, Vimeo,
   Twitch… cualquier fuente que soporte yt-dlp).
2. **Transcribe** el audio con marcas de tiempo por palabra.
3. **Busca los momentos con más potencial**: parte la transcripción en frases,
   genera ventanas candidatas y las puntúa. Claude elige las mejores y escribe
   títulos, ganchos y copys; si no hay clave de Claude, decide la heurística.
4. **Ajusta el audio**: lo deja como está, lo silencia por completo, o lo
   sustituye por una locución generada con IA (ElevenLabs).
5. **Reencuadra a vertical siguiendo al sujeto**: detecta caras con YuNet,
   suaviza la trayectoria y hace un paneo limpio, cortando en seco en los
   cambios de plano en vez de barrer entre escenas.
6. **Quema subtítulos animados** palabra a palabra, al estilo de los clips que
   funcionan, y normaliza el volumen a −14 LUFS.
7. **Entrega** cada clip en MP4 con su miniatura, su nota de viralidad, el texto
   para publicar, los hashtags y el `.srt` por si quieres retocarlo fuera.

## Puesta en marcha

Necesitas **ffmpeg**, **Python 3.11+** y **Node 20+**.

```bash
# ffmpeg
sudo apt install ffmpeg      # Debian/Ubuntu
brew install ffmpeg          # macOS

git clone <este-repo> && cd app
cp .env.example .env         # rellena lo que quieras usar (todo es opcional)
make install                 # dependencias + modelo de detección de caras
make run                     # http://localhost:8000
```

Al arrancar, el servidor imprime las direcciones:

```
Abre la app en:  http://localhost:8000
Desde el móvil (misma red wifi):  http://192.168.1.42:8000
```

La segunda es la útil para **abrirla desde el móvil** sin desplegar nada: el
teléfono y el ordenador tienen que estar en la misma red. Si el navegador del
móvil no conecta, suele ser el cortafuegos del ordenador bloqueando el puerto
8000.

Para desarrollo, con recarga en caliente, en dos terminales:

```bash
make dev-api   # API en :8000
make dev-ui    # interfaz en :5173
```

O con Docker, sin instalar nada más:

```bash
cp .env.example .env
docker compose up --build    # http://localhost:8000
```

### En Windows

El `Makefile` usa rutas de Unix, así que en PowerShell no funciona. Usa Docker
Desktop (requiere WSL2, que su instalador configura):

```powershell
git clone -b claude/viral-clips-app-zzqjc9 https://github.com/stocklink88-debug/app.git viralclips
cd viralclips
Copy-Item .env.example .env
notepad .env                 # pon aquí tu GROQ_API_KEY
docker compose up --build
```

La primera construcción descarga cerca de 1 GB y tarda varios minutos; las
siguientes son casi instantáneas. Luego abres <http://localhost:8000>.

Para entrar desde el móvil necesitas la IP del ordenador: ejecuta `ipconfig` y
busca la *Dirección IPv4* (algo como `192.168.1.42`); en el móvil abres
`http://192.168.1.42:8000`. La primera vez Windows preguntará si permites el
acceso: hay que aceptar para redes privadas.

Si prefieres no usar Docker, la alternativa en Windows es instalar todo dentro
de WSL2 y seguir los pasos de Linux.

## Usarlo desde el móvil

En un teléfono no puedes instalar nada, así que la vía es desplegarlo en un
servidor y abrirlo en el navegador. Todo el proceso se hace desde la web:

1. Entra en [render.com](https://render.com) y crea cuenta con GitHub.
2. **New → Blueprint**, elige este repositorio y la rama. Render lee
   `render.yaml` y configura el servicio solo.
3. En las variables de entorno del servicio, rellena `GROQ_API_KEY` y, si
   quieres, `ANTHROPIC_API_KEY`. Render genera `ACCESS_PASSWORD` por ti: la
   encuentras en la pestaña *Environment*.
4. Abre la URL que te da Render e introduce esa contraseña.

Railway o Fly.io sirven igual: ambos detectan el `Dockerfile` del repositorio.

**Desde el móvil, usa el modo URL en vez de subir archivos.** Pegas el enlace
del vídeo y lo descarga el servidor, que va mucho más rápido que subir un
archivo grande por datos móviles.

**Sobre el plan:** montar vídeo consume CPU y memoria. El plan `starter` de
Render (512 MB) aguanta a 720p pero va lento; para 1080p cómodo necesitas
`standard` (2 GB). Cámbialo en `render.yaml` antes de desplegar. El plan
gratuito no admite disco persistente, así que perderías los proyectos en cada
reinicio.

### Contraseña de acceso

Si publicas la app en internet, **define `ACCESS_PASSWORD`**. Sin ella la API
queda abierta y cualquiera con la URL puede subir vídeos y gastar tus créditos.

Con la contraseña puesta, toda la API exige el token (por cabecera
`X-Access-Token` o por parámetro `?access_token=`, que es lo que necesitan las
etiquetas `<video>` y los eventos SSE). La interfaz muestra una pantalla de
acceso y recuerda la sesión en el navegador.

En local déjala vacía y no te pedirá nada.

## Configuración

Todo vive en `.env` y **todo es opcional**: sin ninguna clave la app arranca y
funciona, sólo que con menos calidad. Estos son los tres ejes:

### 1. Transcripción

| Opción | Coste por hora de vídeo | Calidad | Cómo |
|---|---|---|---|
| **Groq** (recomendado) | ~0,07 $ | muy alta | `GROQ_API_KEY=…` |
| **OpenAI** | ~0,36 $ | muy alta | `OPENAI_API_KEY=…` |
| **faster-whisper** | gratis | alta (lento en CPU) | `pip install faster-whisper` |
| **Subtítulos propios** | gratis | depende del `.srt` | súbelos en la interfaz |
| *(ninguna)* | gratis | baja: sin texto ni subtítulos | por defecto |

Sin transcripción los clips se eligen sólo por la energía del audio y salen sin
subtítulos. Funciona, pero es el modo degradado.

El audio se trocea en bloques de 9 minutos antes de enviarlo, así que no hay
límite práctico de duración por el tamaño del fichero.

### 2. Selección de momentos

Con `ANTHROPIC_API_KEY` Claude lee la transcripción y elige los fragmentos,
escribe títulos, ganchos, resúmenes, copys y hashtags. Cuesta unos pocos
céntimos por vídeo.

Sin clave entra la heurística, que puntúa cada ventana por:

| Señal | Qué mide |
|---|---|
| **Gancho** | si abre con pregunta, cifra o frase de apertura fuerte; penaliza empezar por "y entonces…" |
| **Emoción** | densidad de vocabulario emocional, superlativos y exclamaciones |
| **Claridad** | muletillas, frases interminables, arranques sin contexto |
| **Idea completa** | si empieza y acaba en frontera de frase, con pausas a ambos lados |
| **Energía de voz** | volumen y dinámica del audio en esa ventana frente al resto del vídeo |
| **Ritmo** | palabras por segundo y silencios internos |

Cuando hay clave, la nota final mezcla ambas: `LLM_WEIGHT` (0,65 por defecto)
controla cuánto pesa Claude. La heurística aporta señales objetivas —sobre todo
el audio— que el modelo no puede ver.

### 3. Voces de IA y silenciado (ElevenLabs)

Cada clip puede salir con el **audio original**, **silenciado** (pista muda,
para vídeos que sólo se ven con subtítulos) o con una **locución de IA** que
sustituye a la voz original.

El silenciado no necesita ninguna clave. La locución sí: pon `ELEVENLABS_API_KEY`
en el `.env`. Con ella puedes además:

- Elegir cualquier voz de tu cuenta de ElevenLabs desde la interfaz.
- **Crear una voz nueva describiéndola con texto** ("mujer joven española, tono
  cercano y enérgico, habla rápido"). La app genera varias propuestas, las
  escuchas y guardas la que prefieras, que queda disponible para los clips.
- Editar el texto que se locuta: por defecto lee la transcripción del clip,
  pero puedes escribir otro.
- Dejar el audio original de fondo a bajo volumen en vez de eliminarlo.

**Los subtítulos se resincronizan con la voz nueva.** ElevenLabs devuelve los
tiempos de cada carácter junto al audio; la app los agrupa en palabras y los usa
para los subtítulos, en lugar de arrastrar los tiempos del audio sustituido.

Si la locución es más corta que el clip, se rellena con silencio; si es más
larga, se recorta al final.

### 4. Detección de caras

`make models` descarga YuNet (230 KB). Sin él, el reencuadre cae a saliencia por
movimiento, que funciona razonablemente pero no distingue quién habla.

## Opciones por proyecto

| Ajuste | Opciones |
|---|---|
| **Nº de clips** | 1–30 |
| **Duración** | mínimo y máximo, en segundos |
| **Formato** | 9:16 · 4:5 · 1:1 · 16:9 |
| **Encuadre** | seguir al sujeto · fondo desenfocado · dividido |
| **Audio** | original · silenciado · locución de IA |
| **Voz** | cualquiera de tu cuenta de ElevenLabs, o una creada por ti |
| **Subtítulos** | palabra resaltada · karaoke · con caja · discreto · ninguno |
| **Resolución** | 720p · 1080p · 1440p |
| **Tema** | palabras clave que suben la nota de los clips que las contienen |
| **Idioma** | del audio (pista para el ASR) y de los textos generados |

Cada clip se puede remontar desde la ficha con otro encuadre, otro estilo de
subtítulos u otro formato, sin volver a analizar el vídeo.

## Arquitectura

```
frontend/                 React + TypeScript + Tailwind (Vite)
backend/
  viralclips/
    main.py               API HTTP + progreso por SSE
    worker.py             cola de trabajos y orquestación del pipeline
    db.py                 SQLite (sin ORM)
    pipeline/
      ingest.py           descarga/copia, sondeo, extracción de audio
      transcribe.py       Groq · OpenAI · faster-whisper · .srt/.vtt · energía
      segmentation.py     frases y ventanas candidatas
      scoring.py          heurística de viralidad
      analyze.py          selección con Claude + mezcla de notas
      metadata.py         títulos, copys y hashtags sin LLM
      voice.py            ElevenLabs: locución, tiempos y diseño de voces
      tracking.py         detección de caras, suavizado y paneo
      subtitles.py        generación de ASS con resaltado por palabra
      render.py           montaje final con ffmpeg
  tests/                  131 tests (17 renderizan vídeo real)
```

El backend es un único proceso: FastAPI sirve la API y el frontend compilado, y
una cola en memoria procesa los vídeos en hilos. No hace falta Redis ni Celery.

### Cómo se consigue el paneo suave

El seguimiento no se hace fotograma a fotograma en el render. Se extrae una
copia reducida del fragmento (320 px, 5 fps), se detectan caras en cada muestra,
se eligen por continuidad con la anterior, se suaviza la trayectoria con zona
muerta y límite de velocidad, y se simplifica con Ramer–Douglas–Peucker a unos
pocos puntos clave. Esos puntos se traducen en una expresión de `crop` con
interpolación lineal, de modo que ffmpeg hace un solo pase:

```
crop=w=608:h=1080:x='if(lt(t,1.500),(100.0+(133.3)*(t-0.000)),…)'
```

Los cambios de plano se detectan por diferencia entre fotogramas y reinician el
suavizado, para que la cámara salte en seco en el corte en lugar de barrer.

## API

| Método | Ruta | Para qué |
|---|---|---|
| `GET` | `/api/auth/status` | si el servidor exige contraseña (público) |
| `GET` | `/api/voices` | voces disponibles en ElevenLabs |
| `POST` | `/api/voices/design` | propuestas de voz desde una descripción |
| `POST` | `/api/voices` | guarda la voz elegida en tu cuenta |
| `GET` | `/api/capabilities` | qué proveedores hay configurados |
| `POST` | `/api/projects` | crear proyecto (`file` o `url`, `subtitles` opcional) |
| `GET` | `/api/projects` | lista de proyectos |
| `GET` | `/api/projects/{id}` | proyecto con sus clips |
| `GET` | `/api/projects/{id}/events` | progreso en vivo (SSE) |
| `POST` | `/api/projects/{id}/retry` | reintentar |
| `DELETE` | `/api/projects/{id}` | borrar proyecto y archivos |
| `GET` | `/api/projects/{id}/transcript` | transcripción completa |
| `PATCH` | `/api/clips/{id}` | editar título, copy, hashtags o recorte |
| `POST` | `/api/clips/{id}/rerender` | remontar con otros ajustes |
| `GET` | `/api/clips/{id}/video` | reproducir (soporta `Range`) |
| `GET` | `/api/clips/{id}/download` | descargar el MP4 |
| `GET` | `/api/clips/{id}/srt` | subtítulos del clip |

Documentación interactiva en `/docs`.

Ejemplo:

```bash
curl -X POST http://localhost:8000/api/projects \
  -F 'url=https://www.youtube.com/watch?v=...' \
  -F 'options={"clip_count":10,"min_duration":20,"max_duration":60,"layout":"fill"}'
```

## Tests

```bash
make test        # 114 tests, menos de un segundo
make test-slow   # 17 tests que renderizan vídeo con ffmpeg (~40 s)
```

Los lentos generan un vídeo sintético y comprueban que salen MP4 verticales
válidos con los tres encuadres, los cinco estilos de subtítulos y los cuatro
formatos; que el recorte sigue al sujeto cuando éste se mueve; y que el modo
silencio deja la pista a −91 dB mientras la locución sustituye de verdad al
audio original (se mide la frecuencia dominante para distinguirlos).

## Rendimiento

Medido en 4 vCPU, para una hora de vídeo:

| Etapa | Tiempo aproximado |
|---|---|
| Descarga/preparación | 1–3 min |
| Transcripción (Groq) | 1–2 min |
| Análisis | 10–40 s |
| Montaje | ~25 s por clip |

Sube `RENDER_CONCURRENCY` si tienes núcleos libres. Si tu máquina tiene GPU con
NVENC, cambiar `libx264` por `h264_nvenc` en `pipeline/render.py` acelera mucho
el montaje.

## Limitaciones conocidas

- **La integración de ElevenLabs no se ha probado contra el servicio real.** El
  cliente está escrito sobre la API documentada y cubierto con tests que simulan
  sus respuestas, pero no se ha ejecutado con una clave de verdad.
- **No separa hablantes.** En un plano con dos personas sigue a la cara más
  grande y cercana a la anterior; no cambia de encuadre según quién habla.
- **No reescribe el montaje.** Corta un fragmento continuo: no elimina silencios
  internos ni hace saltos de montaje dentro del clip.
- **La heurística es orientativa.** Sin Claude acierta en lo obvio (preguntas,
  cifras, historias) pero no entiende ironía ni contexto de la conversación.
- **Descargar vídeos de terceros** puede incumplir los términos de servicio de la
  plataforma. Usa material propio o con permiso.

## Licencia

MIT.
