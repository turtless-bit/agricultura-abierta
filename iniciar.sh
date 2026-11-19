#!/usr/bin/env bash
# Reconstruye la imagen y (re)inicia PapaQhawaq en http://localhost:8000
# Para y borra antes cualquier contenedor viejo de PapaQhawaq (por nombre o por ocupar el puerto).
#   ./iniciar.sh            -> puerto 8000
#   PUERTO=8080 ./iniciar.sh
#   ./iniciar.sh --parar    -> solo detiene la web
set -euo pipefail
cd "$(dirname "$0")"

IMAGEN=papaqhawaq
NOMBRE=papaqhawaq
PUERTO="${PUERTO:-8000}"

# Contenedores viejos: los llamados "papaqhawaq" y los de esta imagen que ocupan el puerto
viejos=$( { docker ps -aq --filter "name=^/${NOMBRE}$"; docker ps -q --filter "publish=${PUERTO}"; } | sort -u)
for id in $viejos; do
  imagen=$(docker inspect -f '{{.Config.Image}}' "$id")
  nombre=$(docker inspect -f '{{.Name}}' "$id")
  if [[ "$imagen" == "$IMAGEN"* || "$nombre" == "/$NOMBRE" ]]; then
    echo "Parando contenedor viejo ${nombre#/} ($imagen)"
    docker rm -f "$id" >/dev/null
  else
    echo "El puerto $PUERTO lo usa otro contenedor (${nombre#/}, imagen $imagen), que no es de PapaQhawaq."
    echo "Usa otro puerto, por ejemplo:  PUERTO=8080 ./iniciar.sh"
    exit 1
  fi
done

[[ "${1:-}" == "--parar" ]] && { echo "PapaQhawaq detenido."; exit 0; }

docker build -t "$IMAGEN" .

# La clave de Google se toma de .env si existe (nunca entra en la imagen)
ENV_ARGS=()
[[ -f .env ]] && ENV_ARGS=(--env-file .env)

# --restart unless-stopped: vuelve a arrancar sola al encender la computadora
docker run -d --name "$NOMBRE" --restart unless-stopped -p "${PUERTO}:8000" "${ENV_ARGS[@]}" "$IMAGEN" >/dev/null

for _ in $(seq 1 30); do
  curl -sf "http://localhost:${PUERTO}/api/estado" >/dev/null && break
  sleep 1
done
echo
echo "PapaQhawaq listo en http://localhost:${PUERTO}  ($(curl -s "http://localhost:${PUERTO}/api/estado"))"
echo "Ver registros:  docker logs -f ${NOMBRE}     Parar:  ./iniciar.sh --parar"
