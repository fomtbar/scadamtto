<#
.SYNOPSIS
    Mantiene scadamtto.exe corriendo: si termina por cualquier motivo, lo relanza.

.DESCRIPTION
    Lo lanza la tarea programada "scadaMtto" (creada por preparar_pc.ps1) como
    SYSTEM y sin ventana. No hace falta correrlo a mano.

    - Anota cada arranque y cada salida, con su codigo, en logs\watchdog.log.
    - Espera 5 s entre reintentos. Si el proceso se cae enseguida una y otra vez
      (crash-loop), la espera crece hasta 60 s para no martillar al PLC ni llenar
      el log; vuelve a 5 s cuando el proceso logra correr mas de 5 minutos.
    - Si existe stop.flag en la carpeta, no lanza nada y termina. Asi detener.cmd
      para el servicio y la repeticion cada 5 min de la tarea no lo vuelve a
      levantar.

    Codigos de salida de scadamtto.exe:
      0 parada pedida   1 se murieron los hilos de scan
      2 configuracion invalida   3 ya habia otra instancia corriendo
#>
param(
    [string]$Raiz = $PSScriptRoot
)

$ErrorActionPreference = 'Continue'

$exe  = Join-Path $Raiz 'scadamtto.exe'
$flag = Join-Path $Raiz 'stop.flag'
$dirLog = Join-Path $Raiz 'logs'
$log  = Join-Path $dirLog 'watchdog.log'

$ESPERA_MIN = 5
$ESPERA_MAX = 60
$CORRIDA_SANA_S = 300
$LOG_MAX_BYTES = 5MB

New-Item -ItemType Directory -Force -Path $dirLog | Out-Null

function Escribir-Log([string]$mensaje) {
    try {
        if ((Test-Path $log) -and ((Get-Item $log).Length -gt $LOG_MAX_BYTES)) {
            Move-Item -Force $log "$log.1"
        }
        $linea = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $mensaje
        Add-Content -Path $log -Value $linea -Encoding UTF8
    } catch {
        # Que un problema con el log nunca tumbe al watchdog.
    }
}

function Esperar([int]$segundos) {
    # Espera de a un segundo para atender un stop.flag sin demora.
    for ($i = 0; $i -lt $segundos; $i++) {
        if (Test-Path $flag) { return }
        Start-Sleep -Seconds 1
    }
}

$descripcion = @{
    0 = 'parada pedida'
    1 = 'se murieron los hilos de scan'
    2 = 'configuracion invalida (revisar config\site.toml y logs\scadamtto.log)'
    3 = 'ya habia otra instancia corriendo'
}

# El adquisidor usa esta variable para saber que no hay nadie mirando la consola
# y que no debe frenarse esperando una tecla ante un error.
$env:SCADAMTTO_WATCHDOG = '1'

Escribir-Log ("watchdog iniciado (PID {0}, usuario {1}, raiz {2})" -f $PID, $env:USERNAME, $Raiz)
$espera = $ESPERA_MIN

while ($true) {
    if (Test-Path $flag) {
        Escribir-Log 'stop.flag presente: no se lanza el adquisidor, el watchdog termina'
        break
    }
    if (-not (Test-Path $exe)) {
        Escribir-Log "no existe $exe; reintento en $ESPERA_MAX s"
        Esperar $ESPERA_MAX
        continue
    }

    $inicio = Get-Date
    try {
        # Se lanza con Process.Start y UseShellExecute = false, NO con
        # Start-Process -WindowStyle. Start-Process pasa por ShellExecute (el
        # mismo camino que el doble clic del Explorador) y, si el exe tiene la
        # marca de "descargado de otro equipo" (Zone.Identifier, la trae
        # cualquier zip copiado), Windows muestra el aviso "Desea ejecutar este
        # archivo?". Corriendo como SYSTEM ese aviso queda en una pantalla que
        # nadie ve y el watchdog se queda esperando para siempre. Paso en
        # arg-scada01. CreateProcess directo no pasa por ese control.
        $si = New-Object System.Diagnostics.ProcessStartInfo
        $si.FileName = $exe
        $si.WorkingDirectory = $Raiz
        $si.UseShellExecute = $false
        $si.CreateNoWindow = $true
        $p = [System.Diagnostics.Process]::Start($si)
        Escribir-Log ("scadamtto.exe lanzado (PID {0})" -f $p.Id)
        $p.WaitForExit()
        $codigo = $p.ExitCode
    } catch {
        Escribir-Log ("no se pudo lanzar scadamtto.exe: {0}" -f $_.Exception.Message)
        $codigo = -1
    }
    $duracion = [int]((Get-Date) - $inicio).TotalSeconds

    $texto = $descripcion[[int]$codigo]
    if (-not $texto) { $texto = 'salida inesperada (crash o proceso terminado a la fuerza)' }
    Escribir-Log ("scadamtto.exe termino con codigo {0} tras {1} s: {2}" -f $codigo, $duracion, $texto)

    if (Test-Path $flag) {
        Escribir-Log 'parada pedida con stop.flag: el watchdog termina'
        break
    }

    if ($duracion -ge $CORRIDA_SANA_S) {
        $espera = $ESPERA_MIN
    }
    if ($codigo -eq 3) {
        # Otra instancia (por ejemplo una lanzada a mano con correr.cmd): no
        # tiene sentido reintentar rapido, va a seguir ocupada.
        $espera = $ESPERA_MAX
    }

    Escribir-Log ("relanzando en {0} s" -f $espera)
    Esperar $espera
    if ($duracion -lt $CORRIDA_SANA_S) {
        $espera = [Math]::Min($espera * 2, $ESPERA_MAX)
    }
}
