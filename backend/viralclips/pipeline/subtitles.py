"""Generación de subtítulos ASS con resaltado palabra a palabra."""
from __future__ import annotations

from dataclasses import dataclass

from ..models import CaptionStyle, Word

# Agrupación de palabras en líneas legibles en vertical.
MAX_WORDS_PER_LINE = 4
MAX_CHARS_PER_LINE = 20
MAX_LINE_SECONDS = 2.6
LINE_GAP = 0.6          # una pausa mayor fuerza cambio de línea
TERMINALS = ".!?…"
HARD_WORD_CAP = 6       # tope absoluto aunque haya que arrastrar una palabra

# Cortar la línea justo detrás de una de estas deja el texto colgando.
DANGLING = {
    # español
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "a", "en", "con", "por", "para", "que", "y", "o", "su", "sus", "mi", "tu",
    "lo", "le", "les", "se", "es", "como", "más", "muy", "este", "esta", "mis",
    # inglés
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "with", "and", "or",
    "that", "this", "my", "your", "his", "her", "its", "is", "as", "very",
}


@dataclass
class CaptionGroup:
    words: list[Word]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class StyleSpec:
    font: str = "Inter Display"
    size_ratio: float = 0.050      # respecto a la altura del vídeo
    primary: str = "&H00FFFFFF"    # blanco (formato ASS: &HAABBGGRR)
    highlight: str = "&H0000F5FF"  # amarillo
    outline_colour: str = "&H00000000"
    back_colour: str = "&HA0000000"
    outline: float = 0.075         # respecto al tamaño de fuente
    shadow: float = 0.03
    border_style: int = 1          # 1 contorno, 3 caja opaca
    bold: int = -1
    uppercase: bool = True
    margin_v_ratio: float = 0.20   # desde abajo
    emphasise: bool = True         # agranda la palabra activa


STYLES: dict[CaptionStyle, StyleSpec] = {
    CaptionStyle.POP: StyleSpec(),
    CaptionStyle.KARAOKE: StyleSpec(
        highlight="&H0066FF00", size_ratio=0.048, emphasise=False
    ),
    CaptionStyle.BOXED: StyleSpec(
        border_style=3, outline=0.035, shadow=0.0,
        back_colour="&HD0000000", highlight="&H004BC8FF", size_ratio=0.044,
    ),
    CaptionStyle.MINIMAL: StyleSpec(
        size_ratio=0.034, uppercase=False, emphasise=False,
        highlight="&H00FFFFFF", outline=0.05, margin_v_ratio=0.12, bold=0,
    ),
}


def group_words(words: list[Word]) -> list[CaptionGroup]:
    """Agrupa palabras en líneas cortas respetando pausas y puntuación."""
    groups: list[CaptionGroup] = []
    current: list[Word] = []

    for i, word in enumerate(words):
        if not word.text.strip():
            continue
        current.append(word)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = (nxt.start - word.end) if nxt else 99.0
        chars = len(" ".join(w.text for w in current))
        span = word.end - current[0].start
        terminal = word.text.rstrip('"\'»)]}').endswith(tuple(TERMINALS))

        hit_limit = (
            len(current) >= MAX_WORDS_PER_LINE
            or chars >= MAX_CHARS_PER_LINE
            or span >= MAX_LINE_SECONDS
        )
        # Si el corte viene sólo por longitud y la última palabra es un enlace,
        # arrastramos una palabra más para no dejar la línea coja.
        if (
            hit_limit
            and nxt is not None
            and not terminal
            and pause < LINE_GAP
            and len(current) < HARD_WORD_CAP
            and word.text.strip(".,;:!?¿¡").lower() in DANGLING
        ):
            hit_limit = False

        if nxt is None or terminal or pause >= LINE_GAP or hit_limit:
            groups.append(CaptionGroup(list(current)))
            current = []

    if current:
        groups.append(CaptionGroup(current))
    return groups


def _ts(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(
    words: list[Word],
    *,
    style: CaptionStyle,
    width: int,
    height: int,
    clip_start: float,
    clip_end: float,
    hook: str | None = None,
    hook_seconds: float = 2.4,
    font: str | None = None,
) -> str:
    """Devuelve el contenido de un fichero .ass con los tiempos del clip."""
    spec = STYLES.get(style, STYLES[CaptionStyle.POP])
    font_name = font or spec.font

    # En karaoke el barrido va de SecondaryColour a PrimaryColour, así que el
    # color de resalte debe ser el primario para que marque lo ya pronunciado.
    if style == CaptionStyle.KARAOKE:
        primary, secondary = spec.highlight, spec.primary
    else:
        primary, secondary = spec.primary, spec.highlight

    font_size = max(int(height * spec.size_ratio), 16)
    margin_v = int(height * spec.margin_v_ratio)
    side_margin = int(width * 0.075)
    outline = round(font_size * spec.outline, 1)
    shadow = round(font_size * spec.shadow, 1)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font_name},{font_size},{primary},{secondary},{spec.outline_colour},{spec.back_colour},{spec.bold},0,0,0,100,100,0,0,{spec.border_style},{outline},{shadow},2,{side_margin},{side_margin},{margin_v},1
Style: Hook,{font_name},{int(font_size * 1.08)},&H00FFFFFF,&H000000FF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,3,{round(font_size * 0.05, 1)},0,8,{side_margin},{side_margin},{int(height * 0.12)},1

[Events]
Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []

    if hook:
        text = _escape(hook.upper() if spec.uppercase else hook)
        events.append(
            f"Dialogue: 1,{_ts(0.15)},{_ts(hook_seconds)},Hook,,,,,"
            f"{{\\fad(220,220)}}{text}"
        )

    if style != CaptionStyle.NONE:
        window = [
            Word(w.text, w.start - clip_start, w.end - clip_start)
            for w in words
            if w.end > clip_start and w.start < clip_end and w.text.strip()
        ]
        for group in group_words(window):
            events.extend(_group_events(group, spec, style, clip_end - clip_start))

    return header + "\n".join(events) + "\n"


def _group_events(
    group: CaptionGroup,
    spec: StyleSpec,
    style: CaptionStyle,
    clip_duration: float,
) -> list[str]:
    tokens = [
        (w.text.upper() if spec.uppercase else w.text) for w in group.words
    ]

    if style == CaptionStyle.KARAOKE:
        parts = []
        for word, token in zip(group.words, tokens):
            cs = max(int(round((word.end - word.start) * 100)), 1)
            parts.append(f"{{\\kf{cs}}}{_escape(token)}")
        start = max(group.start, 0.0)
        end = min(group.end + 0.08, clip_duration)
        return [f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,,,,{' '.join(parts)}"]

    if style == CaptionStyle.MINIMAL:
        start = max(group.start - 0.05, 0.0)
        end = min(group.end + 0.12, clip_duration)
        text = _escape(" ".join(tokens))
        return [f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,,,,{text}"]

    # pop / boxed: una línea por palabra activa, con la palabra resaltada.
    events: list[str] = []
    emph = r"\fscx108\fscy108" if spec.emphasise else ""
    for i, word in enumerate(group.words):
        start = max(word.start, 0.0)
        end = min(
            group.words[i + 1].start if i + 1 < len(group.words) else word.end + 0.14,
            clip_duration,
        )
        if end <= start:
            continue
        rendered = []
        for j, token in enumerate(tokens):
            safe = _escape(token)
            if j == i:
                rendered.append(f"{{\\c{spec.highlight}{emph}}}{safe}{{\\r}}")
            else:
                rendered.append(safe)
        events.append(
            f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,,,,{' '.join(rendered)}"
        )
    return events
