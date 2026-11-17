"""Detección de enfermedades de la papa.

Si existe `models/papa_modelo.keras` (entrenado con `entrenar.py`) se usa la red
neuronal. Si no existe, se usa un MODO DEMO basado en el color de la hoja, que
NO es fiable y solo sirve para probar la web.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
RUTA_MODELO = RAIZ / "models" / "papa_modelo.keras"
RUTA_CLASES = RAIZ / "models" / "clases.json"
TAMANO = 224

# Mapeo de las carpetas del dataset PlantVillage a nuestras claves
MAPEO_CLASES = {
    "Potato___Early_blight": "tizon_temprano",
    "Potato___Late_blight": "tizon_tardio",
    "Potato___healthy": "sana",
}


class Detector:
    def __init__(self) -> None:
        self.modelo = None
        self.clases: list[str] = []
        if RUTA_MODELO.exists() and RUTA_CLASES.exists():
            import tensorflow as tf  # import perezoso: solo si hay modelo

            self.modelo = tf.keras.models.load_model(RUTA_MODELO)
            carpetas = json.loads(RUTA_CLASES.read_text())
            self.clases = [MAPEO_CLASES.get(c, c) for c in carpetas]

    @property
    def modo(self) -> str:
        return "ia" if self.modelo is not None else "demo"

    def predecir(self, datos: bytes) -> dict:
        img = Image.open(io.BytesIO(datos)).convert("RGB").resize((TAMANO, TAMANO))
        arr = np.asarray(img, dtype=np.float32)
        if self.modelo is not None:
            probs = self.modelo.predict(arr[None, ...], verbose=0)[0]
            probs = {c: float(p) for c, p in zip(self.clases, probs)}
        else:
            probs = _heuristica_color(arr)
        clase = max(probs, key=probs.get)
        return {"clase": clase, "confianza": probs[clase], "probabilidades": probs, "modo": self.modo}


def _heuristica_color(arr: np.ndarray) -> dict[str, float]:
    """Estimación aproximada por proporción de píxeles marrones / oscuros.
    Solo para demostración: entrene el modelo real para resultados válidos."""
    hsv = np.asarray(Image.fromarray(arr.astype(np.uint8)).convert("HSV"), dtype=np.float32)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    hoja = (s > 0.15) & (v > 0.15)  # ignora fondo blanco/negro
    total = max(int(hoja.sum()), 1)
    verde = ((h >= 60) & (h <= 170) & hoja).sum() / total
    marron = ((h >= 10) & (h < 50) & (v > 0.25) & hoja).sum() / total
    oscuro = ((v <= 0.3) & (s > 0.15)).sum() / total

    danio = marron + oscuro
    puntajes = np.array([
        10 * marron,                   # tizón temprano: manchas marrones
        10 * oscuro,                   # tizón tardío: manchas oscuras/negras
        verde * max(0.0, 1 - 15 * danio),  # sana: casi todo verde, sin manchas
    ])
    puntajes = np.exp(puntajes * 3)
    puntajes /= puntajes.sum()
    return dict(zip(["tizon_temprano", "tizon_tardio", "sana"], map(float, puntajes)))
