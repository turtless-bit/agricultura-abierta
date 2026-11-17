# AgroSano 🌱

Web gratuita para agricultores:

1. **Diagnóstico por foto**: se sube una foto de la hoja y la IA detecta la enfermedad (por ahora solo **papa**: tizón temprano, tizón tardío o sana).
2. **Receta**: muestra los síntomas, el manejo cultural y los fungicidas recomendados.
3. **Calculadora**: con las medidas de la plantación (área total o largo × ancho, en ha, m², acres, manzanas…) calcula
   el producto por mochila, las mochilas por aplicación, cuánto comprar, los pasos para preparar y aplicar, y el costo promedio.

## Descargar y ejecutar

Requisitos: Python 3.10 o superior y Git.

```bash
git clone https://github.com/turtless-bit/agricultura-abierta.git
cd agricultura-abierta
python3 -m venv .venv
```

Linux / macOS:
```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.app:app --reload
```

Windows (PowerShell):
```powershell
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn backend.app:app --reload
```

Abrir http://localhost:8000

- `requirements.txt` es liviano y basta para usar la página.
- `requirements-ia.txt` agrega TensorFlow (~600 MB): solo hace falta para entrenar o usar el modelo de IA.
- Sin clave de Google la página funciona, pero el bloque "¿Cuándo fumigar?" dice que el clima no está disponible
  (ver la sección del clima más abajo para crear tu propio `.env`).

## Entrenar el modelo de IA (papa)

Sin modelo, la web funciona en **modo demo** (estimación por color, no fiable).

1. Descargar el dataset PlantVillage (p. ej. desde Kaggle) y copiar las carpetas
   `Potato___Early_blight`, `Potato___Late_blight` y `Potato___healthy` dentro de `datos/papa/`.
2. Instalar TensorFlow y entrenar:
   ```bash
   .venv/bin/pip install -r requirements-ia.txt
   .venv/bin/python -m backend.entrenar --datos datos/papa --epocas 10
   ```
3. Se generan `models/papa_modelo.keras` y `models/clases.json`. Reiniciar el servidor y la web pasará a modo **IA**.

## Clima para fumigar (Google Weather API)

En la sección 2, el bloque "¿Cuándo fumigar?" usa el pronóstico por hora de los próximos 3 días
para la ubicación de la chacra (departamento, provincia y distrito) y marca cada hora como
buena, con cuidado o no fumigar según viento, temperatura, humedad, lluvia/rocío e inversión
térmica estimada. Los umbrales están en `backend/clima.py` (`UMBRALES`).

Para activarlo:
1. En https://console.cloud.google.com crea un proyecto y activa la facturación.
2. En "APIs y servicios > Biblioteca" habilita **Weather API** y **Geocoding API**.
3. En "Credenciales" crea una **clave de API** y restríngela a esas dos APIs.
4. Crea el archivo `.env` en la raíz del proyecto (ver `.env.example`):
   ```
   GOOGLE_MAPS_API_KEY=tu_clave
   ```
La clave solo la usa el servidor; nunca se envía a la página. `.env` está en `.gitignore`.

## Estructura

```
frontend/index.html   La página completa (diseño, catálogo de productos y cálculos en JavaScript)
frontend/anterior/    Versión anterior de la página (ya no se usa)
imagenes/<producto>/  producto/ (foto), fichatecnica/ y hojadeseguridad/ (PDF)
backend/
  app.py           Sirve la página, /imagenes y la API
  modelo.py        Carga el modelo (o modo demo) y predice
  entrenar.py      Entrenamiento con MobileNetV2 (transfer learning)
  calculadora.py, data/catalogo.json   Calculadora antigua de la API (la página ya no los usa)
models/            Modelo entrenado
```

Los productos, dosis y precios que ve la página están en `frontend/index.html`, en el objeto `PROD`.
Para un producto real se añaden `img`, `ficha` y `hoja` con las rutas dentro de `imagenes/`.

## API

- `GET  /api/estado` – modo del modelo (`ia` / `demo`)
- `GET  /api/catalogo` – enfermedades y productos
- `POST /api/diagnosticar` – formulario con `foto` (imagen)
- `POST /api/calcular` – JSON `{producto_id, area, unidad, capacidad_tanque_l, nivel_dosis, aplicaciones, precio_presentacion}`

## Añadir cultivos o productos

Editar `backend/data/catalogo.json`. Para un nuevo cultivo hay que añadir sus enfermedades ahí y entrenar su propio modelo.

> ⚠️ Las dosis y precios son referenciales. Verifique siempre la etiqueta del producto registrado en su país y consulte a un ingeniero agrónomo.
