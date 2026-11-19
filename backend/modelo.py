"""Detección de enfermedades de la papa.

Orden de preferencia:
1. Modo IA (recomendado): dos modelos binarios TFLite entrenados en Kaggle
   (`entrenar_alternaria_lancha.ipynb`), cada uno con su JSON de etiquetas y umbral:
       models/papa_alternariosis.tflite + papa_alternariosis_etiquetas.json
       models/papa_lancha.tflite        + papa_lancha_etiquetas.json
   Cada modelo responde "¿es esta enfermedad?" y se entrenó con hojas sanas Y con otras
   enfermedades como negativos, para no confundir una enfermedad con la otra.
   Se ejecutan con LiteRT (paquete `ai-edge-litert`, liviano) o, si no está, con TensorFlow.
   Filtro opcional (se usa si existe): models/papa_es_papa.tflite + papa_es_papa_etiquetas.json.
   Si dice que la foto no es de papa, se responde "no_es_papa" sin mirar las enfermedades.
   Modelo opcional "¿está sana?" (se usa si existe): models/papa_sana.tflite + papa_sana_etiquetas.json.
   Si no hay alternariosis ni rancha, decide entre "sana" y "otro_problema" (algo que la app no reconoce).
2. Modelo antiguo de 3 clases (`models/papa_modelo.keras` + `clases.json`), si existe.
3. MODO DEMO por color de la hoja: NO es fiable, solo sirve para probar la web.

La carpeta de modelos se puede cambiar con la variable de entorno MODELOS_DIR.
"""
from __future__ import annotations

import io
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_MODELOS = Path(os.environ.get("MODELOS_DIR", RAIZ / "models"))
TAMANO = 224

# Claves de enfermedad usadas en catalogo.json y en la página
ALTERNARIOSIS, RANCHA, SANA = "tizon_temprano", "tizon_tardio", "sana"
DUDOSO, NO_DETECTADO, NO_ES_PAPA = "dudoso", "no_detectado", "no_es_papa"
OTRO_PROBLEMA = "otro_problema"

# Mapeo de las carpetas del dataset PlantVillage (modelo antiguo de 3 clases)
MAPEO_CLASES = {
    "Potato___Early_blight": ALTERNARIOSIS,
    "Potato___Late_blight": RANCHA,
    "Potato___healthy": SANA,
}


def _interprete(ruta: Path):
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:  # sin LiteRT: se usa el de TensorFlow
        from tensorflow.lite import Interpreter
    it = Interpreter(model_path=str(ruta), num_threads=max(1, min(4, os.cpu_count() or 1)))
    it.allocate_tensors()
    return it


class _ModeloBinario:
    """Un modelo TFLite con salida sigmoide (probabilidad de la enfermedad) y su umbral."""

    def __init__(self, nombre: str) -> None:
        etiquetas = json.loads((CARPETA_MODELOS / f"{nombre}_etiquetas.json").read_text(encoding="utf-8"))
        self.umbral = float(etiquetas.get("umbral", 0.5))
        self.it = _interprete(CARPETA_MODELOS / f"{nombre}.tflite")
        self.entrada = self.it.get_input_details()[0]
        self.salida = self.it.get_output_details()[0]
        self.lock = threading.Lock()  # un intérprete TFLite no es seguro entre hilos

    def probabilidad(self, arr: np.ndarray) -> float:
        with self.lock:
            self.it.set_tensor(self.entrada["index"], arr[None, ...].astype(self.entrada["dtype"]))
            self.it.invoke()
            return float(self.it.get_tensor(self.salida["index"]).ravel()[0])


def _existe(nombre: str) -> bool:
    return all((CARPETA_MODELOS / f"{nombre}{ext}").exists() for ext in (".tflite", "_etiquetas.json"))


def _existen_binarios() -> bool:
    return _existe("papa_alternariosis") and _existe("papa_lancha")


