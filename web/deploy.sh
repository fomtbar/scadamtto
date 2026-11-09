#!/usr/bin/env bash
# =============================================================
#  scadaMtto web - despliegue (el unico comando en el servidor)
#
#  Uso:
#    ./deploy.sh              despliegue normal
#    ./deploy.sh --setup      vuelve a correr el asistente de .env
#    ./deploy.sh --rama dev   fuerza una rama (si la carpeta es un clon git)
#    ./deploy.sh --sin-pull   no toca git
#
#  Sirve en Linux y en Windows con Git Bash. Construye la imagen en el
#  mismo servidor: no hay registry, ni scp, ni ssh. Si la carpeta no es
#  un repositorio git (hoy se copia a mano), el paso de git se omite.
# =============================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA="$RAIZ/infraestructura"
ARCHIVO_ENV="$INFRA/.env"
EJEMPLO_ENV="$INFRA/.env.example"
BITACORA="$RAIZ/deploy.log"
CONTENEDOR="scadamttoweb-web"

SETUP=false
SIN_PULL=false
RAMA_FORZADA=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --setup)    SETUP=true; shift ;;
        --sin-pull) SIN_PULL=true; shift ;;
        --rama)     RAMA_FORZADA="${2:-}"; shift 2 ;;
        *) echo "Opción desconocida: $1"; exit 1 ;;
    esac
done

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
gris()  { printf '\033[90m%s\033[0m\n' "$*"; }
paso()  { printf '\n\033[1m[%s]\033[0m %s\n' "$1" "$2"; }
morir() { rojo "ERROR: $*"; exit 1; }

exec > >(tee -a "$BITACORA") 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="

# -- Saneamiento del .env ------------------------------------
# Con BOM, compose lee la primera clave como "\xEF\xBB\xBFDEPLOY_BRANCH".
# Con CRLF, el \r se mete en el valor y DB_HOST da "ENOTFOUND".
sanear_env() {
    [[ -f "$ARCHIVO_ENV" ]] || return 0
    sed -i '1s/^\xEF\xBB\xBF//' "$ARCHIVO_ENV"
    sed -i 's/\r$//' "$ARCHIVO_ENV"
}

leer_env() {
    [[ -f "$ARCHIVO_ENV" ]] || return 0
    grep -E "^\s*${1}\s*=" "$ARCHIVO_ENV" 2>/dev/null \
        | grep -v '^\s*#' | tail -1 | cut -d'=' -f2- | tr -d ' \r' || true
}

preguntar() {
    local etiqueta="$1" predeterminado="${2:-}" respuesta
    if [[ -n "$predeterminado" ]]; then
        read -r -p "  $etiqueta [$predeterminado]: " respuesta </dev/tty
        echo "${respuesta:-$predeterminado}"
    else
        read -r -p "  $etiqueta: " respuesta </dev/tty
        echo "$respuesta"
    fi
}

# -- [0] Asistente -------------------------------------------
asistente() {
    cat <<'FIN'

  ================================================
    scadaMtto web - configuración inicial
  ================================================

  La base Mantenimiento vive fuera de Docker. Esta aplicación
  solo LEE la tabla que mantiene el adquisidor (test.ValorActual).

FIN
    local host puerto base usuario password esquema tabla puerto_app rama

    host=$(preguntar "IP o nombre del SQL Server" "172.17.132.153")
    [[ -n "$host" ]] || morir "Hace falta el host del SQL Server."
    if [[ "$host" == "localhost" || "$host" == "127.0.0.1" ]]; then
        morir "DB_HOST=$host no sirve: desde el contenedor apunta al contenedor mismo.
       Si SQL Server corre en este servidor usá host.docker.internal."
    fi
    puerto=$(preguntar "Puerto" "1433")
    base=$(preguntar "Nombre de la base" "Mantenimiento")
    usuario=$(preguntar "Usuario SQL (alcanza con permiso de lectura)" "")
    [[ -n "$usuario" ]] || morir "Hace falta el usuario SQL."
    read -r -s -p "  Contraseña SQL: " password </dev/tty; echo
    [[ -n "$password" ]] || morir "Hace falta la contraseña."
    if printf '%s' "$password" | grep -q '[;{}$"'"'"'#]'; then
        rojo "  Atención: la contraseña tiene alguno de estos: ; { } \$ \" ' #"
        rojo "  Van a romper el parseo del .env. Pedí una sin ellos."
    fi
    esquema=$(preguntar "Esquema de la tabla" "test")
    tabla=$(preguntar "Tabla del adquisidor" "ValorActual")
    puerto_app=$(preguntar "Puerto de la aplicación" "3108")
    rama=$(preguntar "Rama de git (si es un clon)" "main")

    # LF y sin BOM a proposito (ver sanear_env).
    cat > "$ARCHIVO_ENV" <<FIN
DEPLOY_BRANCH=$rama

DB_HOST=$host
DB_PUERTO=$puerto
DB_NOMBRE=$base
DB_USUARIO=$usuario
DB_PASSWORD=$password
DB_TRUST_CERT=true
DB_ESQUEMA=$esquema
DB_TABLA=$tabla

APP_PUERTO=$puerto_app
DATOS_DEMO=
TZ=America/Argentina/Buenos_Aires
FIN
    verde "  Escrito: $ARCHIVO_ENV"
}

