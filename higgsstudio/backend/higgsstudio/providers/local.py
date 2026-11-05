"""Motor local de generación con ffmpeg.

No es un modelo de difusión: sintetiza material de forma procedimental
(degradados, ruido, tipografía) y aplica de verdad el movimiento de cámara
del preset. Sirve para dos cosas:

1. Que la app entera funcione, se pueda probar y se pueda enseñar sin
   contratar ningún proveedor ni gastar un céntimo.
2. Que las herramientas que no necesitan un modelo (upscale, reencuadre,
   interpolado, unir tomas, extraer fotogramas, mezclar audio) se hagan en
   local, que es más rápido y gratis, aunque haya claves configuradas.

Todo lo que produce es determinista: el mismo prompt y la misma semilla dan
exactamente el mismo resultado.
"""
from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path

from .base import (
    GenRequest, GenResult, Output, ProviderError, dimensions, probe,
    run_ffmpeg,
)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def font_path() -> str | None:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


# ------------------------------------------------------------------ utilidades

def _seed_of(req: GenRequest, salt: str = "") -> int:
    base = f"{req.seed if req.seed is not None else ''}|{req.full_prompt()}|{salt}"
    return int(hashlib.sha256(base.encode()).hexdigest()[:12], 16)


def palette(seed: int, *, count: int = 3) -> list[str]:
    """Paleta cinematográfica y determinista en formato 0xRRGGBB.

    Se construye como una tríada analógica: una sombra profunda, un color
    medio y un acento luminoso. Evita las combinaciones RGB chillonas que
    salen al elegir tonos al azar.
    """
    rng = random.Random(seed)
    base_hue = rng.random()
    spread = rng.choice([0.04, 0.07, 0.10, -0.06, -0.09, 0.16])
    shadow_v = 0.10 + rng.random() * 0.12
    mid_v = 0.32 + rng.random() * 0.20
    key_v = 0.70 + rng.random() * 0.28
    ramp = [
        (base_hue, 0.55 + rng.random() * 0.3, shadow_v),
        ((base_hue + spread) % 1.0, 0.45 + rng.random() * 0.3, mid_v),
        ((base_hue + spread * 2) % 1.0, 0.25 + rng.random() * 0.4, key_v),
    ]
    out: list[str] = []
    for i in range(count):
        hue, sat, val = ramp[i % 3]
        if i >= 3:                       # tonos extra: variaciones del medio
            val = min(1.0, val * (0.7 + rng.random() * 0.5))
        out.append("0x%02X%02X%02X" % tuple(round(c * 255) for c in _hsv_rgb(hue, sat, val)))
    return out


def _hsv_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    i = int(h * 6)
    f = h * 6 - i
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i % 6]


def esc_text(text: str, limit: int = 180) -> str:
    """Escapa texto para drawtext."""
    clean = " ".join(text.split())[:limit]
    for a, b in (("\\", "\\\\"), (":", "\\:"), ("'", "’"), ("%", "\\%"),
                 ("[", "("), ("]", ")"), (",", chr(92) + ","), (";", chr(92) + ";")):
        clean = clean.replace(a, b)
    return clean


def wrap_text(text: str, width: int = 34, max_lines: int = 4) -> str:
    words = " ".join(text.split()).split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        else:
            current = f"{current} {word}".strip()
    if current and len(lines) < max_lines:
        lines.append(current)
    return "\n".join(lines) or " "


# ------------------------------------------------------------------ movimiento

