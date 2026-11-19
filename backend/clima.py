"""Clima para fumigar: Google Geocoding + Google Weather API (pronóstico por hora).

La clave se lee de la variable de entorno GOOGLE_MAPS_API_KEY o del archivo .env
en la raíz del proyecto. Nunca se envía a la página.

Cada hora se evalúa con 5 factores: viento, temperatura, humedad, lluvia/rocío e
inversión térmica (estimada: cielo despejado + calma + noche o primeras horas).
Los umbrales son referenciales y están en UMBRALES para ajustarlos con un agrónomo.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HORAS = 72
TTL_CACHE = 30 * 60  # segundos
PERU = timezone(timedelta(hours=-5))

UMBRALES = {
    "viento_min": 3,          # km/h: por debajo, aire en calma (deriva impredecible / inversión)
    "viento_ideal_max": 10,   # km/h
    "viento_max": 15,         # km/h: por encima, no fumigar
    "rafaga_max": 20,         # km/h
    "temp_min": 5,            # °C
    "temp_ideal_max": 25,     # °C
    "temp_max": 30,           # °C
    "hr_min": 40,             # %: por debajo, las gotas se evaporan
    "hr_ideal_min": 50,       # %
    "hr_max": 95,             # %: hoja mojada
    "lluvia_prob_max": 60,    # %: no fumigar
    "lluvia_prob_aviso": 30,  # %
    "lluvia_mm_max": 0.5,     # mm en la hora
    "tormenta_max": 60,       # %: tormenta en esta hora o la siguiente -> no fumigar
    "tormenta_aviso": 40,     # %: tormenta posible en las horas de secado -> con cuidado
    "horas_secado": 3,        # horas sin lluvia después de aplicar
    "rocio_delta": 2,         # °C entre temperatura y punto de rocío
    "nubes_inversion": 20,    # %
}


class ClimaError(Exception):
    """Error que se puede mostrar al agricultor."""


def _clave() -> str | None:
    clave = os.environ.get("GOOGLE_MAPS_API_KEY")
    if clave:
        return clave.strip()
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if linea.strip().startswith("GOOGLE_MAPS_API_KEY="):
                return linea.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def disponible() -> bool:
    return _clave() is not None


def _get(url: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": "PapaQhawaq/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {e.code} en {url}: {cuerpo}") from e


_cache: dict[str, tuple[float, dict]] = {}


def _cacheado(clave: str, fn):
    ahora = time.time()
    if clave in _cache and ahora - _cache[clave][0] < TTL_CACHE:
        return _cache[clave][1]
    valor = fn()
    _cache[clave] = (ahora, valor)
    return valor


def geocodificar(departamento: str, provincia: str, distrito: str) -> dict:
    clave = _clave()
    intentos = [
        ", ".join(x for x in (distrito, provincia, departamento, "Perú") if x),
        ", ".join(x for x in (provincia, departamento, "Perú") if x),
    ]
    # Geocoding API v4 (la que admite la clave de demostración de Maps)
    for direccion in intentos:
        d = _get("https://geocode.googleapis.com/v4beta/geocode/address/" + urllib.parse.quote(direccion, safe=""),
                 {"key": clave, "languageCode": "es", "regionCode": "PE"})
        for r in d.get("results", []):
            loc = r.get("location") or {}
            if "latitude" in loc and "longitude" in loc:
                return {"lat": loc["latitude"], "lng": loc["longitude"],
                        "lugar": r.get("formattedAddress", direccion), "buscado": direccion}
    raise ClimaError("No encontramos ese lugar. Revisa el departamento, la provincia y el distrito.")


def pronostico_horas(lat: float, lng: float) -> list[dict]:
    clave = _clave()
    horas: list[dict] = []
    token = None
    while len(horas) < HORAS:
        params = {"key": clave, "location.latitude": lat, "location.longitude": lng,
                  "hours": HORAS, "pageSize": 24, "languageCode": "es", "unitsSystem": "METRIC"}
        if token:
            params["pageToken"] = token
        d = _get("https://weather.googleapis.com/v1/forecast/hours:lookup", params)
        horas.extend(d.get("forecastHours", []))
        token = d.get("nextPageToken")
        if not token:
            break
    return horas[:HORAS]


DIRECCIONES = {
    "NORTH": "norte", "NORTH_NORTHEAST": "norte-noreste", "NORTHEAST": "noreste", "EAST_NORTHEAST": "este-noreste",
    "EAST": "este", "EAST_SOUTHEAST": "este-sureste", "SOUTHEAST": "sureste", "SOUTH_SOUTHEAST": "sur-sureste",
    "SOUTH": "sur", "SOUTH_SOUTHWEST": "sur-suroeste", "SOUTHWEST": "suroeste", "WEST_SOUTHWEST": "oeste-suroeste",
    "WEST": "oeste", "WEST_NORTHWEST": "oeste-noroeste", "NORTHWEST": "noroeste", "NORTH_NORTHWEST": "norte-noroeste",
}


def _num(d: dict, *ruta, defecto=None):
    for k in ruta:
        if not isinstance(d, dict) or k not in d:
            return defecto
        d = d[k]
    return d if isinstance(d, (int, float)) else defecto


def _hora_local(h: dict) -> datetime:
    dt = h.get("displayDateTime") or {}
    if "year" in dt and "hours" in dt:
        return datetime(dt["year"], dt["month"], dt["day"], dt.get("hours", 0), dt.get("minutes", 0))
    inicio = (h.get("interval") or {}).get("startTime")
    if inicio:
        return datetime.fromisoformat(inicio.replace("Z", "+00:00")).astimezone(PERU).replace(tzinfo=None)
    raise ValueError("Hora sin fecha")


def evaluar(horas: list[dict]) -> list[dict]:
    U = UMBRALES
    filas = []
    for h in horas:
        filas.append({
            "hora": _hora_local(h),
            "dia": bool(h.get("isDaytime", True)),
            "temp": _num(h, "temperature", "degrees"),
            "rocio": _num(h, "dewPoint", "degrees"),
            "hr": _num(h, "relativeHumidity"),
            "viento": _num(h, "wind", "speed", "value"),
            "rafaga": _num(h, "wind", "gust", "value"),
            "dir": DIRECCIONES.get(((h.get("wind") or {}).get("direction") or {}).get("cardinal"), None),
            "dir_grados": _num(h, "wind", "direction", "degrees"),
            "lluvia_prob": _num(h, "precipitation", "probability", "percent", defecto=0),
            "lluvia_mm": _num(h, "precipitation", "qpf", "quantity", defecto=0),
            "nubes": _num(h, "cloudCover"),
            "tormenta": _num(h, "thunderstormProbability", defecto=0),
            "cielo": ((h.get("weatherCondition") or {}).get("description") or {}).get("text"),
        })

    resultado = []
    for i, f in enumerate(filas):
        no, aviso = [], []
        # 1. Viento
        v, g = f["viento"], f["rafaga"]
        if v is not None:
            if v > U["viento_max"]:
                no.append(f"Viento fuerte ({v:.0f} km/h): el producto se va con el viento y cae fuera de la chacra")
            elif g is not None and g > U["rafaga_max"]:
                no.append(f"Ráfagas fuertes ({g:.0f} km/h): el producto se va con el viento y cae fuera de la chacra")
            elif v > U["viento_ideal_max"]:
                aviso.append(f"Viento moderado ({v:.0f} km/h): parte del producto puede desviarse; fumiga a favor del viento y cerca de las plantas")
        # 2. Temperatura
        t = f["temp"]
        if t is not None:
            if t > U["temp_max"]:
                no.append(f"Mucho calor ({t:.0f} °C): las gotas se evaporan antes de llegar a la hoja y la planta puede quemarse")
            elif t > U["temp_ideal_max"]:
                aviso.append(f"Calor ({t:.0f} °C): parte del producto se evapora; mejor temprano o al atardecer")
            elif t < U["temp_min"]:
                aviso.append(f"Mucho frío ({t:.0f} °C): la planta absorbe menos el producto")
        # 3. Humedad
        hr = f["hr"]
        if hr is not None:
            if hr < U["hr_min"]:
                no.append(f"Aire muy seco ({hr:.0f} %): las gotas se evaporan antes de llegar a la hoja")
            elif hr < U["hr_ideal_min"]:
                aviso.append(f"Aire algo seco ({hr:.0f} %): parte de las gotas se evapora")
            elif hr > U["hr_max"]:
                aviso.append(f"Humedad muy alta ({hr:.0f} %): la hoja húmeda tarda en secar y el producto puede escurrirse")
        # 4. Lluvia (esta hora y las de secado) y rocío
        siguientes = filas[i:i + 1 + U["horas_secado"]]
        prob = max((x["lluvia_prob"] or 0) for x in siguientes)
        mm = sum((x["lluvia_mm"] or 0) for x in siguientes)
        if prob >= U["lluvia_prob_max"] or mm > U["lluvia_mm_max"]:
            no.append(f"Lluvia probable en las próximas {U['horas_secado']} h ({prob:.0f} %): lavaría el producto antes de que se seque")
        elif max((x["tormenta"] or 0) for x in filas[i:i + 2]) >= U["tormenta_max"]:
            no.append("Posible tormenta eléctrica: es peligroso estar en el campo y la lluvia lavaría el producto")
        elif prob >= U["lluvia_prob_aviso"]:
            aviso.append(f"Puede llover ({prob:.0f} %): si llueve antes de {U['horas_secado']} h, el producto se lava")
        elif max((x["tormenta"] or 0) for x in siguientes) >= U["tormenta_aviso"]:
            aviso.append(f"Puede haber tormenta en las próximas {U['horas_secado']} h: la lluvia lavaría el producto")
        if t is not None and f["rocio"] is not None and t - f["rocio"] <= U["rocio_delta"]:
            aviso.append("Hojas mojadas por rocío: el producto se diluye y escurre de la hoja")
        # 5. Inversión térmica (estimada)
        temprano = 5 <= f["hora"].hour <= 8
        if (f["nubes"] is not None and f["nubes"] < U["nubes_inversion"]
                and v is not None and v < U["viento_min"] and (not f["dia"] or temprano)):
            no.append("Posible inversión térmica (cielo despejado y sin viento): el producto queda flotando en el aire y no baja a las hojas")
        elif v is not None and v < U["viento_min"]:
            aviso.append(f"Casi sin viento ({v:.0f} km/h): las gotas más finas pueden quedarse flotando; usa gotas más gruesas")
        if not f["dia"]:
            no.append("Es de noche: no se ve bien dónde cae el producto y suele haber rocío y aire quieto")

        estado = "no" if no else ("aviso" if aviso else "ok")
        resultado.append({
            "fecha": f["hora"].strftime("%Y-%m-%d"),
            "hora": f["hora"].strftime("%H:%M"),
            "estado": estado,
            "motivos": no + aviso,
            "temp": t, "hr": hr, "viento": v, "rafaga": g, "dir": f["dir"],
            "lluvia_prob": f["lluvia_prob"], "tormenta": f["tormenta"], "rocio": f["rocio"], "nubes": f["nubes"], "cielo": f["cielo"],
        })
    return resultado


def ventanas(horas: list[dict], minimo: int = 1) -> list[dict]:
    """Bloques de horas seguidas aptas ('ok') de al menos `minimo` horas.
    Una sola hora buena también cuenta: así coincide con las horas en verde del calendario."""
    res, actual = [], []
    for h in horas + [{"estado": "fin"}]:
        if h["estado"] == "ok" and (not actual or actual[-1]["fecha"] == h["fecha"]):
            actual.append(h)
            continue
        if len(actual) >= minimo:
            fin = datetime.strptime(actual[-1]["hora"], "%H:%M") + timedelta(hours=1)
            res.append({"fecha": actual[0]["fecha"], "desde": actual[0]["hora"],
                        "hasta": fin.strftime("%H:%M"), "horas": len(actual)})
        actual = [h] if h["estado"] == "ok" else []
    return res


def _nivel(valor: float, medio: float, alto: float) -> str:
    return "alto" if valor >= alto else "medio" if valor >= medio else "bajo"


def riesgo_enfermedades(horas: list[dict]) -> dict:
    """Riesgo de rancha y alternariosis para los próximos días (reglas simplificadas, referenciales).

    Rancha (Phytophthora infestans), inspirado en los periodos de Wallin / SimCast (CIP):
      horas SEGUIDAS con humedad >= 90 % (o lluvia) y temperatura entre 7 y 27 °C en un mismo día.
      >= 10 h: alto · 6-9 h: medio · menos: bajo.
    Alternariosis (Alternaria solani), inspirado en TOMCAST:
      horas de hoja mojada (humedad >= 90 %, rocío o lluvia) por día y su temperatura media
      dan "valores de severidad" diarios (0-4); se suman en los días del pronóstico.
      >= 5: alto · 3-4: medio · menos: bajo.
    """
    por_dia: dict[str, list[dict]] = {}
    for h in horas:
        por_dia.setdefault(h["fecha"], []).append(h)

    def mojada(h):
        return ((h["hr"] or 0) >= 90 or (h["lluvia_prob"] or 0) >= 50
                or (h["temp"] is not None and h["rocio"] is not None and h["temp"] - h["rocio"] <= 2))

    # Rancha
    mejor_racha, dia_racha = 0, None
    for fecha, hs in por_dia.items():
        racha = 0
        for h in hs:
            favorable = ((h["hr"] or 0) >= 90 or (h["lluvia_prob"] or 0) >= 50) and h["temp"] is not None and 7 <= h["temp"] <= 27
            racha = racha + 1 if favorable else 0
            if racha > mejor_racha:
                mejor_racha, dia_racha = racha, fecha
    rancha = {"nivel": _nivel(mejor_racha, 6, 10), "horas": mejor_racha, "fecha": dia_racha,
              "explicacion": (f"{mejor_racha} {'hora' if mejor_racha == 1 else 'horas seguidas'} de humedad alta con temperatura templada"
                              if mejor_racha else "Pocas horas de humedad alta")}

    # Alternariosis (tabla tipo TOMCAST: horas de hoja mojada según temperatura)
    tabla = [  # (temp mínima, temp máxima, [límites de horas para DSV 1, 2, 3, 4])
        (13, 17.99, [7, 16, 21, 99]), (18, 20.99, [4, 9, 16, 23]),
        (21, 25.99, [3, 6, 13, 21]), (26, 29.99, [4, 9, 16, 23]),
    ]
    dsv_total, dias = 0, 0
    for hs in por_dia.values():
        mojadas = [h for h in hs if mojada(h) and h["temp"] is not None]
        if not mojadas:
            dias += 1
            continue
        tm = sum(h["temp"] for h in mojadas) / len(mojadas)
        n = len(mojadas)
        for tmin, tmax, lim in tabla:
            if tmin <= tm <= tmax:
                dsv_total += sum(1 for x in lim if n >= x)
                break
        dias += 1
    alternaria = {"nivel": _nivel(dsv_total, 3, 5), "valor": dsv_total, "dias": dias,
                  "explicacion": f"Índice de severidad {dsv_total} en {dias} días (hojas mojadas con calor)"}
    return {"tizon_tardio": rancha, "tizon_temprano": alternaria}


def clima_para_fumigar(departamento: str, provincia: str, distrito: str) -> dict:
    if not disponible():
        raise ClimaError("El pronóstico del clima no está disponible por ahora.")
    clave = "|".join(x.strip().lower() for x in (departamento, provincia, distrito))

    def calcular():
        lugar = geocodificar(departamento, provincia, distrito)
        horas = evaluar(pronostico_horas(lugar["lat"], lugar["lng"]))
        return {"lugar": lugar, "horas": horas, "ventanas": ventanas(horas), "umbrales": UMBRALES,
                "riesgo": riesgo_enfermedades(horas)}

    return _cacheado(clave, calcular)
