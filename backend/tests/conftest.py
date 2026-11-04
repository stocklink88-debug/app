"""Configuración común de la suite."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Cada sesión de tests usa su propio directorio de datos.
_TMP = tempfile.mkdtemp(prefix="viralclips-tests-")
os.environ["VIRALCLIPS_DATA_DIR"] = _TMP


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return Path(_TMP)


@pytest.fixture
def words():
    """Transcripción sintética con tiempos realistas."""
    from viralclips.models import Word

    script = (
        "Hola a todos y bienvenidos al podcast. "
        "¿Sabes cuál es el error que comete el 90% de la gente al invertir? "
        "Yo lo cometí durante siete años y me costó 40000 euros. "
        "La realidad es que nadie te cuenta esto porque no vende. "
        "Te voy a dar los tres pasos exactos que uso ahora. "
        "Y entonces bueno o sea pues eh nada que eso. "
        "Gracias por ver el vídeo y hasta la próxima."
    )
    out: list[Word] = []
    t = 0.0
    for token in script.split():
        out.append(Word(token, t, t + 0.33))
        t += 0.37 + (0.8 if token.endswith((".", "?")) else 0.0)
    return out


@pytest.fixture
def transcript(words):
    from viralclips.models import Transcript

    return Transcript(
        language="es",
        words=words,
        text=" ".join(w.text for w in words),
        has_text=True,
    )
