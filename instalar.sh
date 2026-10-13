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

GPU_COMPOSE="COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml"
if docker info 2> /dev/null | grep -qi nvidia; then
  echo "==> Tarjeta NVIDIA disponible para Docker: la IA usará la tarjeta gráfica."
  grep -q '^COMPOSE_FILE=' .env || echo "$GPU_COMPOSE" >> .env
else
  echo "==> No se detectó una tarjeta NVIDIA usable por Docker: la IA usará el procesador (más lento)."
  sed -i '/^COMPOSE_FILE=/d' .env
fi

mkdir -p /DATA/AppData/ia-local/ollama /DATA/AppData/ia-local/open-webui

echo "==> Descargando Ollama y Open WebUI..."
$COMPOSE pull ollama modelos open-webui

echo "==> Preparando el conversor de documentos..."
if ! $COMPOSE pull conversor 2> /dev/null; then
  echo "    No hay imagen publicada; se construye en este equipo (puede tardar 10-20 min la primera vez)."
  # "docker build" funciona aunque Docker no tenga el plugin buildx (que "compose build" exige).
  docker build -t ghcr.io/jif2012/ia-local-conversor:latest ./conversor
fi

echo "==> Iniciando..."
if ! $COMPOSE up -d; then
  grep -q '^COMPOSE_FILE=' .env || exit 1
  echo "    No se pudo iniciar usando la tarjeta gráfica; se reintenta solo con el procesador."
  sed -i '/^COMPOSE_FILE=/d' .env
  $COMPOSE up -d
fi

IP=$(hostname -I 2> /dev/null | awk '{print $1}')
PUERTO=$(grep -E '^PUERTO_WEB=' .env | cut -d= -f2)
echo
echo "Listo. Abre http://${IP:-IP-DEL-ZIMA}:${PUERTO:-3000} y crea la cuenta de administrador."
echo "La primera vez se descargan los modelos (varios GB). Para ver el avance:"
echo "    sudo docker logs -f ia-descarga-modelos"
