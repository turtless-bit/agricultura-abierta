# PapaQhawaq 🌱

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

## Modelos de IA (papa)

Sin modelo, la web funciona en **modo demo** (estimación por color, no fiable).

### Modelos actuales: alternariosis y rancha (entrenados en Kaggle)

Son dos modelos binarios que se ejecutan en el servidor con LiteRT (incluido en `requirements.txt`, no hace falta TensorFlow):

| Modelo | Pregunta | Negativos de entrenamiento |
|---|---|---|
| `papa_alternariosis.tflite` | ¿Tiene alternariosis? | hojas sanas, rancha, septoria y otras afecciones |
| `papa_lancha.tflite` | ¿Tiene rancha? | hojas sanas, alternariosis, septoria y otras afecciones |

Al terminar el notebook de Kaggle, descargar de **Output** y copiar en `models/`:

```
models/papa_alternariosis.tflite
models/papa_alternariosis_etiquetas.json   (incluye el umbral elegido en validación)
models/papa_lancha.tflite
models/papa_lancha_etiquetas.json
```

La web combina los dos resultados:

| Alternariosis | Rancha | Resultado en la web |
|---|---|---|
| sí | no | Alternariosis |
| no | sí | Rancha |
| sí | sí | Resultado dudoso (pide otra foto) |
| no | no | No se detectó alternariosis ni rancha (sana u otro problema) |

Para comprobarlo: arrancar el servidor y abrir `/api/estado`; debe decir `"modo_modelo": "ia"`.
La carpeta de modelos se puede cambiar con la variable de entorno `MODELOS_DIR`.

### Modelo opcional "¿está sana?" (`papa_sana`)

Se entrena con `entrenar_papa_sana_v3.ipynb` en Kaggle (por defecto solo entrena este modelo).
Si `models/papa_sana.tflite` y `papa_sana_etiquetas.json` existen, cuando no hay alternariosis ni rancha la web dice
**"Planta sana"** o **"La hoja tiene un problema que la app no reconoce"** (y recomienda consultar a un agrónomo).
Sin este modelo, la web dice "No se detectó alternariosis ni rancha", como antes.
Su umbral se elige con precisión ≥ 98 % en validación, para no llamar sana a una hoja enferma.

### IA en el celular y modo sin internet

Los tres modelos (`papa_es_papa`, `papa_alternariosis` y `papa_lancha`) también corren **dentro del navegador**
con LiteRT.js (`frontend/vendor/litert/`). La primera vez que se abre la página con internet, el service worker
(`frontend/sw.js`, servido en `/sw.js`) guarda la página, los modelos, el motor de IA y las imágenes de los productos.
Desde entonces el diagnóstico y las recomendaciones funcionan **sin internet**; solo el clima la necesita.
En Chrome se puede instalar con *Agregar a pantalla de inicio* (`frontend/manifest.webmanifest`).
Si el navegador no puede correr la IA, la página usa `/api/diagnosticar` en el servidor.

Al copiar modelos nuevos de Kaggle hay que fijar su tamaño de lote en 1 (LiteRT.js no acepta lotes variables;
los pesos no cambian):

```bash
pip install tflite
python scripts/fijar_lote_tflite.py models/papa_*.tflite
```

Cuando cambian los modelos o la página, el service worker lo detecta solo y los celulares descargan la versión nueva.

### Modelo antiguo de 3 clases (PlantVillage)

Si no están los modelos anteriores, se usa `models/papa_modelo.keras` si existe:

1. Descargar el dataset PlantVillage (p. ej. desde Kaggle) y copiar las carpetas
   `Potato___Early_blight`, `Potato___Late_blight` y `Potato___healthy` dentro de `datos/papa/`.
2. Instalar TensorFlow y entrenar:
   ```bash
   .venv/bin/pip install -r requirements-ia.txt
   .venv/bin/python -m backend.entrenar --datos datos/papa --epocas 10
   ```
3. Se generan `models/papa_modelo.keras` y `models/clases.json`. Reiniciar el servidor y la web pasará a modo **IA**.

## Quechua (botón Español / Quechua)

