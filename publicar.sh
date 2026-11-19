#!/usr/bin/env bash
# Publica PapaQhawaq en internet desde esta computadora con Cloudflare Tunnel.
#   ./publicar.sh           -> (re)inicia la web y el túnel: https://papaqhawaq.turtless.app
#   ./publicar.sh --parar   -> deja de publicar (la web local sigue con ./iniciar.sh)
# Los dos contenedores arrancan solos al encender la computadora (--restart unless-stopped).
# Configuración del túnel: ~/.cloudflared/papaqhawaq.yml  (las credenciales nunca entran al repo).
set -euo pipefail
cd "$(dirname "$0")"

TUNEL=agrosano   # nombre interno del túnel en Cloudflare (no se puede renombrar)
CONTENEDOR=papaqhawaq-tunel
DOMINIO=papaqhawaq.turtless.app
CONFIG_DIR="$HOME/.cloudflared"

docker rm -f "$CONTENEDOR" >/dev/null 2>&1 || true
if [[ "${1:-}" == "--parar" ]]; then
  echo "Túnel detenido: $DOMINIO ya no es accesible."
  exit 0
fi

[[ -f "$CONFIG_DIR/papaqhawaq.yml" ]] || { echo "Falta $CONFIG_DIR/papaqhawaq.yml"; exit 1; }

./iniciar.sh

# --network host: el túnel llega a la web por localhost:8000
# --user: para poder leer las credenciales de ~/.cloudflared (solo lectura)
docker run -d --name "$CONTENEDOR" --restart unless-stopped --network host \
  --user "$(id -u):$(id -g)" -v "$CONFIG_DIR:/etc/cloudflared:ro" \
  cloudflare/cloudflared:latest tunnel --no-autoupdate --config /etc/cloudflared/papaqhawaq.yml run "$TUNEL" >/dev/null

echo -n "Conectando el túnel"
for _ in $(seq 1 30); do
  docker logs "$CONTENEDOR" 2>&1 | grep -q "Registered tunnel connection" && break
  echo -n "."; sleep 1
done
echo
if docker logs "$CONTENEDOR" 2>&1 | grep -q "Registered tunnel connection"; then
  echo "Publicado en https://$DOMINIO"
else
  echo "El túnel no se conectó. Revisa:  docker logs $CONTENEDOR"; exit 1
fi
echo "Ver registros del túnel:  docker logs -f $CONTENEDOR      Dejar de publicar:  ./publicar.sh --parar"
