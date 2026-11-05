# HiggsStudio

Un estudio de generación de vídeo e imagen con IA, autoalojado: presets de
cámara, personajes consistentes, avatares que hablan, estudio de anuncios,
herramientas de posproducción, galería, créditos y API. Es una alternativa
abierta a Higgsfield: tú pones las claves de los modelos y todo corre en tu
máquina.

![pipeline](https://img.shields.io/badge/flujo-prompt%20→%20preset%20→%20cola%20→%20biblioteca-C8FF4D)

> **Funciona sin ninguna clave.** Si no configuras ningún proveedor, la app
> arranca en **modo demostración** y genera el material en local con ffmpeg.
> No son modelos de difusión: son fotogramas procedimentales con el
> movimiento de cámara del preset aplicado de verdad. Sirve para probar el
> producto entero, enseñarlo y desarrollar sin gastar un céntimo. En cuanto
> añades una clave, esa parte pasa a usar modelos reales sin tocar nada más.

---

## Qué sabe hacer

### Generar

| Qué | Modos |
|---|---|
| **Vídeo** | texto→vídeo, imagen→vídeo, primer/último fotograma, transferencia de movimiento, efectos |
| **Imagen** | texto→imagen, imagen→imagen, edición por instrucciones, con personaje (Soul ID) |
| **Hablar** | foto que habla (avatar + voz) y sincronización de labios sobre un vídeo |
| **Audio** | locución, música, efectos de sonido, sonido para un vídeo mudo, doblaje, cambio de voz |

- **141 presets** de cámara y efectos en 14 categorías: *crash zoom*, órbita
  360º, bullet time, dron FPV, vértigo, snorricam, derretir, desintegrar,
  glitch, pasarela, unboxing, found footage… Cada preset fija el movimiento,
  enriquece el prompt y sugiere duración y formato.
- **46 modelos** en el catálogo: para vídeo, Kling 2.5 Turbo y 3.0, Seedance
  2.5, Wan 3.0, Veo 3.1, Hailuo H3, FLUX 3, Grok Imagine, PixVerse V6 y
  Gemini Omni; para imagen, Soul, Nano Banana, Seedream, FLUX, Ideogram y
  Qwen; más voz, lipsync y herramientas. Cada uno con sus modos,
  resoluciones, duraciones, **precio real por segundo** y coste en créditos.
  El modelo por defecto es el más barato de la lista.
- **45 estilos** de imagen agrupados en fotografía, cine, ilustración, diseño
  y mundos.
- Generación **en lote**: cruza prompts × presets × semillas en una tanda.
- **Mejora de prompts** y variaciones (con Claude si hay clave; si no, con
  heurísticas de fotografía).

### Personajes y marca

- **Soul ID**: sube de 4 a 20 fotos, entrena y reutiliza la misma cara.
- **Influencers de IA**: ficha de personaje coherente y hoja de poses.
- **Marcas y productos**: tono, paleta, logotipo y fichas de producto.
- **Estudio de anuncios**: eliges plantilla (testimonio UGC, problema/solución,
  unboxing, tres razones, antes y después…), se escribe el guion por planos,
  se ruedan los planos y se montan con transición. Todo en un solo trabajo.

### Posproducción

Upscale de vídeo e imagen, interpolado y cámara lenta, reencuadre siguiendo
el formato, expansión de lienzo, recorte de fondo, extensión de planos,
montaje de tomas con transiciones y música, y conversión de imagen a malla 3D.

### Alrededor

- **Biblioteca** con filtros, favoritos, colecciones, búsqueda por prompt y
  descarga directa.
- **Proyectos** que agrupan tomas, con lienzo y línea de tiempo guardados.
- **Galería de la comunidad**: publicar, me gusta, comentar y **remezclar**
  (recupera prompt, modelo, preset y formato de cualquier publicación).
- **Predictor de viralidad**: puntúa gancho, ritmo, retención y claridad, y
  dice en qué red encaja mejor. Es una heurística explicada, no magia.
- **Créditos y planes** con presupuesto antes de generar y devolución
  automática si algo falla.
- **API con claves propias** (`Authorization: Bearer hs_…`) y **webhooks**
  firmados con HMAC-SHA256.
- **Progreso en vivo** por SSE en cada trabajo y en toda la cuenta.

---

## Puesta en marcha

Necesitas **ffmpeg**, **Python 3.11+** y **Node 20+**.

```bash
# ffmpeg
sudo apt install ffmpeg      # Debian/Ubuntu
brew install ffmpeg          # macOS

cd higgsstudio
cp .env.example .env         # opcional: todo funciona sin tocarlo
make install
make run                     # http://localhost:8000
```

Al arrancar, el servidor imprime las direcciones:

```
  Vídeo:  local
  Imagen: local
  Audio:  local
  Modo demostración: se genera en local con ffmpeg.

  Abre la app en:  http://localhost:8000
  Desde el móvil (misma wifi):  http://192.168.1.42:8000
```

La segunda sirve para **abrirla desde el móvil** sin desplegar nada: el
teléfono y el ordenador tienen que estar en la misma red. Si no conecta, suele
ser el cortafuegos bloqueando el puerto 8000.

Para desarrollar, con recarga en caliente, en dos terminales:

```bash
make dev-api   # API en :8000
make dev-ui    # interfaz en :5173
```

Con Docker, sin instalar nada:

```bash
cp .env.example .env
docker compose up --build    # http://localhost:8000
```

### En Windows

El `Makefile` usa rutas de Unix. Usa Docker Desktop (requiere WSL2, que su
instalador configura):

```powershell
cd higgsstudio
Copy-Item .env.example .env
notepad .env
docker compose up --build
```

---

## Conectar modelos reales

Todas las claves son opcionales y van en `.env`. Cada una enciende una parte:

| Clave | Para qué | Dónde se saca |
|---|---|---|
| `FAL_API_KEY` | Vídeo e imagen (el catálogo más completo) | [fal.ai](https://fal.ai/dashboard/keys) |
| `REPLICATE_API_TOKEN` | Alternativa para vídeo e imagen | [replicate.com](https://replicate.com/account/api-tokens) |
| `OPENAI_API_KEY` | Imagen con gpt-image | [platform.openai.com](https://platform.openai.com/api-keys) |
| `ELEVENLABS_API_KEY` | Voz, música, efectos, doblaje y clonado | [elevenlabs.io](https://elevenlabs.io/app/settings/api-keys) |
| `ANTHROPIC_API_KEY` | Mejora de prompts y guiones de anuncios | [console.anthropic.com](https://console.anthropic.com/) |

El selector es automático: con `VIDEO_PROVIDER=auto` se usa fal si hay clave,
si no Replicate, y si no el motor local. Puedes forzarlo poniendo
`VIDEO_PROVIDER=replicate`, etc.

**Lo que cuesta un vídeo de verdad** (precios de fal, noviembre de 2026; la
ficha de cada modelo manda):

| Modelo | $/segundo | Un plano de 5 s |
|---|---|---|
| Kling 2.5 Turbo | 0,07 | ~0,35 $ |
| Kling 3.0 Standard | 0,084 | ~0,42 $ |
| Kling 3.0 Pro | ~0,12 | ~0,60 $ |
| Seedance 2.5 (con audio) | ~0,30 | ~1,50 $ |
| Veo 3.1 (con audio) | 0,40 | ~2,00 $ |

La app enseña el coste en créditos antes de generar, y 1 crédito ≈ 0,01 $ con
`CREDIT_MULTIPLIER=1.0`.

Algunas cosas **siempre** se hacen en local porque salen igual de bien, más
rápido y gratis: montar tomas, reencuadrar y extender planos.

> **Aviso importante sobre el catálogo de modelos.** Los endpoints se leyeron
> de las páginas de fal en noviembre de 2026 y **caducan rápido**: Sora 2 se
> retiró en septiembre de 2026, Kling pasó de 2.5 a 3.0 y 4.0 en unos meses, y
> Veo cambia de ruta cada poco. Dos salvaguardas:
>
> 1. Cada modelo mapea **un endpoint por modo**, porque en fal texto→vídeo e
>    imagen→vídeo son rutas distintas:
>    `"providers": {"fal": {"t2v": "...", "i2v": "..."}}`.
> 2. Puedes repuntar cualquier endpoint **sin tocar código**, con
>    `MODEL_ENDPOINTS` en el `.env`:
>    `MODEL_ENDPOINTS={"kling-3-pro":{"fal":{"t2v":"fal-ai/kling-video/v4/text-to-video"}}}`
>
> Si un modelo devuelve 404, está retirado o renombrado: mira el catálogo vivo
> en fal.ai/models y repúntalo. Si devuelve 422, el endpoint existe pero espera
> otros campos: pásale `extra.provider_input` con lo que pida su ficha.
> Los endpoints de **imagen** no se han verificado contra el catálogo actual;
> los de vídeo y lipsync sí.

---

## Si lo publicas en internet

La app gasta **tus** claves de proveedor. Antes de dejarla accesible:

1. `ALLOW_SIGNUP=false`, o pon un `INVITE_CODE`.
2. Define `BOOTSTRAP_EMAIL` y `BOOTSTRAP_PASSWORD` para crear tu cuenta de
   administración al arrancar con la base vacía.
3. Revisa `CREDIT_MULTIPLIER` si quieres que cada generación cueste más.
4. **No hay pasarela de pago.** Cambiar de plan o «comprar» créditos ajusta
   límites y suma saldo al momento. Conecta un cobro real (Stripe o lo que
   uses) en `api/billing.py` antes de abrirlo a desconocidos.

Hay un `render.yaml` listo para desplegar en Render con disco persistente.

---

## Cómo está hecho

```
higgsstudio/
├── backend/higgsstudio/
│   ├── main.py            app FastAPI, arranque y servido de la interfaz
│   ├── config.py          ajustes y detección de capacidades
│   ├── db.py              SQLite sin ORM (20 tablas)
│   ├── security.py        cuentas, sesiones y claves de API
│   ├── credits.py         presupuesto, cobro, devolución y límites de plan
│   ├── worker.py          cola de trabajos en hilos, cancelar y reintentar
│   ├── events.py          bus de eventos para el progreso por SSE
│   ├── catalog/           modelos, presets, estilos, planes y voces
│   ├── providers/         local (ffmpeg), fal, replicate, elevenlabs, openai
│   ├── pipeline/          ejecución, biblioteca, prompts y análisis
│   └── api/               13 routers REST
└── frontend/src/
    ├── pages/             explorar, crear, efectos, herramientas, biblioteca,
    │                      proyectos, personajes, anuncios, voces, trabajos,
    │                      créditos y ajustes
    ├── components/        interfaz, selectores y visor de material
    └── lib/               cliente de la API y sesión con SSE
```

**Decisiones que conviene conocer:**

- **SQLite y cola en proceso**, no Postgres ni Celery. Una máquina basta para
  esto y se instala en un comando. La frontera está dibujada en
  `worker.enqueue` / `worker.claim_next` por si algún día hace falta escalar.
- **Se cobra al encolar y se devuelve al fallar o cancelar**, como en
  Higgsfield. Nunca se cobra un resultado que no existe.
- **Los trabajos a medias vuelven a la cola** al reiniciar el servidor.
- **La misma semilla da el mismo resultado**: todas las fuentes aleatorias del
  motor local están sembradas (hay un test que lo comprueba comparando
  fotogramas).
- **El plan gratuito marca el material con agua**; los de pago no.

### El motor local, en concreto

`providers/local.py` sintetiza cada fotograma con tres capas (un degradado
modulado por ondas, una textura fractal y una luz principal), le añade grano,
viñeteado y los rótulos, y después aplica el movimiento de cámara del preset
con `zoompan`, `rotate` y `tblend`. Los 39 movimientos del catálogo están
implementados de verdad: un *crash zoom* acelera, una órbita rodea, un
*whip pan* arrastra.

Lo que el motor local **no** hace, y lo dice claramente en vez de fingirlo:
imagen a 3D (necesita un modelo). El recorte de fondo es un *matte* aproximado
por croma, no una segmentación; con clave de proveedor se usa la buena.

---

## Tests

```bash
make test        # 80 tests, ~2,5 min (generan vídeo de verdad con ffmpeg)
```

Cubren el catálogo, los créditos y los límites de plan, la API y los permisos
entre cuentas, la generación de punta a punta de cada tipo, las herramientas,
los trabajos compuestos (anuncio y hoja de personaje), la cola (cancelar,
reintentar, devoluciones, recuperación), la selección de proveedor y la
traducción de parámetros, y la galería.

---

## API

Crea una clave en **Ajustes → API** y úsala como `Bearer`:

```bash
# Presupuestar
curl -X POST http://localhost:8000/api/generate/quote \
  -H "Authorization: Bearer hs_..." -H "Content-Type: application/json" \
  -d '{"type":"video","model":"higgs-dop-turbo","duration":5,"resolution":"720p"}'

# Generar
curl -X POST http://localhost:8000/api/generate/video \
  -H "Authorization: Bearer hs_..." -H "Content-Type: application/json" \
  -d '{"model":"higgs-dop-turbo","prompt":"un coche derrapando bajo la lluvia",
       "preset":"crash-zoom-in","aspect":"9:16","duration":5}'

# Seguir el progreso
curl -N http://localhost:8000/api/jobs/job_xxx/stream -H "Authorization: Bearer hs_..."
```

La documentación interactiva está en `/docs`.

---

## Licencia y uso responsable

El código es tuyo para lo que quieras. Dos cosas que no son negociables:

- **Clona solo voces y caras sobre las que tengas permiso.** La app no puede
  comprobarlo por ti.
- **Si publicas material generado, dilo.** Un vídeo sintético que se presenta
  como real es un problema, por bonito que haya quedado.
