<#
.SYNOPSIS
    Iniciar, detener y mirar el adquisidor scadaMtto cuando corre como servicio.

.DESCRIPTION
    Lo usan los accesos directos iniciar.cmd, detener.cmd, estado.cmd y
    ver_log.cmd. Iniciar y detener piden permisos de Administrador solos.

      iniciar   borra stop.flag y arranca la tarea programada
      detener   crea stop.flag y espera la salida limpia (cierra bien la
                conexion con el PLC). El flag queda puesto para que nadie lo
                relance hasta usar iniciar.
      estado    tarea, proceso, ultimas lineas del watchdog y dashboard
      log       muestra logs\scadamtto.log en vivo (Ctrl+C para salir)
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('iniciar', 'detener', 'estado', 'log')]
    [string]$Accion,
    [string]$Tarea = 'scadaMtto',
    [switch]$Pausa
)

$ErrorActionPreference = 'Stop'
$Raiz = $PSScriptRoot
$flag = Join-Path $Raiz 'stop.flag'
$TIMEOUT_PARADA_S = 30

function Es-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Fin {
    if ($Pausa) {
        Write-Host ''
        Read-Host 'Presione Enter para cerrar' | Out-Null
    }
}

function Titulo([string]$t) { Write-Host "`n== $t ==" -ForegroundColor Cyan }

function Proceso {
    return Get-Process -Name 'scadamtto' -ErrorAction SilentlyContinue
}

function Puerto-Web {
    # Lee web_puerto de config\app.toml; si no esta, el default de la app.
    $app = Join-Path $Raiz 'config\app.toml'
    if (Test-Path $app) {
        $m = Select-String -Path $app -Pattern '^\s*web_puerto\s*=\s*(\d+)' | Select-Object -First 1
        if ($m) { return [int]$m.Matches[0].Groups[1].Value }
    }
    return 8080
}

# --- elevacion -----------------------------------------------------------------
# C:\scadaMtto queda en manos de SYSTEM/Administradores y la tarea corre como
# SYSTEM: para tocar el flag o la tarea hacen falta permisos de administrador.
if ($Accion -in @('iniciar', 'detener') -and -not (Es-Admin)) {
    $argumentos = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Accion $Accion -Tarea $Tarea -Pausa"
    try {
        Start-Process -FilePath 'powershell.exe' -ArgumentList $argumentos -Verb RunAs
    } catch {
        Write-Host 'Se cancelo el pedido de permisos de Administrador.' -ForegroundColor Yellow
        Fin
    }
    exit
}

