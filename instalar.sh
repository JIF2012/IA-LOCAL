#!/bin/sh
# Instala o actualiza la IA local en ZimaOS (o cualquier equipo con Docker).
# Uso:  sudo sh instalar.sh
set -e
cd "$(dirname "$0")"

if docker compose version > /dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose > /dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "ERROR: no se encontró 'docker compose'. ¿Estás en ZimaOS con Docker activo?" >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  CLAVE=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
  sed -i "s/^CONVERSOR_API_KEY=.*/CONVERSOR_API_KEY=$CLAVE/" .env
  echo "Se creó .env con una clave nueva para el conversor."
fi

mkdir -p /DATA/AppData/ia-local/ollama /DATA/AppData/ia-local/open-webui

echo "==> Descargando Ollama y Open WebUI..."
$COMPOSE pull ollama modelos open-webui

echo "==> Preparando el conversor de documentos..."
if ! $COMPOSE pull conversor 2> /dev/null; then
  echo "    No hay imagen publicada; se construye en este equipo (puede tardar 10-20 min la primera vez)."
  $COMPOSE build conversor
fi

echo "==> Iniciando..."
$COMPOSE up -d

IP=$(hostname -I 2> /dev/null | awk '{print $1}')
PUERTO=$(grep -E '^PUERTO_WEB=' .env | cut -d= -f2)
echo
echo "Listo. Abre http://${IP:-IP-DEL-ZIMA}:${PUERTO:-3000} y crea la cuenta de administrador."
echo "La primera vez se descargan los modelos (varios GB). Para ver el avance:"
echo "    sudo docker logs -f ia-descarga-modelos"
