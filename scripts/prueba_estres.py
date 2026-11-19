"""Prueba de estrés del diagnóstico de PapaQhawaq (fila «Ejecuciones sin fallo» de la Tabla 8).

Envía muchas fotos a /api/diagnosticar, varias a la vez (como si varios celulares usaran la app al mismo
tiempo), y cuenta cuántas respuestas fueron correctas y cuánto tardaron.

Uso (con la web corriendo, por ejemplo con ./iniciar.sh):
    python3 scripts/prueba_estres.py                         # 1000 envíos, 10 a la vez, a localhost:8000
    python3 scripts/prueba_estres.py --total 200 --simultaneos 20
    python3 scripts/prueba_estres.py --url https://papaqhawaq.turtless.app --total 100

Una ejecución es correcta si el servidor responde 200 con un diagnóstico («clase»); el tiempo se informa
aparte (porcentaje por debajo de --limite-ms, 1000 ms por defecto, la meta de la HE2).
Por defecto las fotos se achican a 512 px antes de enviarlas, igual que hace la app (necesita Pillow);
con --originales se envían tal cual. Al final guarda el detalle en prueba_estres.csv.
"""
import argparse, csv, mimetypes, random, statistics, time, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib import request, error
import json

RAIZ = Path(__file__).resolve().parent.parent
CARPETAS = ["fotos", "3fotosrancha", "3fotosalternariosis"]
EXT = {".jpg", ".jpeg", ".png", ".webp"}


def como_app(ruta: Path) -> bytes:
    """Igual que la página: lado mayor de 512 px y JPEG de calidad 0,85."""
    import io
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    im.thumbnail((512, 512))
    b = io.BytesIO(); im.save(b, "JPEG", quality=85)
    return b.getvalue()


def cuerpo_multipart(nombre: str, contenido: bytes, tipo: str) -> tuple[bytes, str]:
    limite = uuid.uuid4().hex
    datos = (f"--{limite}\r\nContent-Disposition: form-data; name=\"foto\"; filename=\"{nombre}\"\r\n"
             f"Content-Type: {tipo}\r\n\r\n").encode() + contenido + f"\r\n--{limite}--\r\n".encode()
    return datos, f"multipart/form-data; boundary={limite}"


def enviar(url: str, foto: tuple, limite_ms: float) -> dict:
    nombre, contenido, tipo_img = foto
    datos, tipo = cuerpo_multipart(nombre, contenido, tipo_img)
    req = request.Request(f"{url}/api/diagnosticar?cultivo=papa", data=datos, method="POST",
                          headers={"Content-Type": tipo, "User-Agent": "prueba-estres-papaqhawaq"})
    t0 = time.perf_counter()
    try:
        with request.urlopen(req, timeout=30) as r:
            cuerpo = r.read(); codigo = r.status
        ms = (time.perf_counter() - t0) * 1000
        clase = json.loads(cuerpo).get("clase")
        ok = codigo == 200 and bool(clase)
        return {"foto": nombre, "codigo": codigo, "ms": round(ms, 1), "clase": clase, "ok": ok,
                "a_tiempo": ok and ms <= limite_ms, "motivo": "" if ok else "sin diagnóstico"}
    except error.HTTPError as e:
        return {"foto": nombre, "codigo": e.code, "ms": round((time.perf_counter() - t0) * 1000, 1),
                "clase": "", "ok": False, "a_tiempo": False, "motivo": f"HTTP {e.code}"}
    except Exception as e:  # sin conexión, tiempo agotado, etc.
        return {"foto": nombre, "codigo": 0, "ms": round((time.perf_counter() - t0) * 1000, 1),
                "clase": "", "ok": False, "a_tiempo": False, "motivo": type(e).__name__}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--total", type=int, default=1000, help="número de diagnósticos (por defecto 1000)")
    ap.add_argument("--simultaneos", type=int, default=10, help="envíos al mismo tiempo (por defecto 10)")
    ap.add_argument("--limite-ms", type=float, default=1000, help="tiempo máximo para contar como correcto")
    ap.add_argument("--salida", default="prueba_estres.csv")
    ap.add_argument("--originales", action="store_true", help="enviar las fotos sin achicar")
    a = ap.parse_args()

    fotos = [p for c in CARPETAS for p in (RAIZ / c).rglob("*") if p.suffix.lower() in EXT]
    if not fotos:
        raise SystemExit(f"No encontré fotos en {', '.join(CARPETAS)}")
    random.seed(1)
    elegidas = [random.choice(fotos) for _ in range(a.total)]
    cache = {}
    def preparar(p):
        if p not in cache:
            cache[p] = ((p.name, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/jpeg") if a.originales
                        else (p.stem + ".jpg", como_app(p), "image/jpeg"))
        return cache[p]
    lista = [preparar(p) for p in elegidas]
    kb = statistics.mean(len(x[1]) for x in lista) / 1024
    print(f"Enviando {a.total} fotos a {a.url}, {a.simultaneos} a la vez "
          f"({len(cache)} fotos distintas, {kb:.0f} KB en promedio{'' if a.originales else ', achicadas como la app'})…")

    res, t0 = [], time.perf_counter()
    with ThreadPoolExecutor(max_workers=a.simultaneos) as ex:
        for i, f in enumerate(as_completed([ex.submit(enviar, a.url, p, a.limite_ms) for p in lista]), 1):
            res.append(f.result())
            if i % max(1, a.total // 10) == 0:
                print(f"  {i}/{a.total}")
    dur = time.perf_counter() - t0

    ok = sum(r["ok"] for r in res)
    ms = sorted(r["ms"] for r in res if r["codigo"] == 200)
    print("\n================ RESULTADO ================")
    at = sum(r["a_tiempo"] for r in res)
    print(f"Ejecuciones sin fallo: {ok} de {len(res)} = {ok / len(res) * 100:.1f} %   (meta ≥ 99 %)")
    print(f"Respondidas en ≤ {a.limite_ms:.0f} ms: {at} de {len(res)} = {at / len(res) * 100:.1f} %")
    if ms:
        p95 = ms[min(len(ms) - 1, int(len(ms) * 0.95))]
        print(f"Tiempo de respuesta con {a.simultaneos} a la vez: mediana {statistics.median(ms):.0f} ms · "
              f"promedio {statistics.mean(ms):.0f} ms · 95 % por debajo de {p95:.0f} ms · máximo {ms[-1]:.0f} ms")
    print(f"Duración total: {dur:.0f} s ({len(res) / dur:.1f} diagnósticos por segundo)")
    fallos = {}
    for r in res:
        if not r["ok"]: fallos[r["motivo"]] = fallos.get(r["motivo"], 0) + 1
    if fallos:
        print("Fallos por motivo:", ", ".join(f"{k}: {v}" for k, v in fallos.items()))
    with open(a.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0])); w.writeheader(); w.writerows(res)
    print(f"Detalle de cada envío: {a.salida}")


if __name__ == "__main__":
    main()