paso 0 "Configuración"
if [[ "$SETUP" == true || ! -f "$ARCHIVO_ENV" ]]; then
    [[ -f "$EJEMPLO_ENV" ]] || morir "Falta $EJEMPLO_ENV; la carpeta está incompleta."
    asistente
else
    gris "Usando $ARCHIVO_ENV (--setup para rehacerlo)"
fi
sanear_env

RAMA="${RAMA_FORZADA:-$(leer_env DEPLOY_BRANCH)}"; RAMA="${RAMA:-main}"
APP_PUERTO="$(leer_env APP_PUERTO)"; APP_PUERTO="${APP_PUERTO:-3108}"
DB_HOST_ENV="$(leer_env DB_HOST)"
DB_PUERTO_ENV="$(leer_env DB_PUERTO)"; DB_PUERTO_ENV="${DB_PUERTO_ENV:-1433}"
DB_NOMBRE_ENV="$(leer_env DB_NOMBRE)"
DEMO_ENV="$(leer_env DATOS_DEMO)"

command -v docker >/dev/null 2>&1 || morir "Docker no está instalado o no está en el PATH."
docker info >/dev/null 2>&1 || morir "El demonio de Docker no responde. ¿Docker Desktop está abierto?"
docker compose version >/dev/null 2>&1 || morir "Hace falta Docker Compose v2 (docker compose, sin guion)."

gris "Base: ${DB_HOST_ENV}:${DB_PUERTO_ENV}/${DB_NOMBRE_ENV} · puerto: $APP_PUERTO"
[[ -n "$DEMO_ENV" ]] && rojo "  Atención: DATOS_DEMO=$DEMO_ENV. La app muestra datos de EJEMPLO, no los reales."

# -- [1] Código ----------------------------------------------
paso 1 "Actualizando el código"
if [[ "$SIN_PULL" == true ]]; then
    gris "Omitido por --sin-pull"
elif ! git -C "$RAIZ" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    gris "No es un repositorio git: se usa el código tal como está en la carpeta"
else
    cd "$RAIZ"
    if [[ -n "$(git status --porcelain -- .)" ]]; then
        morir "Hay cambios locales sin confirmar. Guardalos o descartalos antes de desplegar."
    fi
    git fetch origin "$RAMA"
    git checkout "$RAMA"
    git pull origin "$RAMA"
    verde "En $(git rev-parse --short HEAD)"
fi

# -- [1b] Acceso a la base -----------------------------------
paso 1b "Comprobando el acceso a la base"
if [[ -n "$DEMO_ENV" ]]; then
    gris "  Modo demo: se omite"
