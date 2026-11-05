"""Estilos de imagen (los "looks" de Soul) y plantillas de anuncio."""
from __future__ import annotations

from typing import Any


def _s(sid: str, name: str, group: str, prompt: str, *, badge: str | None = None) -> dict[str, Any]:
    return {"id": sid, "name": name, "group": group, "prompt": prompt, "badge": badge}


IMAGE_STYLES: list[dict[str, Any]] = [
    # --- Fotografía ---
    _s("general", "General", "foto", "fotografía nítida y bien expuesta"),
    _s("soul-realism", "Soul Realismo", "foto",
       "fotografía hiperrealista, piel con textura real, iluminación natural, 85mm f/1.4",
       badge="popular"),
    _s("film-35mm", "Película 35mm", "foto",
       "grano de película 35mm Kodak Portra, colores cálidos, halo suave"),
    _s("polaroid", "Polaroid", "foto",
       "instantánea polaroid con flash directo, bordes lavados y viñeteado"),
    _s("paparazzi", "Paparazzi", "foto",
       "foto de paparazzi con flash duro de noche, movimiento y sorpresa",
       badge="popular"),
    _s("cctv", "Cámara de seguridad", "foto",
       "imagen de CCTV en blanco y negro con marca de tiempo y ruido"),
    _s("studio-portrait", "Retrato de estudio", "foto",
       "retrato de estudio con luz de tres puntos y fondo gris"),
    _s("editorial", "Editorial de moda", "foto",
       "editorial de moda tipo Vogue, pose escultórica, luz dura controlada"),
    _s("street-photo", "Fotografía callejera", "foto",
       "fotografía callejera en blanco y negro, instante decisivo"),
    _s("golden-hour", "Hora dorada", "foto",
       "contraluz de hora dorada con destellos y polvo en el aire"),
    _s("analog-y2k", "Y2K", "foto",
       "estética Y2K de cámara digital de 2003, flash y fecha impresa"),
    _s("drone-top", "Vista de dron", "foto",
       "vista aérea de dron perfectamente cenital"),
    _s("underwater-photo", "Submarina", "foto",
       "fotografía submarina con luz filtrada y partículas"),
    _s("macro-photo", "Macro", "foto",
       "macrofotografía con profundidad de campo mínima y detalle extremo"),
    _s("long-exposure", "Larga exposición", "foto",
       "larga exposición con estelas de luz y agua sedosa"),

    # --- Cine ---
    _s("cinematic", "Cinematográfico", "cine",
       "fotograma de cine, color grading teal and orange, anamórfico", badge="popular"),
    _s("film-noir", "Cine negro", "cine",
       "cine negro en blanco y negro, claroscuro, humo y persianas"),
    _s("wes-anderson", "Simetría pastel", "cine",
       "composición perfectamente simétrica con paleta pastel y plano frontal"),
    _s("blockbuster", "Superproducción", "cine",
       "fotograma de superproducción con escala épica y luz volumétrica"),
    _s("horror-still", "Terror", "cine",
       "fotograma de terror, luz baja, contraste alto, textura sucia"),
    _s("documentary", "Documental", "cine",
       "estética documental, luz disponible, sin artificio"),

    # --- Ilustración ---
    _s("anime", "Anime", "ilustracion",
       "ilustración anime con líneas limpias y color plano vibrante"),
    _s("manga-bw", "Manga", "ilustracion",
       "manga en blanco y negro con tramas y líneas de velocidad"),
    _s("comic-usa", "Cómic americano", "ilustracion",
       "cómic americano con tinta gruesa y puntos de medio tono"),
    _s("pixar-3d", "3D animado", "ilustracion",
       "render 3D de película animada, materiales suaves y ojos expresivos"),
    _s("oil-painting", "Óleo", "ilustracion",
       "pintura al óleo con pincelada gruesa visible"),
    _s("watercolor", "Acuarela", "ilustracion",
       "acuarela con sangrados y papel texturado"),
    _s("pencil-sketch", "Lápiz", "ilustracion",
       "boceto a lápiz con sombreado cruzado"),
    _s("vector-flat", "Vectorial plano", "ilustracion",
       "ilustración vectorial plana con formas geométricas y paleta limitada"),
    _s("pixel-art", "Pixel art", "ilustracion",
       "pixel art de 32 bits con paleta reducida"),
    _s("claymation", "Plastilina", "ilustracion",
       "aspecto de animación en plastilina con huellas de dedos"),
    _s("papercut", "Papel recortado", "ilustracion",
       "collage de papel recortado por capas con sombras"),

    # --- Diseño / marca ---
    _s("product-studio", "Estudio de producto", "diseno",
       "packshot de producto sobre fondo infinito con luz suave", badge="popular"),
    _s("minimal-brand", "Marca minimalista", "diseno",
       "composición minimalista con mucho aire y tipografía limpia"),
    _s("luxury", "Lujo", "diseno",
       "estética de lujo con mármol, dorados y luz especular"),
    _s("brutalist", "Brutalista", "diseno",
       "diseño brutalista con hormigón, rejilla rígida y alto contraste"),
    _s("retro-print", "Impresión retro", "diseno",
       "cartel impreso retro con registro desplazado y papel amarillento"),
    _s("blueprint", "Plano técnico", "diseno",
       "plano técnico en azul con líneas blancas y cotas"),

    # --- Mundos ---
    _s("cyberpunk", "Ciberpunk", "mundos",
       "ciudad ciberpunk de neón, lluvia y hologramas", badge="popular"),
    _s("solarpunk", "Solarpunk", "mundos",
       "futuro verde solarpunk con vegetación y energía limpia"),
    _s("post-apocalyptic", "Postapocalíptico", "mundos",
       "mundo postapocalíptico polvoriento con ruinas oxidadas"),
    _s("fantasy-epic", "Fantasía épica", "mundos",
       "fantasía épica con arquitectura imposible y luz mágica"),
    _s("space-opera", "Ópera espacial", "mundos",
       "ópera espacial con naves gigantes y nebulosas"),
    _s("dreamcore", "Dreamcore", "mundos",
       "estética onírica dreamcore, espacios vacíos y luz irreal"),
    _s("vaporwave", "Vaporwave", "mundos",
       "vaporwave con rejilla rosa, estatuas y degradados"),
]