switch ($Accion) {

    'iniciar' {
        Titulo 'Iniciar scadaMtto'
        if (Test-Path $flag) {
            Remove-Item -Force $flag
            Write-Host '  stop.flag borrado'
        }
        $p = Proceso
        if ($p) {
            Write-Host ("  Ya estaba corriendo (PID {0})." -f $p.Id) -ForegroundColor Green
            Fin; break
        }
        $t = Get-ScheduledTask -TaskName $Tarea -ErrorAction SilentlyContinue
        if (-not $t) {
            Write-Host "  No existe la tarea '$Tarea'. Correr primero preparar_pc.ps1 como Administrador." -ForegroundColor Red
            Fin; break
        }
        Start-ScheduledTask -TaskName $Tarea
        Write-Host '  tarea iniciada, esperando al proceso...'
        for ($i = 0; $i -lt 20 -and -not (Proceso); $i++) { Start-Sleep -Seconds 1 }
        $p = Proceso
        if ($p) {
            Write-Host ("  Corriendo (PID {0}). Dashboard: http://localhost:{1}" -f $p.Id, (Puerto-Web)) -ForegroundColor Green
        } else {
            Write-Host '  El proceso no aparecio en 20 s. Mirar logs\watchdog.log y logs\scadamtto.log' -ForegroundColor Yellow
        }
        Fin
    }

    'detener' {
        Titulo 'Detener scadaMtto'
        # Set-Content actualiza la fecha de modificacion aunque el archivo ya
        # exista: el adquisidor solo hace caso a un flag mas nuevo que su arranque.
        Set-Content -Path $flag -Value (Get-Date -Format 'o') -Encoding ASCII
        Write-Host '  stop.flag creado: se pide la parada ordenada'
        $p = Proceso
        if (-not $p) {
            Write-Host '  No habia ningun adquisidor corriendo. Queda detenido.' -ForegroundColor Green
            Fin; break
        }
        $plazo = (Get-Date).AddSeconds($TIMEOUT_PARADA_S)
        while ((Proceso) -and ((Get-Date) -lt $plazo)) { Start-Sleep -Milliseconds 500 }
        if (Proceso) {
            Write-Host "  No termino en $TIMEOUT_PARADA_S s: se fuerza el cierre." -ForegroundColor Yellow
            Write-Host '  La conexion MC puede quedar ocupada en el PLC un rato hasta que expire.' -ForegroundColor Yellow
            Get-Process -Name 'scadamtto' -ErrorAction SilentlyContinue | Stop-Process -Force
        } else {
            Write-Host '  Detenido de forma limpia.' -ForegroundColor Green
        }
        Write-Host '  No se va a relanzar solo. Para volver a arrancarlo: iniciar.cmd'
        Fin
    }

    'estado' {
        Titulo 'Proceso'
        $p = Proceso
        if ($p) {
            Write-Host ("  CORRIENDO  PID {0}  desde {1}  memoria {2:N0} MB" -f `
                $p.Id, $p.StartTime, ($p.WorkingSet64 / 1MB)) -ForegroundColor Green
        } else {
            Write-Host '  DETENIDO' -ForegroundColor Red
        }
        if (Test-Path $flag) {
            Write-Host '  stop.flag presente: detenido a proposito (iniciar.cmd para arrancar)' -ForegroundColor Yellow
        }

        Titulo 'Tarea programada'
        try {
            $t = Get-ScheduledTask -TaskName $Tarea -ErrorAction Stop
            $info = $t | Get-ScheduledTaskInfo
            Write-Host ("  estado: {0}   ultima ejecucion: {1}   resultado: 0x{2:X}" -f `
                $t.State, $info.LastRunTime, $info.LastTaskResult)
        } catch {
            Write-Host "  No se encontro la tarea '$Tarea' (o hace falta ser Administrador para verla)." -ForegroundColor Yellow
        }

        Titulo 'Ultimas lineas de logs\watchdog.log'
        $wlog = Join-Path $Raiz 'logs\watchdog.log'
        if (Test-Path $wlog) {
            Get-Content -Path $wlog -Tail 8 -Encoding UTF8 | ForEach-Object { Write-Host "  $_" }
        } else {
            Write-Host '  (todavia no hay log del watchdog)'
        }

        Titulo 'Dashboard'
        $puerto = Puerto-Web
        try {
            $e = Invoke-RestMethod -Uri "http://127.0.0.1:$puerto/api/estado" -TimeoutSec 5
            foreach ($plc in $e.plcs) {
                $c = 'Red'; if ($plc.conectado) { $c = 'Green' }
                Write-Host ("  PLC {0} ({1}:{2})  conectado={3}  lecturas ok/error={4}/{5}" -f `
                    $plc.nombre, $plc.ip, $plc.puerto, $plc.conectado, $plc.lecturas_ok, $plc.lecturas_error) -ForegroundColor $c
            }
            $c = 'Red'; if ($e.db.conectada) { $c = 'Green' }
            Write-Host ("  SQL Server conectada={0}  escrituras={1}  pendientes en buffer={2}" -f `
                $e.db.conectada, $e.db.filas_escritas, $e.buffer_pendientes) -ForegroundColor $c
            Write-Host "  http://localhost:$puerto"
        } catch {
            Write-Host "  No responde http://127.0.0.1:$puerto (el adquisidor esta detenido o arrancando)." -ForegroundColor Yellow
        }
        Fin
    }

    'log' {
        $alog = Join-Path $Raiz 'logs\scadamtto.log'
        if (-not (Test-Path $alog)) {
            Write-Host "Todavia no existe $alog" -ForegroundColor Yellow
            Fin; break
        }
        Write-Host "Log en vivo de $alog  (Ctrl+C para salir)`n" -ForegroundColor Cyan
        Get-Content -Path $alog -Tail 50 -Wait -Encoding UTF8
    }
}
