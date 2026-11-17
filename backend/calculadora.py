"""Cálculo de dosis, mezcla, cantidad a comprar y costo de una aplicación."""
from __future__ import annotations

import math

# Factores de conversión a hectáreas
UNIDADES_AREA = {
    "ha": 1.0,
    "m2": 0.0001,
    "acre": 0.404686,
    "manzana": 0.7050,     # Centroamérica
    "cuadra": 0.6400,      # aproximado (varía según país)
    "fanegada": 0.6400,    # Colombia
    "yugada": 0.2500,      # aproximado
}


def calcular(producto: dict, area: float, unidad: str, capacidad_tanque_l: float,
             nivel_dosis: str = "media", aplicaciones: int | None = None,
             precio_presentacion: float | None = None) -> dict:
    if area <= 0:
        raise ValueError("El área debe ser mayor que cero.")
    if unidad not in UNIDADES_AREA:
        raise ValueError(f"Unidad de área no válida: {unidad}")
    if capacidad_tanque_l <= 0:
        raise ValueError("La capacidad del tanque debe ser mayor que cero.")

    area_ha = area * UNIDADES_AREA[unidad]
    dmin, dmax = producto["dosis_min_ha"], producto["dosis_max_ha"]
    dosis_ha = {"minima": dmin, "maxima": dmax}.get(nivel_dosis, (dmin + dmax) / 2)

    n_apl = aplicaciones or producto["aplicaciones_max_ciclo"]
    n_apl = max(1, min(n_apl, producto["aplicaciones_max_ciclo"]))

    agua_ha = producto["agua_l_ha"]
    producto_por_aplicacion = dosis_ha * area_ha
    agua_por_aplicacion = agua_ha * area_ha
    tanques = math.ceil(agua_por_aplicacion / capacidad_tanque_l)
    # Producto por cada tanque lleno (g o mL)
    producto_por_tanque = dosis_ha / agua_ha * capacidad_tanque_l * 1000
    producto_total = producto_por_aplicacion * n_apl

    presentacion = producto["presentacion"]
    precio = precio_presentacion if precio_presentacion is not None else producto["precio_presentacion"]
    envases = math.ceil(round(producto_total / presentacion, 6))
    costo_total = envases * precio
    costo_aplicacion = producto_por_aplicacion / presentacion * precio

    unidad_p = producto["unidad"]
    sub = "g" if unidad_p == "kg" else "mL"

    pasos = [
        "Use equipo de protección: guantes de nitrilo, mascarilla, gafas, botas y ropa de manga larga.",
        "Calibre su mochila/equipo con agua limpia para confirmar que aplica unos "
        f"{agua_ha / 10:.0f} L por cada 1.000 m².",
        f"Llene el tanque hasta la mitad con agua limpia.",
        (f"Pese {producto_por_tanque:.0f} {sub} del producto y disuélvalo primero en un balde con poca agua (premezcla)."
         if unidad_p == "kg" else
         f"Mida {producto_por_tanque:.0f} {sub} del producto con una probeta o jeringa graduada."),
        f"Vierta la mezcla al tanque, complete con agua hasta {capacidad_tanque_l:.0f} L y agite bien.",
        producto["modo_aplicacion"],
        "Aplique en horas frescas (temprano o al final de la tarde), sin viento fuerte ni lluvia prevista en 2-4 horas.",
        f"Repita cada {producto['intervalo_dias']} días si persisten condiciones favorables "
        f"(máximo {producto['aplicaciones_max_ciclo']} aplicaciones por cosecha).",
        f"No coseche antes de {producto['carencia_dias']} días de la última aplicación (periodo de carencia) "
        f"y no ingrese al lote antes de {producto['reingreso_horas']} horas.",
        "Lave el equipo después de usarlo y no vierta sobrantes en ríos ni fuentes de agua. Perfore y entregue los envases vacíos.",
    ]

    return {
        "area_ha": round(area_ha, 4),
        "dosis_ha": dosis_ha,
        "unidad_producto": unidad_p,
        "producto_por_aplicacion": round(producto_por_aplicacion, 3),
        "agua_por_aplicacion_l": round(agua_por_aplicacion, 1),
        "tanques_por_aplicacion": tanques,
        "producto_por_tanque": round(producto_por_tanque, 1),
        "unidad_por_tanque": sub,
        "aplicaciones": n_apl,
        "intervalo_dias": producto["intervalo_dias"],
        "producto_total": round(producto_total, 3),
        "presentacion": presentacion,
        "envases_a_comprar": envases,
        "precio_presentacion": precio,
        "costo_por_aplicacion": round(costo_aplicacion, 2),
        "costo_total": round(costo_total, 2),
        "pasos": pasos,
    }