La cabecera tiene un botón para cambiar la app al quechua chanka. Las traducciones están en `frontend/qu.js`
(`EXACTOS`: textos fijos; `PATRONES`: textos con números). La página reemplaza en pantalla cada texto en castellano
por su traducción, también los que se crean después (diagnóstico, productos, clima). Las fichas técnicas y hojas
de seguridad (PDF) no se traducen. El idioma elegido se recuerda en el navegador.
**Es un borrador: debe revisarlo un hablante nativo.** Para corregir, se cambia el texto de la derecha en `qu.js`.

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

## Ejecutar con Docker en local

```bash
./iniciar.sh            # reconstruye, para la versión anterior y arranca en http://localhost:8000
./iniciar.sh --parar    # detiene la web
docker logs -f papaqhawaq # ver registros
```

El script usa la clave de Google de `.env` si existe. Si el puerto 8000 lo ocupa otro programa: `PUERTO=8080 ./iniciar.sh`.

## Publicación actual: https://papaqhawaq.turtless.app (desde esta computadora)

```bash
./publicar.sh           # reconstruye la web y conecta el túnel de Cloudflare
./publicar.sh --parar   # deja de publicar
docker logs -f papaqhawaq-tunel
```

- Túnel `agrosano` de Cloudflare Tunnel (nombre interno; sirve papaqhawaq.turtless.app) con su configuración en `~/.cloudflared/papaqhawaq.yml`;
  las credenciales están en `~/.cloudflared/` y nunca entran al repositorio.
- Los contenedores `papaqhawaq` y `papaqhawaq-tunel` arrancan solos al encender la computadora.
  La web solo está disponible mientras la computadora esté encendida y con internet.

## Desplegar en internet (Docker + dominio en Cloudflare)

La foto se procesa en el servidor, así que hace falta un servidor que ejecute Python.
La imagen Docker pesa ~470 MB y funciona con ~512 MB de RAM.

1. Copiar los 4 archivos del modelo en `models/` (ver "Modelos de IA").
2. Construir y probar en local:
   ```bash
   docker build -t papaqhawaq .
   docker run -p 8000:8000 -e GOOGLE_MAPS_API_KEY=tu_clave papaqhawaq
   ```
   Abrir http://localhost:8000 y subir una foto.

### Opción A: VPS propio + Cloudflare Tunnel (recomendada, siempre encendido)

Un VPS pequeño (1 CPU, 1 GB) cuesta unos 4-6 USD/mes. Con Cloudflare Tunnel no hace falta abrir puertos
ni configurar certificados: Cloudflare da el HTTPS.

```bash
# En el VPS (con Docker instalado), dentro de la carpeta del proyecto:
docker build -t papaqhawaq .
docker run -d --name papaqhawaq --restart unless-stopped -p 127.0.0.1:8000:8000 \
  -e GOOGLE_MAPS_API_KEY=tu_clave papaqhawaq
```

En el panel de Cloudflare: **Zero Trust → Networks → Tunnels → Create a tunnel** (tipo *Cloudflared*),
seguir las instrucciones para instalar `cloudflared` en el VPS y, en **Public Hostname**, poner
tu dominio (p. ej. `papa.tudominio.com`) apuntando a `http://localhost:8000`.

### Opción B: Render / Railway (sin administrar servidor)

1. Subir el proyecto a GitHub (incluidos los `.tflite` y `.json` de `models/`).
2. Crear un *Web Service* desde el repositorio; detectan el `Dockerfile` solos.
3. Añadir la variable de entorno `GOOGLE_MAPS_API_KEY`. El puerto se toma de `PORT` automáticamente.
4. En *Custom Domain* poner tu dominio y crear en Cloudflare el registro `CNAME` que indiquen.

Los planes gratuitos se "duermen" sin visitas y la primera foto puede tardar ~1 minuto.

## Estructura

```
frontend/index.html   La página completa (diseño, catálogo de productos y cálculos en JavaScript)
frontend/anterior/    Versión anterior de la página (ya no se usa)
imagenes/<producto>/  producto/ (foto), fichatecnica/ y hojadeseguridad/ (PDF)
backend/
  app.py           Sirve la página, /imagenes y la API
  modelo.py        Carga los modelos .tflite (o el antiguo / modo demo) y predice
  entrenar.py      Entrenamiento con MobileNetV2 (transfer learning)
  calculadora.py, data/catalogo.json   Calculadora antigua de la API (la página ya no los usa)
models/            Modelos entrenados (.tflite + _etiquetas.json)
Dockerfile         Imagen para desplegar
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
