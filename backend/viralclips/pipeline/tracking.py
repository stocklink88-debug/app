"""Reencuadre inteligente: sigue al sujeto para pasar de 16:9 a 9:16.

Estrategia:
 1. Se extrae una versión reducida del fragmento (320 px, 5 fps) con ffmpeg.
 2. Se detectan caras con YuNet (ONNX, ~230 KB) en cada muestra.
 3. Si no hay caras, se usa el centroide del movimiento como punto de interés.
 4. Se detectan cortes de plano para no hacer barridos imposibles entre escenas.
 5. La trayectoria se suaviza (zona muerta + límite de velocidad) y se reduce a
    unos pocos puntos clave que se traducen en una expresión de `crop`.
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .ffmpeg import run_ffmpeg

log = logging.getLogger(__name__)

SAMPLE_FPS = 5.0
SAMPLE_WIDTH = 320
DETECT_SCORE = 0.55
SCENE_CUT_THRESHOLD = 0.34     # diferencia media normalizada entre fotogramas
DEADZONE_RATIO = 0.035         # % del ancho que puede moverse el sujeto sin mover la cámara
MAX_SPEED_RATIO = 0.22         # desplazamiento máximo por segundo (% del ancho)
EMA_ALPHA = 0.18
MAX_KEYFRAMES = 60


@dataclass
class Track:
    """Trayectoria horizontal (y vertical) del encuadre, en píxeles de origen."""
    keyframes_x: list[tuple[float, float]]   # (t relativo al clip, x del recorte)
    keyframes_y: list[tuple[float, float]]
    crop_w: int
    crop_h: int
    source_w: int
    source_h: int
    found_subject: bool
    samples: int = 0

    @property
    def is_static(self) -> bool:
        return len(self.keyframes_x) <= 1


_detector = None
_detector_path: str | None = None


def _get_detector(model_path: Path):
    """Carga YuNet una sola vez por proceso."""
    global _detector, _detector_path
    if not model_path.exists():
        return None
    if _detector is not None and _detector_path == str(model_path):
        return _detector
    try:
        import cv2

        _detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (SAMPLE_WIDTH, SAMPLE_WIDTH), DETECT_SCORE, 0.3, 500
        )
        _detector_path = str(model_path)
        return _detector
    except Exception as exc:  # pragma: no cover
        log.warning("No se pudo cargar el detector de caras: %s", exc)
        return None


def _sample_frames(src: Path, start: float, duration: float, work_dir: Path) -> list["np.ndarray"]:
    """Extrae el fragmento reducido y devuelve sus fotogramas."""
    import cv2

    tmp = work_dir / f"probe_{int(start * 1000)}.mp4"
    run_ffmpeg([
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src),
        "-an", "-vf", f"fps={SAMPLE_FPS},scale={SAMPLE_WIDTH}:-2:flags=fast_bilinear",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
        "-pix_fmt", "yuv420p", str(tmp),
    ])

    frames: list[np.ndarray] = []
    cap = cv2.VideoCapture(str(tmp))
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(frame)
    finally:
        cap.release()
        tmp.unlink(missing_ok=True)
    return frames


def _detect_faces(detector, frame: "np.ndarray") -> list[tuple[float, float, float, float]]:
    """Devuelve [(cx, cy, área, confianza)] en coordenadas de la muestra."""
    h, w = frame.shape[:2]
    try:
        detector.setInputSize((w, h))
        _, faces = detector.detect(frame)
    except Exception:
        return []
    if faces is None:
        return []
    out = []
    for f in faces:
        x, y, fw, fh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
        conf = float(f[14]) if len(f) > 14 else 1.0
        if fw <= 1 or fh <= 1:
            continue
        out.append((x + fw / 2, y + fh / 2, fw * fh, conf))
    return out


def _motion_centroid(prev: "np.ndarray", frame: "np.ndarray") -> tuple[float, float] | None:
    """Centro de masa del movimiento: sirve cuando no hay caras visibles."""
    import cv2

    a = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(a, b).astype(np.float32)
    if diff.max() < 8:
        return None
    cols = diff.sum(axis=0)
    rows = diff.sum(axis=1)
    if cols.sum() <= 0:
        return None
    xs = np.arange(len(cols), dtype=np.float32)
    ys = np.arange(len(rows), dtype=np.float32)
    return float((cols * xs).sum() / cols.sum()), float((rows * ys).sum() / rows.sum())


def _scene_change(prev: "np.ndarray", frame: "np.ndarray") -> float:
    import cv2

    a = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.absdiff(a, b).mean() / 255.0)


def compute_track(
    src: Path,
    *,
    start: float,
    duration: float,
    source_w: int,
    source_h: int,
    target_ratio: float,
    model_path: Path,
    work_dir: Path | None = None,
) -> Track:
    """Calcula la trayectoria de recorte para un fragmento."""
    crop_w, crop_h = crop_size(source_w, source_h, target_ratio)

    # Si el vídeo ya es más estrecho que el destino, no hay nada que seguir.
    if crop_w >= source_w and crop_h >= source_h:
        return Track([], [], crop_w, crop_h, source_w, source_h, False, 0)

    work = Path(work_dir or tempfile.gettempdir())
    work.mkdir(parents=True, exist_ok=True)

    try:
        frames = _sample_frames(src, start, duration, work)
    except Exception as exc:
        log.warning("No se pudo muestrear el fragmento para seguimiento: %s", exc)
        frames = []

    if not frames:
        return _static_track(crop_w, crop_h, source_w, source_h)

    detector = _get_detector(model_path)
    sample_w = frames[0].shape[1]
    scale = source_w / sample_w

    raw: list[tuple[float, float | None, float | None, bool]] = []  # (t, cx, cy, cut)
    prev = None
    last_center: tuple[float, float] | None = None
    found_any = False

    for i, frame in enumerate(frames):
        t = i / SAMPLE_FPS
        cut = False
        if prev is not None and _scene_change(prev, frame) > SCENE_CUT_THRESHOLD:
            cut = True
            last_center = None

        cx = cy = None
        faces = _detect_faces(detector, frame) if detector is not None else []
        if faces:
            found_any = True
            if last_center is None:
                best = max(faces, key=lambda f: f[2])
            else:
                # Continuidad: preferimos la cara grande más cercana a la anterior.
                def key(f):
                    dist = abs(f[0] - last_center[0]) / sample_w
                    return f[2] / (1.0 + dist * 6.0)

                best = max(faces, key=key)
            cx, cy = best[0], best[1]
            last_center = (cx, cy)
        elif prev is not None:
            motion = _motion_centroid(prev, frame)
            if motion:
                cx, cy = motion

        raw.append((t, cx, cy, cut))
        prev = frame

    if not any(r[1] is not None for r in raw):
        return _static_track(crop_w, crop_h, source_w, source_h)

    xs = _smooth(
        [(t, cx, cut) for t, cx, _, cut in raw],
        width=sample_w, default=sample_w / 2,
    )
    ys = _smooth(
        [(t, cy, cut) for t, _, cy, cut in raw],
        width=frames[0].shape[0], default=frames[0].shape[0] / 2,
    )

    # Pasamos de "centro del sujeto" a "esquina del recorte", en píxeles de origen.
    kf_x = [
        (t, _clamp(cx * scale - crop_w / 2, 0.0, max(source_w - crop_w, 0)))
        for t, cx in xs
    ]
    scale_y = source_h / frames[0].shape[0]
    # Encuadramos la cara algo por encima del centro: queda más natural.
    kf_y = [
        (t, _clamp(cy * scale_y - crop_h * 0.42, 0.0, max(source_h - crop_h, 0)))
        for t, cy in ys
    ]

    kf_x = _simplify(kf_x, tolerance=max(source_w * 0.004, 1.5))
    kf_y = _simplify(kf_y, tolerance=max(source_h * 0.006, 1.5))

    return Track(
        keyframes_x=kf_x,
        keyframes_y=kf_y,
        crop_w=crop_w,
        crop_h=crop_h,
        source_w=source_w,
        source_h=source_h,
        found_subject=found_any,
        samples=len(frames),
    )


def _static_track(crop_w: int, crop_h: int, source_w: int, source_h: int) -> Track:
    return Track(
        keyframes_x=[(0.0, max((source_w - crop_w) / 2, 0.0))],
        keyframes_y=[(0.0, max((source_h - crop_h) / 2, 0.0))],
        crop_w=crop_w, crop_h=crop_h, source_w=source_w, source_h=source_h,
        found_subject=False,
    )


def _smooth(
    series: list[tuple[float, float | None, bool]],
    *,
    width: float,
    default: float,
) -> list[tuple[float, float]]:
    """Rellena huecos, aplica zona muerta, EMA y límite de velocidad."""
    deadzone = width * DEADZONE_RATIO
    max_step_per_s = width * MAX_SPEED_RATIO

    # 1) Relleno de huecos: hacia delante con el último valor conocido y hacia
    #    atrás para las muestras iniciales sin detección.
    filled: list[float | None] = []
    last: float | None = None
    for _, value, _ in series:
        if value is not None:
            last = value
        filled.append(last)

    nxt = default
    for i in range(len(filled) - 1, -1, -1):
        if filled[i] is None:
            filled[i] = nxt
        else:
            nxt = filled[i]

    # 2) Objetivo con zona muerta: la cámara sólo reacciona a desplazamientos reales.
    target: list[float] = []
    anchor = filled[0]
    for value in filled:
        if abs(value - anchor) > deadzone:
            anchor = value
        target.append(anchor)

    # 3) EMA + límite de velocidad, reiniciando en los cortes de plano.
    out: list[tuple[float, float]] = []
    current = target[0]
    prev_t = series[0][0]
    for (t, _, cut), goal in zip(series, target):
        dt = max(t - prev_t, 1e-3)
        if cut:
            current = goal  # salto instantáneo: estamos en otro plano
        else:
            current += (goal - current) * EMA_ALPHA
            limit = max_step_per_s * dt
            delta = current - out[-1][1] if out else 0.0
            if abs(delta) > limit and out:
                current = out[-1][1] + limit * (1 if delta > 0 else -1)
        out.append((t, current))
        prev_t = t
    return out


def _simplify(points: list[tuple[float, float]], *, tolerance: float) -> list[tuple[float, float]]:
    """Reduce la trayectoria a pocos puntos (Ramer-Douglas-Peucker)."""
    if len(points) <= 2:
        return points

    keep = _rdp(points, tolerance)
    if len(keep) > MAX_KEYFRAMES:
        step = len(keep) / MAX_KEYFRAMES
        keep = [keep[int(i * step)] for i in range(MAX_KEYFRAMES)]
        if keep[-1] != points[-1]:
            keep.append(points[-1])
    return keep


def _rdp(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denom = (dx * dx + dy * dy) ** 0.5 or 1.0

    worst_idx, worst = 0, 0.0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        dist = abs(dy * px - dx * py + end[0] * start[1] - end[1] * start[0]) / denom
        if dist > worst:
            worst_idx, worst = i, dist

    if worst <= tolerance:
        return [start, end]
    left = _rdp(points[: worst_idx + 1], tolerance)
    right = _rdp(points[worst_idx:], tolerance)
    return left[:-1] + right


def crop_size(source_w: int, source_h: int, target_ratio: float) -> tuple[int, int]:
    """Mayor recorte con la proporción pedida que cabe en el vídeo original."""
    if source_w <= 0 or source_h <= 0:
        return source_w, source_h
    if source_w / source_h > target_ratio:
        h = source_h
        w = int(round(h * target_ratio))
    else:
        w = source_w
        h = int(round(w / target_ratio))
    w = min(w - (w % 2), source_w - (source_w % 2))
    h = min(h - (h % 2), source_h - (source_h % 2))
    return max(w, 2), max(h, 2)


def build_crop_expression(keyframes: list[tuple[float, float]], *, fallback: float) -> str:
    """Expresión de ffmpeg con interpolación lineal entre puntos clave.

    El resultado debe ir entre comillas simples dentro del filtro
    (`crop=x='<expr>'`), que es lo que protege las comas de la expresión.
    """
    if not keyframes:
        return f"{fallback:.1f}"
    if len(keyframes) == 1:
        return f"{keyframes[0][1]:.1f}"

    # Se construye de atrás hacia delante: if(lt(t,T1), tramo1, if(lt(t,T2), ...))
    expr = f"{keyframes[-1][1]:.1f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(keyframes, keyframes[1:]))):
        span = max(t1 - t0, 1e-3)
        slope = (x1 - x0) / span
        segment = f"({x0:.1f}+({slope:.4f})*(t-{t0:.3f}))"
        expr = f"if(lt(t,{t1:.3f}),{segment},{expr})"
    return expr


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_aspect(aspect: str) -> float:
    try:
        w, _, h = aspect.partition(":")
        return float(w) / float(h)
    except (ValueError, ZeroDivisionError):
        return 9 / 16