class Detector:
    def __init__(self) -> None:
        self.binarios: dict[str, _ModeloBinario] = {}
        self.filtro: _ModeloBinario | None = None
        self.sana: _ModeloBinario | None = None
        self.modelo = None
        self.clases: list[str] = []
        if _existen_binarios():
            self.binarios = {ALTERNARIOSIS: _ModeloBinario("papa_alternariosis"),
                             RANCHA: _ModeloBinario("papa_lancha")}
            if _existe("papa_es_papa"):
                self.filtro = _ModeloBinario("papa_es_papa")
            if _existe("papa_sana"):
                self.sana = _ModeloBinario("papa_sana")
            # Los modelos se ejecutan a la vez, cada uno en su hilo
            self.hilos = ThreadPoolExecutor(max_workers=4)
            self._predecir_binarios(np.zeros((TAMANO, TAMANO, 3), np.float32))  # calentamiento
        elif (CARPETA_MODELOS / "papa_modelo.keras").exists() and (CARPETA_MODELOS / "clases.json").exists():
            import tensorflow as tf  # import perezoso: solo si hay modelo antiguo

            self.modelo = tf.keras.models.load_model(CARPETA_MODELOS / "papa_modelo.keras")
            carpetas = json.loads((CARPETA_MODELOS / "clases.json").read_text())
            self.clases = [MAPEO_CLASES.get(c, c) for c in carpetas]

    @property
    def modo(self) -> str:
        return "ia" if (self.binarios or self.modelo is not None) else "demo"

    def predecir(self, datos: bytes) -> dict:
        img = Image.open(io.BytesIO(datos))
        img.draft("RGB", (TAMANO * 2, TAMANO * 2))  # JPEG grande: se decodifica ya reducido (mucho más rápido)
        img = ImageOps.exif_transpose(img).convert("RGB")  # fotos de celular giradas
        arr = np.asarray(img.resize((TAMANO, TAMANO), Image.BILINEAR), dtype=np.float32)  # RGB 0-255
        if self.binarios:
            return self._predecir_binarios(arr)
        if self.modelo is not None:
            probs = self.modelo.predict(arr[None, ...], verbose=0)[0]
            probs = {c: float(p) for c, p in zip(self.clases, probs)}
        else:
            probs = _heuristica_color(arr)
        clase = max(probs, key=probs.get)
        return {"clase": clase, "confianza": probs[clase], "probabilidades": probs, "modo": self.modo}

    def _predecir_binarios(self, arr: np.ndarray) -> dict:
        # Los modelos corren en paralelo; si el filtro dice "no es papa", se ignoran las enfermedades
        ma, ml = self.binarios[ALTERNARIOSIS], self.binarios[RANCHA]
        t_a, t_l = self.hilos.submit(ma.probabilidad, arr), self.hilos.submit(ml.probabilidad, arr)
        t_p = self.hilos.submit(self.filtro.probabilidad, arr) if self.filtro else None
        t_s = self.hilos.submit(self.sana.probabilidad, arr) if self.sana else None
        pa, pl = t_a.result(), t_l.result()
        if t_p is not None:
            pp = t_p.result()
            if pp < self.filtro.umbral:
                return {"clase": NO_ES_PAPA, "confianza": 1 - pp, "probabilidades": {"papa": pp},
                        "umbrales": {"papa": self.filtro.umbral}, "modo": self.modo}
        es_a, es_l = pa >= ma.umbral, pl >= ml.umbral
        if es_a and not es_l:
            clase, conf = ALTERNARIOSIS, pa
        elif es_l and not es_a:
            clase, conf = RANCHA, pl
        elif es_a and es_l:
            clase, conf = DUDOSO, max(pa, pl)
        elif t_s is not None:
            # Ni alternariosis ni rancha: ¿la hoja está sana o tiene otra cosa?
            ps = t_s.result()
            clase, conf = (SANA, ps) if ps >= self.sana.umbral else (OTRO_PROBLEMA, 1 - ps)
        else:
            clase, conf = NO_DETECTADO, 1 - max(pa, pl)
        probs, umbrales = {ALTERNARIOSIS: pa, RANCHA: pl}, {ALTERNARIOSIS: ma.umbral, RANCHA: ml.umbral}
        if t_s is not None:
            probs[SANA], umbrales[SANA] = t_s.result(), self.sana.umbral
        return {"clase": clase, "confianza": conf, "probabilidades": probs, "umbrales": umbrales,
                "modo": self.modo}


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
    return dict(zip([ALTERNARIOSIS, RANCHA, SANA], map(float, puntajes)))