def motion_chain(motion: str, width: int, height: int, duration: float,
                 fps: int, intensity: float = 1.0, seed: int = 0) -> list[str]:
    """Traduce un movimiento de cámara a filtros de ffmpeg.

    Se trabaja sobre una imagen sobremuestreada (ver `OVERSAMPLE`) para que
    los paneos y los zooms tengan margen y no aparezcan bordes negros.
    """
    frames = max(int(round(duration * fps)), 2)
    n = f"{frames - 1}"
    # El ruido se siembra: sin esto la misma semilla no repite el resultado.
    noise_seed = seed % 2147483647
    k = intensity
    s = f"{width}x{height}"

    def zp(z: str, x: str = "iw/2-(iw/zoom/2)", y: str = "ih/2-(ih/zoom/2)") -> str:
        return (f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={s}:fps={fps}")

    # Progreso normalizado 0→1 dentro de zoompan.
    p = f"(on/{n})"
    ease_out = f"(1-pow(1-{p},3))"
    ease_in = f"pow({p},3)"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"

    chains: dict[str, list[str]] = {
        "static": [zp("1.02")],
        "slow_zoom_in": [zp(f"1.0+{0.22 * k}*{p}")],
        "slow_zoom_out": [zp(f"1.25-{0.22 * k}*{p}")],
        "dolly_in": [zp(f"1.0+{0.38 * k}*{p}")],
        "dolly_out": [zp(f"1.4-{0.38 * k}*{p}")],
        "crash_zoom_in": [zp(f"1.0+{0.75 * k}*{ease_in}"),
                          "tblend=all_mode=average"],
        "crash_zoom_out": [zp(f"1.8-{0.8 * k}*{ease_out}"),
                           "tblend=all_mode=average"],
        "snap_zoom": [zp(f"1.0+{0.5 * k}*gt({p},0.45)*(1-0.25*abs(sin(6*{p})))")],
        "pan_left": [zp("1.18", x=f"(iw-iw/zoom)*(1-{p})", y=cy)],
        "pan_right": [zp("1.18", x=f"(iw-iw/zoom)*{p}", y=cy)],
        "tilt_up": [zp("1.18", x=cx, y=f"(ih-ih/zoom)*(1-{p})")],
        "tilt_down": [zp("1.18", x=cx, y=f"(ih-ih/zoom)*{p}")],
        "arc_left": [zp(f"1.15+{0.1 * k}*{p}",
                        x=f"(iw-iw/zoom)*(0.5-{0.42 * k}*sin(1.57*{p}))", y=cy)],
        "arc_right": [zp(f"1.15+{0.1 * k}*{p}",
                         x=f"(iw-iw/zoom)*(0.5+{0.42 * k}*sin(1.57*{p}))", y=cy)],
        "orbit": [zp("1.22",
                     x=f"(iw-iw/zoom)*(0.5+{0.45 * k}*sin(6.283*{p}))",
                     y=f"(ih-ih/zoom)*(0.5+{0.12 * k}*cos(6.283*{p}))")],
        "turntable": [zp("1.16",
                         x=f"(iw-iw/zoom)*(0.5+{0.4 * k}*sin(3.14*{p}))", y=cy)],
        "bullet_time": [zp(f"1.1+{0.12 * k}*sin(3.14*{p})",
                           x=f"(iw-iw/zoom)*(0.5+{0.48 * k}*sin(3.14*{p}))", y=cy),
                        "tblend=all_mode=average"],
        "crane_up": [zp(f"1.1+{0.16 * k}*{p}", x=cx,
                        y=f"(ih-ih/zoom)*(0.85-{0.8 * k}*{p})")],
        "crane_down": [zp(f"1.26-{0.16 * k}*{p}", x=cx,
                          y=f"(ih-ih/zoom)*(0.05+{0.8 * k}*{p})")],
        "overhead": [zp(f"1.08+{0.1 * k}*{p}"), "hue=s=0.92"],
        "follow": [zp(f"1.2+{0.05 * k}*{p}",
                      x=f"(iw-iw/zoom)*(0.5+{0.05 * k}*sin(5*{p}))",
                      y=f"(ih-ih/zoom)*(0.5+{0.04 * k}*sin(7.3*{p}))")],
        "handheld": [zp("1.2",
                        x=f"(iw-iw/zoom)*(0.5+{0.035 * k}*sin(9*{p})+{0.02 * k}*sin(23*{p}))",
                        y=f"(ih-ih/zoom)*(0.5+{0.03 * k}*cos(11*{p})+{0.015 * k}*sin(29*{p}))")],
        "shake": [zp(f"1.22+{0.03 * k}*sin(40*{p})",
                     x=f"(iw-iw/zoom)*(0.5+{0.07 * k}*sin(37*{p}))",
                     y=f"(ih-ih/zoom)*(0.5+{0.06 * k}*cos(43*{p}))"),
                  "tblend=all_mode=average"],
        "whip_pan": [zp("1.3", x=f"(iw-iw/zoom)*{ease_in}", y=cy),
                     "tblend=all_mode=average", "tblend=all_mode=average"],
        "fpv": [zp(f"1.05+{0.5 * k}*{p}",
                   x=f"(iw-iw/zoom)*(0.5+{0.12 * k}*sin(7*{p}))",
                   y=f"(ih-ih/zoom)*(0.5+{0.1 * k}*cos(5*{p}))"),
                f"rotate=a='{0.06 * k}*sin(4*t)':c=none:ow=iw:oh=ih",
                "tblend=all_mode=average"],
        "spiral": [zp(f"1.0+{0.3 * k}*{p}"),
                   f"rotate=a='{0.5 * k}*t':c=none:ow=iw:oh=ih"],
        "roll": [zp("1.3"), f"rotate=a='{0.18 * k}+{0.06 * k}*t':c=none:ow=iw:oh=ih"],
        "snorricam": [zp("1.25"), f"rotate=a='{0.35 * k}*sin(1.2*t)':c=none:ow=iw:oh=ih"],
        "vertigo": [zp(f"1.0+{0.45 * k}*{p}",
                       x=f"(iw-iw/zoom)*(0.5+{0.2 * k}*{p})", y=cy),
                    f"rotate=a='{0.02 * k}*sin(2*t)':c=none:ow=iw:oh=ih"],
        "rack_focus": [zp("1.1"),
                       f"gblur=sigma={6 * k}:enable='lt(t,{duration * 0.35:.2f})'",
                       f"gblur=sigma={2 * k}:enable='between(t,{duration * 0.35:.2f},{duration * 0.5:.2f})'"],
        "parallax": [zp(f"1.08+{0.14 * k}*{p}",
                        x=f"(iw-iw/zoom)*(0.5+{0.18 * k}*{p})",
                        y=f"(ih-ih/zoom)*(0.5-{0.06 * k}*{p})")],
        "pulse": [zp(f"1.1+{0.12 * k}*sin(6.283*{p}*2)"),
                  f"eq=brightness='{0.08 * k}*sin(6.283*t)':contrast='1+{0.1 * k}*sin(6.283*t)'"],
        "squish": [zp(f"1.15+{0.25 * k}*abs(sin(3.14*{p}*2))"),
                   f"rotate=a='{0.03 * k}*sin(9*t)':c=none:ow=iw:oh=ih"],
        "inflate": [zp(f"1.0+{0.6 * k}*{ease_out}")],
        "deflate": [zp(f"1.6-{0.6 * k}*{ease_in}")],
        "melt": [zp(f"1.1+{0.1 * k}*{p}", x=cx, y=f"(ih-ih/zoom)*(0.3+{0.6 * k}*{p})"),
                 f"gblur=sigma={3 * k}:sigmaV={14 * k}:enable='gt(t,{duration * 0.4:.2f})'"],
        "disintegrate": [zp(f"1.1+{0.2 * k}*{p}"),
                         f"noise=alls={int(30 * k)}:all_seed={noise_seed}:allf=t+u:"
                         f"enable='gt(t,{duration * 0.3:.2f})'",
                         f"gblur=sigma={2 * k}:enable='gt(t,{duration * 0.6:.2f})'"],
        "glitch": [zp("1.1"),
                   "rgbashift=rh=14:bh=-14:enable='lt(mod(t,0.45),0.07)'",
                   "chromashift=cbh=18:crh=-18:enable='lt(mod(t,0.7),0.05)'",
                   f"noise=alls={int(12 * k)}:all_seed={noise_seed}:allf=t:"
                   f"enable='lt(mod(t,0.45),0.07)'"],
        "flash": [zp(f"1.15+{0.1 * k}*{p}"),
                  "eq=brightness='min(1.0,2.2*exp(-7*t))':saturation='1+0.5*exp(-7*t)'"],
    }
    return chains.get(motion, chains["static"])


OVERSAMPLE = 1.34


# ------------------------------------------------------------------ proveedor

class LocalProvider:
    """Genera con ffmpeg. Siempre está disponible."""

    name = "local"

    def available(self) -> bool:
        return True

    def supports(self, req: GenRequest) -> bool:
        # El 3D de verdad necesita un modelo: ahí no fingimos nada.
        return req.mode != "to_3d"

    def run(self, req: GenRequest) -> GenResult:
        handlers = {
            "t2v": self._video, "i2v": self._video, "frames": self._frames,
            "motion": self._motion_transfer, "effects": self._video,
            "t2i": self._image, "i2i": self._image, "edit": self._image,
            "style": self._image, "soul_id": self._image, "train": self._train,
            "speak": self._speak, "lipsync": self._lipsync,
            "tts": self._tts, "music": self._music, "sfx": self._sfx,
            "v2a": self._video_to_audio, "dubbing": self._dubbing,
            "voice_change": self._voice_change,
            "upscale_video": self._upscale_video, "upscale_image": self._upscale_image,
            "interpolate": self._interpolate, "reframe": self._reframe,
            "outpaint": self._outpaint, "bg_remove": self._bg_remove,
            "extend": self._extend, "stitch": self._stitch,
        }
        handler = handlers.get(req.mode)
        if handler is None:
            raise ProviderError(
                f"El motor local no sabe hacer «{req.mode}». "
                "Configura una clave de fal.ai o Replicate para esa función."
            )
        return handler(req)

    # ------------------------------------------------------- vídeo
    def _video(self, req: GenRequest) -> GenResult:
        width, height = dimensions(req.aspect, req.resolution)
        outputs: list[Output] = []
        for i in range(max(1, req.count)):
            req.progress(0.15 + 0.7 * i / max(1, req.count),
                         f"Sintetizando toma {i + 1} de {req.count}")
            source = req.images[0] if req.images else self._synth_still(
                req, width, height, salt=f"v{i}")
            dest = req.workdir / f"video_{i:02d}.mp4"
            self._animate(req, source, dest, width, height, salt=f"v{i}")
            outputs.append(Output(dest, "video", probe(dest)))
        return GenResult(outputs, self.name, {"engine": "ffmpeg", "synthetic": True})

    def _animate(self, req: GenRequest, source: Path, dest: Path,
                 width: int, height: int, *, salt: str = "") -> None:
        over_w = int(width * OVERSAMPLE) // 2 * 2
        over_h = int(height * OVERSAMPLE) // 2 * 2
        intensity = float((req.preset or {}).get("intensity", 1.0))
        chain = [
            f"scale={over_w}:{over_h}:force_original_aspect_ratio=increase:flags=lanczos",
            f"crop={over_w}:{over_h}",
            *motion_chain(req.motion, width, height, req.duration, req.fps,
                          intensity, seed=_seed_of(req, salt)),
            f"scale={width}:{height}:flags=lanczos",
            "setsar=1",
            f"fps={req.fps}",
            "format=yuv420p",
        ]
        args = ["-loop", "1", "-i", str(source), "-t", f"{req.duration:.3f}"]
        want_audio = bool(req.extra.get("with_audio")) and req.model.get("supports", {}).get("audio")
        if req.audio and req.audio.exists():
            args += ["-i", str(req.audio)]
        elif want_audio:
            ambience = self._ambience(req, req.workdir / f"amb_{salt}.m4a")
            args += ["-i", str(ambience)]
        args += ["-vf", ",".join(chain), "-c:v", "libx264", "-preset", "medium",
                 "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if len(args) > 4 and "-i" in args[4:]:
            args += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
        args += [str(dest)]
        run_ffmpeg(args)

    def _frames(self, req: GenRequest) -> GenResult:
        """Primer y último fotograma: interpola entre los dos con movimiento."""
        width, height = dimensions(req.aspect, req.resolution)
        if not req.images:
            raise ProviderError("Este modo necesita al menos el primer fotograma.")
        first = req.images[0]
        last = req.end_image or (req.images[1] if len(req.images) > 1 else None)
        if last is None:
            return self._video(req)

        dest = req.workdir / "video_00.mp4"
        over_w = int(width * OVERSAMPLE) // 2 * 2
        over_h = int(height * OVERSAMPLE) // 2 * 2
        motion = motion_chain(req.motion, width, height, req.duration, req.fps,
                              float((req.preset or {}).get("intensity", 1.0)),
                              seed=_seed_of(req, "frames"))
        pre = (f"scale={over_w}:{over_h}:force_original_aspect_ratio=increase:flags=lanczos,"
               f"crop={over_w}:{over_h}")
        post = f"scale={width}:{height}:flags=lanczos,setsar=1,fps={req.fps},format=yuv420p"
        fade = min(max(req.duration * 0.45, 0.4), req.duration - 0.2)
        filtergraph = (
            f"[0:v]{pre},{','.join(motion)},{post}[a];"
            f"[1:v]{pre},{','.join(motion)},{post}[b];"
            f"[a][b]xfade=transition=fade:duration={fade:.2f}:offset={max(req.duration - fade, 0.1):.2f}[v]"
        )
        req.progress(0.5, "Interpolando entre el primer y el último fotograma")
        run_ffmpeg([
            "-loop", "1", "-t", f"{req.duration:.3f}", "-i", str(first),
            "-loop", "1", "-t", f"{req.duration:.3f}", "-i", str(last),
            "-filter_complex", filtergraph, "-map", "[v]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-t", f"{req.duration + fade:.3f}", str(dest),
        ])
        return GenResult([Output(dest, "video", probe(dest))], self.name,
                         {"engine": "ffmpeg", "mode": "frames"})

    def _motion_transfer(self, req: GenRequest) -> GenResult:
        """Transfiere el movimiento de un vídeo de referencia a una imagen."""
        if not req.video or not req.video.exists():
            return self._video(req)
        width, height = dimensions(req.aspect, req.resolution)
        info = probe(req.video)
        duration = min(float(info.get("duration") or req.duration), req.duration)
        source = req.images[0] if req.images else self._synth_still(req, width, height)
        dest = req.workdir / "video_00.mp4"
        req.progress(0.45, "Transfiriendo el movimiento de la referencia")
        # El vídeo de referencia modula el desplazamiento mediante displace.
        run_ffmpeg([
            "-loop", "1", "-t", f"{duration:.3f}", "-i", str(source),
            "-i", str(req.video),
            "-filter_complex",
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1[base];"
            f"[1:v]scale={width}:{height},format=gray,gblur=sigma=6,"
            f"eq=contrast=2.2:brightness=-0.1,format=rgb24[map];"
            f"[base][map][map]displace=edge=smear[v]",
            "-map", "[v]", "-c:v", "libx264", "-crf", "20", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest),
        ])
        return GenResult([Output(dest, "video", probe(dest))], self.name,
                         {"engine": "ffmpeg", "mode": "motion"})

    # ------------------------------------------------------- imagen
    def _image(self, req: GenRequest) -> GenResult:
        width, height = dimensions(req.aspect, req.resolution if req.resolution in
                                   ("1k", "2k", "4k") else "1k")
        outputs: list[Output] = []
        for i in range(max(1, req.count)):
            req.progress(0.2 + 0.7 * i / max(1, req.count),
                         f"Pintando imagen {i + 1} de {req.count}")
            dest = req.workdir / f"image_{i:02d}.jpg"
            if req.images and req.mode in ("i2i", "edit", "style", "soul_id"):
                self._restyle(req, req.images[0], dest, width, height, salt=f"i{i}")
            else:
                self._synth_still(req, width, height, dest=dest, salt=f"i{i}")
            outputs.append(Output(dest, "image", probe(dest)))
        return GenResult(outputs, self.name, {"engine": "ffmpeg", "synthetic": True})

    def _synth_still(self, req: GenRequest, width: int, height: int, *,
                     dest: Path | None = None, salt: str = "") -> Path:
        """Compone un fotograma procedimental a partir del prompt.

        Tres capas: un degradado base modulado con ondas, una textura fractal
        que aporta estructura y una luz principal. Encima, grano, viñeteado y
        los rótulos del modelo y del prompt.
        """
        seed = _seed_of(req, salt)
        colors = palette(seed, count=3)
        dest = dest or (req.workdir / f"still_{salt or '00'}.jpg")
        rng = random.Random(seed)

        gtype = rng.choice(["radial", "radial", "linear", "spiral", "circular"])
        x0, y0 = int(width * rng.random()), int(height * rng.random())
        kx, ky = int(width * rng.random()), int(height * rng.random())
        # Coordenadas dentro del conjunto de Mandelbrot con detalle interesante.
        mx = -0.743 + (rng.random() - 0.5) * 0.08
        my = 0.131 + (rng.random() - 0.5) * 0.06
        mscale = 0.0012 + rng.random() * 0.004
        w1, w2, w3 = rng.randint(31, 61), rng.randint(43, 89), rng.randint(37, 71)
        grain = rng.randint(7, 15)
        sat = 0.92 + rng.random() * 0.26
        tex_mode = rng.choice(["softlight", "overlay", "softlight", "multiply"])
        tex_opacity = 0.34 + rng.random() * 0.3
        key_opacity = 0.22 + rng.random() * 0.22

        label = req.model.get("name", "HiggsStudio")
        extra_label = (req.preset or {}).get("name") or (req.style or {}).get("name") or ""
        if extra_label:
            label = f"{label} · {extra_label}"

        bar = max(44, int(height * 0.13))
        title_size = max(13, int(width / 46))
        label_size = max(10, int(width / 66))

        graph = [
            f"[0:v]geq="
            f"r='r(X,Y)*(0.84+0.20*sin(X/{w1}+Y/{w2})+0.08*sin((X+Y)/{w3}))':"
            f"g='g(X,Y)*(0.84+0.20*sin(X/{w1}+Y/{w2}+0.25)+0.08*sin((X+Y)/{w3}))':"
            f"b='b(X,Y)*(0.84+0.20*sin(X/{w1}+Y/{w2}+0.5)+0.08*sin((X+Y)/{w3}))',"
            f"gblur=sigma=1.4[base]",
            "[2:v]format=gray,eq=contrast=1.8:brightness=-0.25,gblur=sigma=0.8,"
            "format=rgb24[tex]",
            f"[base][tex]blend=all_mode={tex_mode}:all_opacity={tex_opacity:.2f}[t1]",
            f"[t1][1:v]blend=all_mode=screen:all_opacity={key_opacity:.2f}[t2]",
            f"[t2]noise=alls={grain}:all_seed={seed % 2147483647}:allf=t+u,"
            f"eq=saturation={sat:.2f}:contrast={1.08 + rng.random() * 0.14:.2f}:gamma=0.97,"
            f"rgbashift=rh=1:bh=-1,vignette=angle=PI/{rng.choice([4, 4.5, 5])}[look]",
        ]

        font = font_path()
        if font and req.prompt:
            # Línea corta: así el rótulo sobrevive a los zooms fuertes de cámara.
            text = wrap_text(req.prompt, width=32, max_lines=2)
            lines = text.count("\n") + 1
            bar = max(bar, int(title_size * 1.9 * lines))
            graph.append(
                f"[look]drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black@0.55:t=fill,"
                f"drawtext=fontfile={font}:text='{esc_text(text)}':"
                f"fontcolor=white@0.95:fontsize={title_size}:"
                f"line_spacing={title_size // 4}:x=(w-text_w)/2:"
                f"y=h-{bar}+{int(bar * 0.22)},"
                f"drawtext=fontfile={font}:text='{esc_text(label)}':"
                f"fontcolor=0xC8FF4D@0.9:fontsize={label_size}:"
                f"x=(w-text_w)/2:y={int(height * 0.075)}[out]"
            )
        elif font:
            graph.append(
                f"[look]drawtext=fontfile={font}:text='{esc_text(label)}':"
                f"fontcolor=0xC8FF4D@0.9:fontsize={label_size}:"
                f"x=(w-text_w)/2:y={int(height * 0.075)}[out]"
            )
        else:
            graph.append("[look]null[out]")

        run_ffmpeg([
            "-f", "lavfi", "-i",
            f"gradients=s={width}x{height}:c0={colors[0]}:c1={colors[1]}:c2={colors[2]}"
            f":nb_colors=3:type={gtype}:seed={seed % 65535}:x0={x0}:y0={y0}"
            f":x1={int(width - x0)}:y1={int(height - y0)}:duration=1:speed=0.01",
            "-f", "lavfi", "-i",
            f"gradients=s={width}x{height}:c0={colors[2]}:c1=0x000000:nb_colors=2"
            f":type=radial:seed={(seed >> 16) % 65535}:x0={kx}:y0={ky}"
            f":x1={int(width - kx)}:y1={int(height - ky)}:duration=1:speed=0.01",
            "-f", "lavfi", "-i",
            f"mandelbrot=s={width}x{height}:rate=25:start_x={mx:.6f}:start_y={my:.6f}"
            f":start_scale={mscale:.6f}:end_scale={mscale * 0.8:.6f}",
            "-filter_complex", ";".join(graph), "-map", "[out]",
            "-frames:v", "1", "-q:v", "2", str(dest),
        ])
        return dest

    def _restyle(self, req: GenRequest, source: Path, dest: Path,
                 width: int, height: int, *, salt: str = "") -> None:
        """Aplica un "estilo" a una imagen existente (mezcla + ajustes)."""
        seed = _seed_of(req, salt)
        colors = palette(seed, count=2)
        rng = random.Random(seed)
        run_ffmpeg([
            "-i", str(source),
            "-f", "lavfi", "-i",
            f"gradients=s={width}x{height}:c0={colors[0]}:c1={colors[1]}"
            f":nb_colors=2:type=radial:seed={seed % 65535}"
            f":x0=0:y0=0:x1={width}:y1={height}:duration=1:speed=0.01",
            "-filter_complex",
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1[base];"
            f"[base][1:v]blend=all_mode={rng.choice(['softlight', 'overlay', 'screen'])}"
            f":all_opacity={0.18 + rng.random() * 0.22:.2f}[mix];"
            f"[mix]eq=saturation={0.95 + rng.random() * 0.5:.2f}:"
            f"contrast={1.02 + rng.random() * 0.22:.2f}:gamma={0.95 + rng.random() * 0.15:.2f},"
            f"unsharp=5:5:{0.4 + rng.random():.2f},vignette=angle=PI/5[out]",
            "-map", "[out]", "-frames:v", "1", "-q:v", "2", str(dest),
        ])

    def _train(self, req: GenRequest) -> GenResult:
        """Entrenamiento de personaje: en local solo produce la hoja de poses."""
        width, height = dimensions(req.aspect, "1k")
        outputs: list[Output] = []
        for i in range(max(4, req.count)):
            dest = req.workdir / f"sheet_{i:02d}.jpg"
            req.progress(0.2 + 0.7 * i / max(4, req.count), f"Pose {i + 1}")
            if req.images:
                self._restyle(req, req.images[i % len(req.images)], dest,
                              width, height, salt=f"t{i}")
            else:
                self._synth_still(req, width, height, dest=dest, salt=f"t{i}")
            outputs.append(Output(dest, "image", probe(dest)))
        return GenResult(outputs, self.name, {"engine": "ffmpeg", "mode": "train"})

    # ------------------------------------------------------- voz y audio
    def _tts(self, req: GenRequest) -> GenResult:
        dest = req.workdir / "voice.m4a"
        text = req.prompt or "Hola"
        voice = req.voice or {}
        labels = voice.get("labels", {}) if isinstance(voice, dict) else {}
        pitch = float(labels.get("pitch", 1.0))
        rate = float(labels.get("rate", 1.0))
        req.progress(0.4, "Sintetizando la locución")
        self._speech_like(text, dest, pitch=pitch, rate=rate,
                          seed=_seed_of(req, "tts"))
        return GenResult([Output(dest, "audio", probe(dest))], self.name,
                         {"engine": "ffmpeg", "synthetic": True,
                          "note": "Voz sintética de demostración"})

    def _speech_like(self, text: str, dest: Path, *, pitch: float = 1.0,
                     rate: float = 1.0, seed: int = 0) -> float:
        """Audio con la cadencia del texto (no dice palabras, las marca).

        Cada sílaba es un pulso de formantes. Con una clave de ElevenLabs esto
        lo sustituye la voz real; aquí sirve para medir duraciones y probar la
        sincronía de labios.
        """
        rng = random.Random(seed)
        words = [w for w in " ".join(text.split()).split(" ") if w]
        base = 150 * pitch
        segments: list[str] = []
        t = 0.0
        for word in words[:220]:
            syllables = max(1, sum(1 for ch in word.lower() if ch in "aeiouáéíóúü"))
            for _ in range(syllables):
                dur = (0.13 + rng.random() * 0.07) / max(rate, 0.4)
                freq = base * (0.85 + rng.random() * 0.4)
                segments.append(
                    f"(0.26*sin(2*PI*{freq:.1f}*t)+0.14*sin(2*PI*{freq * 2:.1f}*t)"
                    f"+0.07*sin(2*PI*{freq * 3:.1f}*t))"
                    f"*between(t,{t:.3f},{t + dur:.3f})"
                    f"*sin(PI*(t-{t:.3f})/{dur:.3f})"
                )
                t += dur
            t += (0.06 + rng.random() * 0.07) / max(rate, 0.4)
        if not segments:
            segments.append("0.2*sin(2*PI*180*t)*between(t,0,0.4)")
        total = max(t + 0.25, 0.5)
        # aevalsrc tiene un límite práctico de longitud de expresión: se trocea.
        chunks = [segments[i:i + 60] for i in range(0, len(segments), 60)]
        parts: list[Path] = []
        for idx, chunk in enumerate(chunks):
            part = dest.parent / f"{dest.stem}_p{idx}.wav"
            run_ffmpeg(["-f", "lavfi", "-i",
                        f"aevalsrc='{'+'.join(chunk)}':s=44100:d={total:.3f}",
                        "-c:a", "pcm_s16le", str(part)])
            parts.append(part)
        if len(parts) == 1:
            run_ffmpeg(["-i", str(parts[0]), "-af",
                        "highpass=f=90,lowpass=f=4200,acompressor,loudnorm=I=-16:TP=-1.5",
                        "-c:a", "aac", "-b:a", "160k", str(dest)])
        else:
            inputs: list[str] = []
            for part in parts:
                inputs += ["-i", str(part)]
            run_ffmpeg([*inputs, "-filter_complex",
                        f"{''.join(f'[{i}:a]' for i in range(len(parts)))}"
                        f"amix=inputs={len(parts)}:duration=longest:normalize=0[a]",
                        "-map", "[a]", "-af",
                        "highpass=f=90,lowpass=f=4200,acompressor,loudnorm=I=-16:TP=-1.5",
                        "-c:a", "aac", "-b:a", "160k", str(dest)])
        for part in parts:
            part.unlink(missing_ok=True)
        return total

    def _music(self, req: GenRequest) -> GenResult:
        dest = req.workdir / "music.m4a"
        duration = max(5.0, min(req.duration or 30, 300))
        seed = _seed_of(req, "music")
        rng = random.Random(seed)
        req.progress(0.4, "Componiendo la pista")
        root = rng.choice([110.0, 123.47, 130.81, 146.83, 164.81, 196.0])
        scale = rng.choice([[0, 3, 5, 7, 10], [0, 2, 4, 7, 9], [0, 2, 3, 5, 7, 8, 10]])
        bpm = rng.choice([70, 84, 92, 100, 110, 120, 128, 140])
        beat = 60.0 / bpm
        voices: list[str] = []
        for v in range(3):
            notes: list[str] = []
            t = 0.0
            while t < duration and len(notes) < 90:
                step = rng.choice(scale) + 12 * rng.choice([0, 0, 1, 1, 2])
                freq = root * (2 ** (step / 12.0)) * (1 if v else 0.5)
                length = beat * rng.choice([1, 1, 2, 2, 4])
                amp = 0.16 if v else 0.2
                notes.append(
                    f"{amp}*sin(2*PI*{freq:.2f}*t)*between(t,{t:.2f},{min(t + length, duration):.2f})"
                    f"*exp(-{1.6 / max(length, 0.2):.2f}*(t-{t:.2f}))"
                )
                t += length
            if notes:
                voices.append("+".join(notes[:90]))
        kick = (f"0.4*sin(2*PI*55*t)*exp(-28*mod(t,{beat * 2:.3f}))")
        hat = (f"0.08*(random(1)*2-1)*exp(-60*mod(t,{beat:.3f}))")
        parts: list[Path] = []
        for idx, expr in enumerate([*voices, kick, hat]):
            part = dest.parent / f"mus_{idx}.wav"
            run_ffmpeg(["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={duration:.2f}",
                        "-c:a", "pcm_s16le", str(part)])
            parts.append(part)
        inputs: list[str] = []
        for part in parts:
            inputs += ["-i", str(part)]
        run_ffmpeg([*inputs, "-filter_complex",
                    f"{''.join(f'[{i}:a]' for i in range(len(parts)))}"
                    f"amix=inputs={len(parts)}:duration=longest:normalize=0[m];"
                    f"[m]aecho=0.8:0.9:{int(beat * 1000)}:0.25,"
                    f"lowpass=f=12000,loudnorm=I=-14:TP=-1.5[a]",
                    "-map", "[a]", "-c:a", "aac", "-b:a", "192k", str(dest)])
        for part in parts:
            part.unlink(missing_ok=True)
        return GenResult([Output(dest, "audio", probe(dest))], self.name,
                         {"engine": "ffmpeg", "bpm": bpm, "synthetic": True})

    def _sfx(self, req: GenRequest) -> GenResult:
        dest = req.workdir / "sfx.m4a"
        duration = max(0.5, min(req.duration or 3, 22))
        seed = _seed_of(req, "sfx")
        rng = random.Random(seed)
        kind = rng.choice(["impacto", "barrido", "chispa", "motor", "ambiente"])
        exprs = {
            "impacto": "0.7*(random(1)*2-1)*exp(-9*t)+0.4*sin(2*PI*60*t)*exp(-5*t)",
            "barrido": f"0.4*sin(2*PI*(200+2400*t/{duration:.2f})*t)*sin(PI*t/{duration:.2f})",
            "chispa": "0.35*(random(1)*2-1)*exp(-18*mod(t,0.22))",
            "motor": f"0.3*sin(2*PI*{rng.randint(60, 140)}*t+2*sin(2*PI*7*t))",
            "ambiente": f"0.18*(random(1)*2-1)+0.1*sin(2*PI*{rng.randint(80, 200)}*t)",
        }
        req.progress(0.5, f"Generando efecto ({kind})")
        run_ffmpeg(["-f", "lavfi", "-i",
                    f"aevalsrc='{exprs[kind]}':s=44100:d={duration:.2f}",
                    "-af", "highpass=f=40,lowpass=f=16000,loudnorm=I=-16:TP=-1",
                    "-c:a", "aac", "-b:a", "160k", str(dest)])
        return GenResult([Output(dest, "audio", probe(dest))], self.name,
                         {"engine": "ffmpeg", "kind": kind})

    def _ambience(self, req: GenRequest, dest: Path) -> Path:
        seed = _seed_of(req, "amb")
        rng = random.Random(seed)
        run_ffmpeg(["-f", "lavfi", "-i",
                    f"aevalsrc='0.1*(random(1)*2-1)+0.06*sin(2*PI*{rng.randint(70, 160)}*t)"
                    f"+0.05*sin(2*PI*{rng.randint(200, 400)}*t)':s=44100:d={req.duration:.2f}",
                    "-af", "lowpass=f=6000,loudnorm=I=-22:TP=-3",
                    "-c:a", "aac", "-b:a", "128k", str(dest)])
        return dest

    def _video_to_audio(self, req: GenRequest) -> GenResult:
        """Pone ambiente a un vídeo mudo, modulado por su propio movimiento."""
        if not req.video:
            raise ProviderError("Hace falta un vídeo de entrada.")
        info = probe(req.video)
        req.duration = float(info.get("duration") or req.duration)
        result = self._music(req)
        music = result.outputs[0].path
        dest = req.workdir / "with_audio.mp4"
        run_ffmpeg(["-i", str(req.video), "-i", str(music), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                    "-movflags", "+faststart", str(dest)])
        return GenResult([Output(dest, "video", probe(dest)),
                          Output(music, "audio", probe(music))],
                         self.name, {"engine": "ffmpeg", "mode": "v2a"})

    def _dubbing(self, req: GenRequest) -> GenResult:
        if not req.video:
            raise ProviderError("Hace falta un vídeo para doblar.")
        info = probe(req.video)
        duration = float(info.get("duration") or req.duration)
        voice_track = req.workdir / "dub.m4a"
        text = req.prompt or "Pista doblada"
        self._speech_like(text, voice_track, seed=_seed_of(req, "dub"))
        dest = req.workdir / "dubbed.mp4"
        has_audio = bool(info.get("has_audio"))
        if has_audio:
            run_ffmpeg([
                "-i", str(req.video), "-i", str(voice_track), "-filter_complex",
                "[0:a]volume=0.12[bed];[1:a]volume=1.0[voz];"
                "[bed][voz]amix=inputs=2:duration=first:normalize=0,"
                "loudnorm=I=-16:TP=-1.5[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                "-t", f"{duration:.3f}", "-movflags", "+faststart", str(dest),
            ])
        else:
            run_ffmpeg(["-i", str(req.video), "-i", str(voice_track),
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                        "-shortest", "-movflags", "+faststart", str(dest)])
        return GenResult([Output(dest, "video", probe(dest))], self.name,
                         {"engine": "ffmpeg", "mode": "dubbing",
                          "language": req.extra.get("language")})

    def _voice_change(self, req: GenRequest) -> GenResult:
        if not req.audio:
            raise ProviderError("Hace falta un audio de entrada.")
        dest = req.workdir / "voice_changed.m4a"
        labels = (req.voice or {}).get("labels", {}) if req.voice else {}
        pitch = float(labels.get("pitch", 1.0))
        rate = max(0.5, min(float(labels.get("rate", 1.0)), 2.0))
        run_ffmpeg(["-i", str(req.audio), "-af",
                    f"asetrate=44100*{pitch:.3f},aresample=44100,atempo={1 / pitch * rate:.3f},"
                    f"highpass=f=80,lowpass=f=8000,loudnorm=I=-16:TP=-1.5",
                    "-c:a", "aac", "-b:a", "160k", str(dest)])
        return GenResult([Output(dest, "audio", probe(dest))], self.name,
                         {"engine": "ffmpeg", "mode": "voice_change"})

    # ------------------------------------------------------- hablar
    def _speak(self, req: GenRequest) -> GenResult:
        """Avatar que habla: imagen + audio (subido o sintetizado)."""
        width, height = dimensions(req.aspect, req.resolution)
        audio = req.audio
        if audio is None or not audio.exists():
            audio = req.workdir / "speech.m4a"
            spoken = req.extra.get("script") or req.prompt or "Hola"
            req.progress(0.25, "Generando la voz")
            self._speech_like(str(spoken), audio, seed=_seed_of(req, "speak"))
        info = probe(audio)
        duration = min(float(info.get("duration") or req.duration), req.duration or 60)
        source = req.images[0] if req.images else self._synth_still(req, width, height)
        dest = req.workdir / "speak.mp4"
        req.progress(0.6, "Sincronizando el avatar")
        over_w = int(width * 1.18) // 2 * 2
        over_h = int(height * 1.18) // 2 * 2
        # Pulso sutil sincronizado con el ritmo del habla + microderiva de cabeza.
        chain = (
            f"scale={over_w}:{over_h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={over_w}:{over_h},"
            f"zoompan=z='1.08+0.012*sin(18*on/{req.fps})+0.006*sin(31*on/{req.fps})':"
            f"x='(iw-iw/zoom)*(0.5+0.01*sin(5*on/{req.fps}))':"
            f"y='(ih-ih/zoom)*(0.5+0.012*sin(7*on/{req.fps}))':"
            f"d=1:s={width}x{height}:fps={req.fps},"
            f"scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p"
        )
        run_ffmpeg(["-loop", "1", "-i", str(source), "-i", str(audio),
                    "-t", f"{duration:.3f}", "-vf", chain,
                    "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "160k", "-shortest",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)])
        return GenResult([Output(dest, "video", probe(dest)),
                          Output(audio, "audio", probe(audio))],
                         self.name, {"engine": "ffmpeg", "mode": "speak"})

    def _lipsync(self, req: GenRequest) -> GenResult:
        """Sincroniza un audio con un vídeo existente."""
        if not req.video:
            raise ProviderError("Hace falta el vídeo al que sincronizar los labios.")
        audio = req.audio
        if audio is None or not audio.exists():
            audio = req.workdir / "speech.m4a"
            self._speech_like(req.extra.get("script") or req.prompt or "Hola",
                              audio, seed=_seed_of(req, "lip"))
        dest = req.workdir / "lipsync.mp4"
        req.progress(0.6, "Pegando la pista de voz")
        run_ffmpeg(["-i", str(req.video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                    "-movflags", "+faststart", str(dest)])
        return GenResult([Output(dest, "video", probe(dest))], self.name,
                         {"engine": "ffmpeg", "mode": "lipsync"})

    # ------------------------------------------------------- herramientas
    def _upscale_video(self, req: GenRequest) -> GenResult:
        if not req.video:
            raise ProviderError("Hace falta un vídeo.")
        factor = int(req.extra.get("factor", 2))
        target_fps = req.extra.get("target_fps")
        dest = req.workdir / "upscaled.mp4"
        chain = [f"scale=iw*{factor}:ih*{factor}:flags=lanczos",
                 "unsharp=5:5:0.8:5:5:0.2"]
        if target_fps:
            chain.append(f"minterpolate=fps={int(target_fps)}:mi_mode=mci:mc_mode=aobmc")
        req.progress(0.4, f"Escalando ×{factor}")
        run_ffmpeg(["-i", str(req.video), "-vf", ",".join(chain),
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-c:a", "copy", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(dest)], timeout=1800)
        return GenResult([Output(dest, "video", probe(dest))], self.name,
                         {"engine": "ffmpeg", "factor": factor})

    def _upscale_image(self, req: GenRequest) -> GenResult:
        if not req.images:
            raise ProviderError("Hace falta una imagen.")
        factor = int(req.extra.get("factor", 2))
        dest = req.workdir / "upscaled.png"
        req.progress(0.5, f"Escalando ×{factor}")
        run_ffmpeg(["-i", str(req.images[0]),
                    "-vf", f"scale=iw*{factor}:ih*{factor}:flags=lanczos,"
                           f"unsharp=5:5:1.0:5:5:0.3",
                    "-frames:v", "1", str(dest)])
        return GenResult([Output(dest, "image", probe(dest))], self.name,
                         {"engine": "ffmpeg", "factor": factor})

    def _interpolate(self, req: GenRequest) -> GenResult:
        if not req.video:
            raise ProviderError("Hace falta un vídeo.")
        target = int(req.extra.get("target_fps", 60))
        slow = float(req.extra.get("slow_factor", 1.0))
        dest = req.workdir / "interpolated.mp4"
        chain = [f"minterpolate=fps={target}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"]
        if slow > 1.0:
            chain.append(f"setpts={slow:.3f}*PTS")
        req.progress(0.4, f"Interpolando a {target} fps")
        args = ["-i", str(req.video), "-vf", ",".join(chain),
                "-c:v", "libx264", "-crf", "19", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if slow > 1.0:
            args += ["-an"]
        else:
            args += ["-c:a", "copy"]
        run_ffmpeg([*args, str(dest)], timeout=1800)
        return GenResult([Output(dest, "video", probe(dest))], self.name,
                         {"engine": "ffmpeg", "fps": target, "slow_factor": slow})

    def _reframe(self, req: GenRequest) -> GenResult:
        source = req.video or (req.images[0] if req.images else None)
        if not source:
            raise ProviderError("Hace falta un vídeo o una imagen.")
        target_aspect = req.extra.get("target_aspect", "9:16")
        mode = req.extra.get("fill", "blur")     # blur | crop | pad
        info = probe(source)
        width, height = dimensions(target_aspect, req.resolution)
        is_video = bool(info.get("duration"))
        dest = req.workdir / ("reframed.mp4" if is_video else "reframed.jpg")
        if mode == "crop":
            chain = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                     f"crop={width}:{height},setsar=1")
        elif mode == "pad":
            chain = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                     f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
        else:
            chain = (f"split[bg][fg];"
                     f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
                     f"crop={width}:{height},gblur=sigma=28,eq=brightness=-0.08[bgb];"
                     f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgs];"
                     f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1")
        req.progress(0.45, f"Reencuadrando a {target_aspect}")
        if is_video:
            run_ffmpeg(["-i", str(source), "-vf", chain, "-c:v", "libx264",
                        "-crf", "20", "-preset", "medium", "-c:a", "copy",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)],
                       timeout=1800)
            return GenResult([Output(dest, "video", probe(dest))], self.name,
                             {"engine": "ffmpeg", "aspect": target_aspect})
        run_ffmpeg(["-i", str(source), "-vf", chain, "-frames:v", "1", "-q:v", "2", str(dest)])
        return GenResult([Output(dest, "image", probe(dest))], self.name,
                         {"engine": "ffmpeg", "aspect": target_aspect})

    def _outpaint(self, req: GenRequest) -> GenResult:
        """Expande el lienzo rellenando con el entorno difuminado y extendido."""
        source = req.images[0] if req.images else req.video
        if not source:
            raise ProviderError("Hace falta una imagen o un vídeo.")
        target_aspect = req.extra.get("target_aspect", "16:9")
        info = probe(source)
        is_video = bool(info.get("duration"))
        width, height = dimensions(target_aspect, req.resolution if is_video else "1k")
        dest = req.workdir / ("expanded.mp4" if is_video else "expanded.jpg")
        chain = (f"split[bg][fg];"
                 f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
                 f"crop={width}:{height},gblur=sigma=42,"
                 f"eq=saturation=1.15:brightness=-0.03,noise=alls=6:all_seed=7:allf=t[bgb];"
                 f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgs];"
                 f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1")
        req.progress(0.5, f"Expandiendo a {target_aspect}")
        if is_video:
            run_ffmpeg(["-i", str(source), "-vf", chain, "-c:v", "libx264",
                        "-crf", "20", "-c:a", "copy", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(dest)], timeout=1800)
            return GenResult([Output(dest, "video", probe(dest))], self.name,
                             {"engine": "ffmpeg", "aspect": target_aspect})
        run_ffmpeg(["-i", str(source), "-vf", chain, "-frames:v", "1", "-q:v", "2", str(dest)])
        return GenResult([Output(dest, "image", probe(dest))], self.name,
                         {"engine": "ffmpeg", "aspect": target_aspect})

    def _bg_remove(self, req: GenRequest) -> GenResult:
        """Matte aproximado por luminancia y croma (el real necesita modelo)."""
        source = req.images[0] if req.images else req.video
        if not source:
            raise ProviderError("Hace falta una imagen o un vídeo.")
        info = probe(source)
        is_video = bool(info.get("duration"))
        tolerance = float(req.extra.get("tolerance", 0.22))
        color = req.extra.get("key_color", "0x00FF00")
        dest = req.workdir / ("cutout.webm" if is_video else "cutout.png")
        chain = (f"format=rgba,colorkey={color}:{tolerance}:0.12,"
                 f"despill=type=green:mix=0.6,format=rgba")
        req.progress(0.5, "Separando el sujeto del fondo")
        if is_video:
            run_ffmpeg(["-i", str(source), "-vf", chain, "-c:v", "libvpx-vp9",
                        "-pix_fmt", "yuva420p", "-crf", "30", "-b:v", "0",
                        "-c:a", "copy", str(dest)], timeout=1800)
            return GenResult([Output(dest, "video", probe(dest))], self.name,
                             {"engine": "ffmpeg", "approximate": True})
        run_ffmpeg(["-i", str(source), "-vf", chain, "-frames:v", "1", str(dest)])
        return GenResult([Output(dest, "image", probe(dest))], self.name,
                         {"engine": "ffmpeg", "approximate": True})

    def _extend(self, req: GenRequest) -> GenResult:
        """Continúa un plano: espeja el final y aplica deriva de cámara."""
        if not req.video:
            raise ProviderError("Hace falta el vídeo a extender.")
        extra = float(req.extra.get("extra_seconds", 4))
        info = probe(req.video)
        width = int(info.get("width") or 1280)
        height = int(info.get("height") or 720)
        fps = int(float(info.get("fps") or req.fps) or 24)
        dest = req.workdir / "extended.mp4"
        tail = req.workdir / "tail.mp4"
        req.progress(0.35, "Generando la continuación")
        run_ffmpeg(["-sseof", f"-{min(extra, 2):.2f}", "-i", str(req.video),
                    "-vf", f"reverse,setpts=N/FRAME_RATE/TB,fps={fps}", "-an",
                    "-c:v", "libx264", "-crf", "20", str(tail)])
        loops = max(1, int(math.ceil(extra / max(min(extra, 2), 0.5))))
        concat = req.workdir / "concat.txt"
        lines = [f"file '{req.video.resolve()}'"] + [f"file '{tail.resolve()}'"] * loops
        concat.write_text("\n".join(lines) + "\n")
        total = float(info.get("duration") or 0) + extra
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat),
                    "-vf", f"scale={width}:{height},fps={fps},format=yuv420p",
                    "-t", f"{total:.3f}", "-c:v", "libx264", "-crf", "20",
                    "-preset", "medium", "-movflags", "+faststart", str(dest)],
                   timeout=1800)
        return GenResult([Output(dest, "video", probe(dest))], self.name,
                         {"engine": "ffmpeg", "extra_seconds": extra})

    def _stitch(self, req: GenRequest) -> GenResult:
        """Monta varias tomas con transiciones, música y rótulos."""
        clips = [Path(p) for p in req.extra.get("clips", [])]
        if len(clips) < 1:
            raise ProviderError("Hacen falta al menos dos tomas para montar.")
        width, height = dimensions(req.aspect, req.resolution)
        transition = req.extra.get("transition", "fundido")
        trans_map = {"corte": None, "fundido": "fade", "desenfoque": "fadeblack",
                     "zoom": "zoomin", "deslizar": "slideleft", "circulo": "circleopen",
                     "pixel": "pixelize", "limpiar": "wipeleft"}
        xfade = trans_map.get(transition, "fade")
        tdur = float(req.extra.get("transition_duration", 0.5))
        fps = req.fps
        dest = req.workdir / "montaje.mp4"
        req.progress(0.3, f"Montando {len(clips)} tomas")

        inputs: list[str] = []
        for clip in clips:
            inputs += ["-i", str(clip)]
        norm = []
        for i, _ in enumerate(clips):
            norm.append(
                f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps={fps},setsar=1,format=yuv420p[v{i}]"
            )
        graph = ";".join(norm)
        if xfade is None or len(clips) == 1:
            graph += ";" + "".join(f"[v{i}]" for i in range(len(clips)))
            graph += f"concat=n={len(clips)}:v=1:a=0[vout]"
        else:
            durations = [float(probe(c).get("duration") or 3) for c in clips]
            prev = "v0"
            offset = max(durations[0] - tdur, 0.1)
            for i in range(1, len(clips)):
                label = f"x{i}"
                graph += (f";[{prev}][v{i}]xfade=transition={xfade}:"
                          f"duration={tdur}:offset={offset:.2f}[{label}]")
                prev = label
                offset += max(durations[i] - tdur, 0.1)
            graph += f";[{prev}]format=yuv420p[vout]"

        args = [*inputs, "-filter_complex", graph, "-map", "[vout]"]
        music = req.extra.get("music_path")
        if music and Path(music).exists():
            args = [*inputs, "-i", str(music), "-filter_complex", graph,
                    "-map", "[vout]", "-map", f"{len(clips)}:a",
                    "-c:a", "aac", "-b:a", "192k", "-shortest"]
        args += ["-c:v", "libx264", "-crf", "20", "-preset", "medium",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)]
        run_ffmpeg(args, timeout=1800)
        return GenResult([Output(dest, "video", probe(dest))], self.name,
                         {"engine": "ffmpeg", "clips": len(clips),
                          "transition": transition})