_BY_ID = {s["id"]: s for s in IMAGE_STYLES}

STYLE_GROUPS = [
    {"id": "foto", "name": "Fotografía"},
    {"id": "cine", "name": "Cine"},
    {"id": "ilustracion", "name": "Ilustración"},
    {"id": "diseno", "name": "Diseño"},
    {"id": "mundos", "name": "Mundos"},
]


def find_style(style_id: str) -> dict[str, Any] | None:
    return _BY_ID.get(style_id)


# ------------------------- Plantillas de anuncio -------------------------

AD_TEMPLATES: list[dict[str, Any]] = [
    {"id": "ugc-testimonial", "name": "Testimonio UGC", "format": "9:16", "duration": 15,
     "beats": ["gancho a cámara", "problema", "producto en mano", "resultado", "llamada a la acción"],
     "description": "Una persona real cuenta su experiencia. El formato que más convierte."},
    {"id": "problem-solution", "name": "Problema / solución", "format": "9:16", "duration": 15,
     "beats": ["problema exagerado", "transición", "producto", "alivio", "oferta"],
     "description": "Enseña el dolor y resuélvelo con el producto."},
    {"id": "unboxing", "name": "Unboxing", "format": "9:16", "duration": 20,
     "beats": ["paquete llegando", "apertura", "detalle del producto", "primer uso", "veredicto"],
     "description": "Abrir la caja despacio, con sonido y detalle."},
    {"id": "three-reasons", "name": "Tres razones", "format": "9:16", "duration": 20,
     "beats": ["gancho numérico", "razón 1", "razón 2", "razón 3", "cierre"],
     "description": "Lista rápida con rótulos. Muy fácil de retener."},
    {"id": "before-after", "name": "Antes y después", "format": "9:16", "duration": 10,
     "beats": ["antes", "barrido", "después", "prueba", "oferta"],
     "description": "La transformación en el menor tiempo posible."},
    {"id": "product-hero", "name": "Hero de producto", "format": "16:9", "duration": 10,
     "beats": ["revelación", "giro 360", "detalle macro", "logotipo"],
     "description": "Packshot de estudio sin personas, para cabecera web."},
    {"id": "lifestyle", "name": "Lifestyle", "format": "9:16", "duration": 15,
     "beats": ["escena cotidiana", "producto integrado", "momento de disfrute", "marca"],
     "description": "El producto dentro de una vida que apetece."},
    {"id": "street-interview", "name": "Entrevista en la calle", "format": "9:16", "duration": 20,
     "beats": ["pregunta", "reacción", "prueba del producto", "sorpresa", "cierre"],
     "description": "Micrófono en mano, reacciones espontáneas."},
    {"id": "asmr-product", "name": "ASMR de producto", "format": "9:16", "duration": 15,
     "beats": ["sonido de apertura", "textura", "aplicación", "resultado"],
     "description": "Sonido muy cerca y texturas. Funciona sin voz."},
    {"id": "founder-story", "name": "Historia del fundador", "format": "9:16", "duration": 30,
     "beats": ["por qué lo creé", "el problema", "el proceso", "el producto", "invitación"],
     "description": "Credibilidad y marca. Vende sin parecer anuncio."},
]

AVATAR_PRESETS: list[dict[str, Any]] = [
    {"id": "podcast-host", "name": "Presentadora de podcast", "prompt":
     "mujer de 30 años en un estudio de podcast con micrófono de brazo, luz cálida"},
    {"id": "news-anchor", "name": "Presentador de informativos", "prompt":
     "presentador trajeado en un plató de noticias con pantalla detrás"},
    {"id": "fitness-coach", "name": "Entrenador personal", "prompt":
     "entrenador en un gimnasio moderno con ropa técnica, luz de ventanal"},
    {"id": "finance-bro", "name": "Analista financiero", "prompt":
     "analista con camisa en una oficina acristalada con gráficos de bolsa"},
    {"id": "beauty-creator", "name": "Creadora de belleza", "prompt":
     "creadora de belleza frente a un aro de luz con fondo rosa suave"},
    {"id": "teacher", "name": "Profesora", "prompt":
     "profesora junto a una pizarra con luz natural de aula"},
    {"id": "chef", "name": "Chef", "prompt":
     "chef con chaquetilla en una cocina profesional de acero"},
    {"id": "gamer", "name": "Streamer", "prompt":
     "streamer con auriculares y luces RGB en su setup nocturno"},
    {"id": "doctor", "name": "Profesional sanitario", "prompt":
     "profesional sanitario con bata blanca en una consulta luminosa"},
    {"id": "travel-vlogger", "name": "Vlogger de viajes", "prompt":
     "vlogger con mochila en un mirador al atardecer, viento en el pelo"},
]