elif (echo >"/dev/tcp/${DB_HOST_ENV}/${DB_PUERTO_ENV}") 2>/dev/null; then
    verde "  El host llega a ${DB_HOST_ENV}:${DB_PUERTO_ENV}"
    # El host puede llegar y un contenedor no: pasa cuando la subred de
    # Docker (172.17-172.31) se superpone con la de la base, y
    # Mantenimiento esta en 172.17.132.153, justo adentro.
    if docker run --rm --quiet busybox true >/dev/null 2>&1; then
        if docker run --rm busybox timeout 5 nc -z "$DB_HOST_ENV" "$DB_PUERTO_ENV" >/dev/null 2>&1; then
            verde "  Un contenedor también llega a ${DB_HOST_ENV}:${DB_PUERTO_ENV}"
        else
            rojo "  El host llega pero un contenedor NO."
            rojo "  Casi seguro: la subred de Docker se superpone con la de la base."
            rojo "  Ver 'Subred de Docker' en examenesWeb/infraestructura/DEPLOYMENT.md"
            rojo "  (daemon.json con \"bip\" y \"default-address-pools\" fuera de 172.17)."
            morir "El contenedor no alcanza la base."
        fi
    else
        gris "  (sin imagen busybox a mano: se omite la prueba desde el contenedor)"
    fi
else
    morir "No hay TCP a ${DB_HOST_ENV}:${DB_PUERTO_ENV} desde este equipo.
       Revisá el puerto, el firewall y que la instancia acepte TCP/IP."
fi

# -- [2] Contenedores ----------------------------------------
paso 2 "Construyendo y levantando"
cd "$INFRA"
# -f deja afuera el override de desarrollo. --force-recreate no es
# opcional: sin el, compose reconstruye la imagen pero deja corriendo el
# contenedor viejo y el despliegue "sale bien" con el codigo anterior.
docker compose -f docker-compose.yml up -d --build --force-recreate

# -- [3] Salud -----------------------------------------------
paso 3 "Verificando el estado"
printf '  %s ' "$CONTENEDOR"
transcurrido=0
while :; do
    estado="$(docker inspect --format '{{.State.Health.Status}}' "$CONTENEDOR" 2>/dev/null || echo ausente)"
    case "$estado" in
        healthy)   verde "OK (${transcurrido}s)"; break ;;
        unhealthy) rojo "sin salud"; docker logs --tail 30 "$CONTENEDOR"; morir "La aplicación no llegó a estar sana." ;;
    esac
    if [[ $transcurrido -ge 150 ]]; then
        rojo "tiempo agotado"; docker logs --tail 30 "$CONTENEDOR"; morir "La aplicación no llegó a estar sana."
    fi
    sleep 5; transcurrido=$((transcurrido + 5)); printf '.'
done

# -- [4] Prueba de humo --------------------------------------
paso 4 "Prueba de humo"
curl -fsS "http://localhost:${APP_PUERTO}/api/health" >/dev/null 2>&1 \
    && verde "  /api/health responde y la base contesta" \
    || morir "La aplicación no responde en el puerto ${APP_PUERTO}."
curl -fsS "http://localhost:${APP_PUERTO}/api/celda/fca0203" >/dev/null 2>&1 \
    && verde "  /api/celda/fca0203 devuelve datos" \
    || rojo "  /api/celda/fca0203 falló: mirar 'docker logs $CONTENEDOR'"

# -- [5] Limpieza --------------------------------------------
paso 5 "Limpieza"
# Nunca con -v: la costumbre se pega y en otros proyectos borra la base.
docker image prune -f >/dev/null
gris "Imágenes huérfanas eliminadas."

# -- [6] Resumen ---------------------------------------------
paso 6 "Listo"
docker compose -f docker-compose.yml ps --format 'table {{.Name}}\t{{.Status}}'
IP_LAN="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "$IP_LAN" ]] && command -v ipconfig >/dev/null 2>&1; then
    IP_LAN="$(ipconfig 2>/dev/null | grep -a -m1 -E 'IPv4' | sed -E 's/.*: *//' | tr -d '\r')"
fi
[[ -z "$IP_LAN" ]] && IP_LAN="<ip-del-servidor>"
echo
verde "  Disponible en: http://${IP_LAN}:${APP_PUERTO}"
gris  "  Bitácora: $BITACORA"
gris  "  Si desde otra máquina no entra, falta abrir el puerto ${APP_PUERTO} en el firewall."
echo
