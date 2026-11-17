"""Servidor de AgroSano: diagnóstico de enfermedades y calculadora de aplicaciones.

Ejecutar:  .venv/bin/uvicorn backend.app:app --reload
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import logging

from . import clima
from .calculadora import UNIDADES_AREA, calcular
from .modelo import Detector

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO = json.loads((Path(__file__).parent / "data" / "catalogo.json").read_text(encoding="utf-8"))
MAX_BYTES = 10 * 1024 * 1024

app = FastAPI(title="AgroSano", version="0.1.0")
detector = Detector()


def _enfermedad(cultivo: str, clave: str) -> dict:
    try:
        return CATALOGO["cultivos"][cultivo]["enfermedades"][clave]
    except KeyError:
        raise HTTPException(404, "Enfermedad no encontrada")


def _productos_de(enf: dict) -> list[dict]:
    return [{"id": p, **CATALOGO["productos"][p]} for p in enf["productos"]]


@app.get("/api/estado")
def estado():
    return {"modo_modelo": detector.modo, "cultivos": list(CATALOGO["cultivos"]), "clima": clima.disponible()}


@app.get("/api/catalogo")
def catalogo():
    return {
        "moneda": CATALOGO["moneda"],
        "nota": CATALOGO["_nota"],
        "unidades_area": list(UNIDADES_AREA),
        "cultivos": CATALOGO["cultivos"],
        "productos": CATALOGO["productos"],
    }


@app.post("/api/diagnosticar")
async def diagnosticar(foto: UploadFile = File(...), cultivo: str = "papa"):
    if cultivo != "papa":
        raise HTTPException(400, "Por ahora solo está disponible el modelo para papa.")
    if not (foto.content_type or "").startswith("image/"):
        raise HTTPException(400, "El archivo debe ser una imagen (JPG, PNG...).")
    datos = await foto.read()
    if len(datos) > MAX_BYTES:
        raise HTTPException(413, "La imagen supera los 10 MB.")
    try:
        res = detector.predecir(datos)
    except Exception:
        raise HTTPException(400, "No se pudo leer la imagen.")
    enf = _enfermedad(cultivo, res["clase"])
    return {**res, "enfermedad": {"id": res["clase"], **enf}, "productos": _productos_de(enf)}


class SolicitudCalculo(BaseModel):
    producto_id: str
    area: float = Field(gt=0)
    unidad: str = "m2"
    capacidad_tanque_l: float = Field(20, gt=0)
    nivel_dosis: str = "media"
    aplicaciones: int | None = Field(None, ge=1)
    precio_presentacion: float | None = Field(None, ge=0)


@app.post("/api/calcular")
def api_calcular(s: SolicitudCalculo):
    prod = CATALOGO["productos"].get(s.producto_id)
    if not prod:
        raise HTTPException(404, "Producto no encontrado")
    try:
        r = calcular(prod, s.area, s.unidad, s.capacidad_tanque_l, s.nivel_dosis,
                     s.aplicaciones, s.precio_presentacion)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"producto": {"id": s.producto_id, **prod}, "moneda": CATALOGO["moneda"], **r}


@app.get("/api/clima")
def api_clima(departamento: str = "", provincia: str = "", distrito: str = ""):
    """Pronóstico por hora (72 h) evaluado para fumigar en la ubicación de la chacra."""
    if not (departamento.strip() and (provincia.strip() or distrito.strip())):
        raise HTTPException(400, "Escribe el departamento, la provincia y el distrito.")
    try:
        return clima.clima_para_fumigar(departamento, provincia, distrito)
    except clima.ClimaError as e:
        raise HTTPException(503, str(e))
    except Exception:
        logging.exception("Fallo al consultar el clima")
        raise HTTPException(502, "No pudimos consultar el clima. Inténtalo más tarde.")


app.mount("/static", StaticFiles(directory=RAIZ / "frontend"), name="static")
app.mount("/imagenes", StaticFiles(directory=RAIZ / "imagenes"), name="imagenes")


@app.get("/")
def inicio():
    # Sin caché: así el navegador siempre muestra la última versión de la página
    return FileResponse(RAIZ / "frontend" / "index.html", headers={"Cache-Control": "no-store"})
