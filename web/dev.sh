#!/usr/bin/env bash
# =============================================================
#  scadaMtto web - desarrollo en contenedor
#
#  Corre Compose desde infraestructura/ SIN -f, para que se cargue
#  docker-compose.override.yml (codigo por bind-mount, recarga sola).
#
#    ./dev.sh up | build | down | logs | ps | shell
#
#  Sin Docker:  npm install && DATOS_DEMO=si npm run dev
# =============================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA="$RAIZ/infraestructura"

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
morir() { rojo "ERROR: $*"; exit 1; }

command -v docker >/dev/null 2>&1 || morir "Docker no esta instalado o no esta en el PATH."
docker info >/dev/null 2>&1 || morir "El demonio de Docker no responde. ¿Docker Desktop esta abierto?"
[[ -f "$INFRA/.env" ]] || morir "Falta $INFRA/.env. Generalo con:  ./deploy.sh --setup --sin-pull"

cd "$INFRA"
case "${1:-}" in
    up)    docker compose up "${@:2}" ;;
    build) docker compose up --build "${@:2}" ;;
    down)  docker compose down "${@:2}" ;;   # nunca con -v
    logs)  docker compose logs -f "${@:2}" ;;
    ps)    docker compose ps ;;
    shell) docker compose exec app sh ;;
    *)     echo "Uso: ./dev.sh up|build|down|logs|ps|shell   (http://localhost:3108)" ;;
esac
