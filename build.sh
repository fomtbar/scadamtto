#!/usr/bin/env bash
#
# Genera el ejecutable de scadaMtto y arma el paquete para llevar a la PC de
# adquisicion. Se corre desde Git Bash, parado en la raiz del proyecto:
#
#     ./build.sh                     build normal
#     ./build.sh --con-credenciales  incluye config/site.toml (TRAE LA PASSWORD)
#     ./build.sh --sin-tests         saltea los tests (no recomendado)
#     ./build.sh --version 5         fuerza el numero de version
#
# Deja:
#     release/scadaMtto_vN/          la carpeta lista para copiar
#     release/scadaMtto_vN.zip       la misma, comprimida
#
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

PY=".venv/Scripts/python.exe"
CON_CREDENCIALES=0
CORRER_TESTS=1
VERSION_FORZADA=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --con-credenciales) CON_CREDENCIALES=1; shift ;;
    --sin-tests)        CORRER_TESTS=0; shift ;;
    --version)          VERSION_FORZADA="${2:-}"; shift 2 ;;
    -h|--help)          sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Opcion desconocida: $1  (probá --help)" >&2; exit 2 ;;
  esac
done

titulo() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }
ok()     { printf '  \033[32m✓\033[0m %s\n' "$1"; }
aviso()  { printf '  \033[33m!\033[0m %s\n' "$1"; }
morir()  { printf '\n\033[31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

# --------------------------------------------------------------- prerequisitos
titulo "Prerrequisitos"
[[ -f "$PY" ]] || morir "No existe $PY. Crear el entorno: py -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt"
ok "python: $("$PY" -V 2>&1)"

if ! "$PY" -m PyInstaller --version >/dev/null 2>&1; then
  aviso "PyInstaller no esta instalado, instalandolo en .venv ..."
  "$PY" -m pip install -q --disable-pip-version-check pyinstaller || morir "No se pudo instalar PyInstaller"
fi
ok "pyinstaller: $("$PY" -m PyInstaller --version 2>&1 | tail -1)"

# Que no falte ninguna dependencia de runtime antes de congelar: un import roto
# aca es un exe que arranca y muere en planta.
"$PY" - <<'PYEOF' || morir "Falta alguna dependencia. Revisar: .venv/Scripts/python.exe -m pip install -r requirements.txt"
import importlib.util, sys
faltan = [m for m in ("pytds", "pymcprotocol", "snap7", "loguru") if not importlib.util.find_spec(m)]
if faltan:
    print("  faltan modulos:", ", ".join(faltan)); sys.exit(1)
PYEOF
ok "dependencias de runtime presentes"

# ----------------------------------------------------------------------- tests
if [[ $CORRER_TESTS -eq 1 ]]; then
  titulo "Tests"
  "$PY" -m pytest -q || morir "Los tests fallan. Corregir antes de empaquetar (o usar --sin-tests bajo tu responsabilidad)."
  ok "todos los tests pasan"
else
  aviso "tests salteados por --sin-tests"
fi

# --------------------------------------------------------------------- version
titulo "Version"
if [[ -n "$VERSION_FORZADA" ]]; then
  VERSION="$VERSION_FORZADA"
else
  VERSION=$(( $(cat VERSION 2>/dev/null || echo 0) + 1 ))
fi
echo "$VERSION" > VERSION
NOMBRE="scadaMtto_v${VERSION}"
DEST="release/${NOMBRE}"
ok "version $VERSION  ->  $DEST"

# ----------------------------------------------------------------------- build
titulo "Compilando el ejecutable"
# El watchdog puede tener el exe tomado y bloquear el borrado del dist anterior.
if command -v taskkill >/dev/null 2>&1; then
  taskkill //F //IM scadamtto.exe >/dev/null 2>&1 || true
fi
rm -rf build dist "$DEST" "${DEST}.zip"
"$PY" -m PyInstaller scadamtto.spec --clean --noconfirm --log-level WARN \
  || morir "Fallo PyInstaller"
[[ -f "dist/scadamtto/scadamtto.exe" ]] || morir "PyInstaller no genero dist/scadamtto/scadamtto.exe"
ok "dist/scadamtto/scadamtto.exe"

# ------------------------------------------------------------------- humo
titulo "Prueba de humo del ejecutable"
# Que al menos arranque y resuelva sus imports. Se usa --help, que no toca red.
if ! ./dist/scadamtto/scadamtto.exe --help >/dev/null 2>&1; then
  morir "El ejecutable generado no arranca. Probar a mano: ./dist/scadamtto/scadamtto.exe --help"
fi
ok "el ejecutable arranca y responde --help"

# ------------------------------------------------------------------- empaquetado
titulo "Armando el paquete"
mkdir -p "$DEST"
cp -r dist/scadamtto/. "$DEST/"

mkdir -p "$DEST/config" "$DEST/sql"
cp config/app.default.toml   "$DEST/config/"
cp config/site.example.toml  "$DEST/config/"
cp config/tags.toml          "$DEST/config/"
cp scripts/sql/*.sql         "$DEST/sql/"
cp README.md                 "$DEST/"
ok "config de ejemplo, SQL y README"

if [[ $CON_CREDENCIALES -eq 1 ]]; then
  cp config/site.toml "$DEST/config/site.toml"
  aviso "site.toml INCLUIDO: el paquete contiene la password de la base de datos"
else
  ok "site.toml NO incluido (usar --con-credenciales si lo querés adentro)"
fi

# app.toml, data/ y logs/ se generan solos en el primer arranque; no se copian
# para que la PC de destino arranque limpia.

# -------------------------------------------------------------- scripts de planta
# Los .ps1 y .cmd de operacion viven versionados en deploy/ y se copian tal cual.
# Antes se validan con el parser de PowerShell: un error de sintaxis en
# preparar_pc.ps1 o watchdog.ps1 se descubriria recien en la PC de planta.
titulo "Validando scripts de PowerShell"
for ps in deploy/preparar_pc.ps1 deploy/watchdog.ps1 deploy/control.ps1; do
  ruta_win="$(cygpath -w "$RAIZ/$ps")"
  salida=$(powershell.exe -NoProfile -Command "\
    \$t=\$null; \$e=\$null; \
    [System.Management.Automation.Language.Parser]::ParseFile('$ruta_win',[ref]\$t,[ref]\$e) | Out-Null; \
    \$e | ForEach-Object { 'linea ' + \$_.Extent.StartLineNumber + ': ' + \$_.Message }; \
    if ([IO.File]::ReadAllBytes('$ruta_win') | Where-Object { \$_ -gt 127 }) { 'tiene caracteres no ASCII (PS 5.1 los lee mal sin BOM)' }" 2>&1 | tr -d '\r')
  [[ -z "$salida" ]] || morir "$ps no es valido:"$'\n'"$salida"
  ok "$ps"
done

cp deploy/preparar_pc.ps1 deploy/watchdog.ps1 deploy/control.ps1 "$DEST/"
cp deploy/iniciar.cmd deploy/detener.cmd deploy/estado.cmd deploy/ver_log.cmd "$DEST/"
ok "preparar_pc.ps1, watchdog.ps1, control.ps1"
ok "iniciar.cmd, detener.cmd, estado.cmd, ver_log.cmd"

cat > "$DEST/correr.cmd" <<'EOF'
@echo off
rem Arranque MANUAL con la consola a la vista, para depurar.
rem Si el servicio esta corriendo, esta instancia sale enseguida (solo puede
rem haber una): usar primero detener.cmd.
cd /d "%~dp0"
scadamtto.exe
echo.
echo El proceso termino. Presione una tecla para cerrar.
pause >nul
EOF

cat > "$DEST/diagnostico.cmd" <<'EOF'
@echo off
rem Diagnostico completo: base de datos, conexion al PLC y lectura de los tags.
rem Usa la conexion MC del PLC: si el servicio esta corriendo y el PLC tiene una
rem sola entrada MC Protocol, la prueba del PLC puede no entrar.
cd /d "%~dp0"
echo ============================== BASE DE DATOS ==============================
scadamtto.exe testdb
echo.
echo ============================== CONEXION PLC ===============================
scadamtto.exe probe
echo.
echo ============================== LECTURA TAGS ===============================
scadamtto.exe leer
echo.
pause
EOF
ok "correr.cmd, diagnostico.cmd"

# --------------------------------------------------------------------- LEEME
cat > "$DEST/LEEME.txt" <<EOF
scadaMtto v${VERSION} - adquisidor de PLC hacia SQL Server
Generado: $(date '+%Y-%m-%d %H:%M')

INSTALACION EN LA PC DE ADQUISICION
-----------------------------------

1. Descomprimir esta carpeta en C:\scadaMtto
   (fuera de Escritorio/Documentos: el servicio corre como SYSTEM).

2. Red. La PC necesita DOS caminos:
     - placa al MikroTik de la celda : IP fija 192.168.30.10/24, SIN puerta de enlace
       (la regla NAT del hEX solo acepta esa IP de origen)
     - placa/Wi-Fi a la red de IT    : con puerta de enlace (la unica que la lleva)
   Si la PC de desarrollo tambien usa 192.168.30.10, desconectarla antes.

3. Si no viene incluido, copiar config\site.example.toml a config\site.toml
   y completarlo. La app apunta a la IP del MikroTik, no a la del PLC.

4. PowerShell como Administrador:
     cd C:\scadaMtto
     powershell -ExecutionPolicy Bypass -File .\preparar_pc.ps1
   Deja energia, recuperacion ante cortes, red, hora, updates y Defender, y crea
   la tarea que arranca el adquisidor AL ENCENDER, sin iniciar sesion.
   Muestra un reporte OK / CAMBIADO / AVISO / MANUAL. Se puede correr de nuevo
   cuando se quiera; para solo mirar: .\preparar_pc.ps1 -Verificar

5. BIOS (MANUAL, ningun script lo puede hacer). En la MSI: tecla Supr al
   encender > Settings > Advanced > Power Management Setup:
     Restore after AC Power Loss = Power On
     ErP Ready                  = Disabled

6. Reiniciar. Sin iniciar sesion, el adquisidor tiene que estar corriendo:
   desde otra sesion, estado.cmd o http://localhost:8080


OPERACION
---------
  iniciar.cmd       arranca el servicio
  detener.cmd       lo para de forma limpia (y no se relanza solo)
  estado.cmd        proceso, tarea, ultimas lineas del watchdog, PLC y DB
  ver_log.cmd       log en vivo
  diagnostico.cmd   prueba base de datos, PLC y lectura de tags
  correr.cmd        arranque manual con consola (detener el servicio antes)

  Dashboard: http://localhost:8080
    Monitor   -> estado en vivo de PLC, base y buffer
    Variables -> alta/baja/edicion de tags, se aplica sin reiniciar

  Si scadamtto.exe se cae, el watchdog lo relanza en segundos.
  Si se corta la luz, la PC vuelve sola (BIOS) y la tarea lo arranca.
  Si se cae la base, sigue leyendo y guarda en data\buffer.sqlite; cuando
  vuelve, descarga todo solo.


LOGS
----
  logs\scadamtto.log     el adquisidor (rota cada 5 MB, 30 dias)
  logs\watchdog.log      cada arranque y cada caida, con su codigo
  logs\preparar_pc_*.txt como quedo el equipo cada vez que se preparo

  Codigos de salida: 0 parada pedida, 1 se murieron los hilos de scan,
  2 configuracion invalida, 3 ya habia otra instancia corriendo.


ACTUALIZAR A UNA VERSION NUEVA
------------------------------
  detener.cmd, copiar SOLO scadamtto.exe y _internal\ sobre C:\scadaMtto
  (no pisar config\ ni data\), iniciar.cmd.


DESHACER
--------
  .\preparar_pc.ps1 -Desinstalar       quita la tarea y la exclusion de Defender
  .\preparar_pc.ps1 -HabilitarUpdates  vuelve Windows Update a fabrica


QUE NO HAY QUE HACER
--------------------
  - No borrar config\site.toml: tiene la configuracion de ESTA maquina.
  - No cerrar el adquisidor con el Administrador de tareas: usar detener.cmd.
    Matarlo deja ocupada la conexion MC en el PLC hasta que expira.
  - Cada entrada "MC Protocol" del PLC acepta UN solo cliente. Si un HMI usa el
    mismo puerto, abrir otra entrada en el Open Setting en vez de compartirla.
EOF
ok "LEEME.txt"

echo "$VERSION" > "$DEST/VERSION.txt"
date '+%Y-%m-%d %H:%M' >> "$DEST/VERSION.txt"

# ------------------------------------------------------------------------- zip
titulo "Comprimiendo"
"$PY" - "$DEST" "${DEST}.zip" <<'PYEOF'
import shutil, sys, pathlib
origen, destino = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
shutil.make_archive(str(destino.with_suffix("")), "zip", origen.parent, origen.name)
PYEOF
ok "$(ls -lh "${DEST}.zip" | awk '{print $9, "(" $5 ")"}')"

# --------------------------------------------------------------------- resumen
titulo "Listo"
printf '  carpeta : %s\n' "$RAIZ/$DEST"
printf '  zip     : %s\n' "$RAIZ/${DEST}.zip"
printf '  tamano  : %s\n' "$(du -sh "$DEST" | cut -f1)"
printf '  archivos: %s\n' "$(find "$DEST" -type f | wc -l | tr -d ' ')"
echo
echo "  Copiar el zip a la PC de adquisicion, descomprimir y seguir LEEME.txt"
[[ $CON_CREDENCIALES -eq 1 ]] && printf '\n  \033[33mOJO: el paquete incluye la password de la base en config/site.toml\033[0m\n'
echo
