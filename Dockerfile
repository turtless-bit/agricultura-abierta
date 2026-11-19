# PapaQhawaq: imagen para desplegar en cualquier servidor (VPS, Render, Railway, Fly.io...)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend backend
COPY frontend frontend
COPY imagenes imagenes
COPY models models

# Usuario sin privilegios
RUN useradd --create-home papaqhawaq && chown -R papaqhawaq /app
USER papaqhawaq

EXPOSE 8000
# La clave de Google se pasa como variable de entorno GOOGLE_MAPS_API_KEY (nunca dentro de la imagen)
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
