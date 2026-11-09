<#
.SYNOPSIS
    Deja una PC con Windows 11 lista para correr el adquisidor scadaMtto 24/7.

.DESCRIPTION
    Pensado para arg-scada01 (MSI PRO Cubi 5 12M), sirve para cualquier PC
    dedicada. Es idempotente: se puede correr las veces que haga falta.

    Que hace:
      Energia       plan Alto rendimiento, nunca suspende/hiberna, sin Inicio
                    rapido, sin ahorro en USB ni PCIe, boton de encendido = apagar
      Recuperacion  sin pantalla de Reparacion automatica tras un corte, reinicio
                    solo ante pantallazo azul, sin dialogos de error que frenen
      Red           sin ahorro de energia en las placas; valida gateway, PLC y DB
      Hora          servicio de hora en automatico y sincronizado
      Updates       Windows Update desactivado (reversible con -HabilitarUpdates)
      Defender      exclusion de la carpeta del adquisidor
      Tarea         arranca el watchdog al encender, como SYSTEM, sin login

    Lo que NINGUN script puede hacer, y queda marcado como MANUAL: la BIOS.
    En la MSI: Settings > Advanced > Power Management Setup >
      Restore after AC Power Loss = Power On
      ErP Ready                  = Disabled

    Uso (PowerShell como Administrador, parado en la carpeta del adquisidor):
      powershell -ExecutionPolicy Bypass -File .\preparar_pc.ps1
      powershell -ExecutionPolicy Bypass -File .\preparar_pc.ps1 -Verificar

.PARAMETER Verificar
    Solo lectura: reporta el estado de cada punto sin cambiar nada.
.PARAMETER Desinstalar
    Para el adquisidor, borra la tarea y la exclusion de Defender. No revierte
    energia ni recuperacion.
.PARAMETER HabilitarUpdates
    Vuelve a dejar Windows Update como viene de fabrica.
.PARAMETER NoIniciar
    Instala todo pero no arranca el adquisidor al terminar.
.PARAMETER IpRecoleccion
    IP que tiene que tener la placa conectada al MikroTik. La regla dst-nat del
    hEX filtra por esta IP de origen.
#>
[CmdletBinding()]
param(
    [switch]$Verificar,
    [switch]$Desinstalar,
    [switch]$HabilitarUpdates,
    [switch]$NoIniciar,
    [string]$IpRecoleccion = '192.168.30.10',
    [string]$Tarea = 'scadaMtto'
)

$ErrorActionPreference = 'Stop'
$Aplicar = -not $Verificar

# ============================================================== utilidades

$resultados = New-Object System.Collections.Generic.List[object]

function Res([string]$area, [string]$item, [string]$estado, [string]$detalle = '') {
    $resultados.Add([pscustomobject]@{
        Area = $area; Item = $item; Estado = $estado; Detalle = $detalle
    })
    $color = @{ 'OK' = 'Green'; 'CAMBIADO' = 'Cyan'; 'AVISO' = 'Yellow';
                'MANUAL' = 'Magenta'; 'ERROR' = 'Red'; 'PENDIENTE' = 'Yellow';
                'NO VERIFICADO' = 'DarkYellow' }[$estado]
    if (-not $color) { $color = 'Gray' }
    $linea = '  [{0,-13}] {1}' -f $estado, $item
    if ($detalle) { $linea += "  -- $detalle" }
    Write-Host $linea -ForegroundColor $color
}

function Seccion([string]$t) { Write-Host "`n== $t ==" -ForegroundColor White }

function Es-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Verifica un valor y, si no es el deseado y estamos aplicando, lo corrige.
#   $leer     scriptblock que devuelve el valor actual
#   $escribir scriptblock que aplica el valor deseado
function Asegurar([string]$area, [string]$item, $deseado, [scriptblock]$leer, [scriptblock]$escribir) {
    try {
        $actual = & $leer
    } catch {
        $msg = $_.Exception.Message.Trim()
        # Varios cmdlets devuelven errores enganiosos sin permisos (CIM dice que
        # "un dispositivo no funciona"): se aclara el motivo probable.
        if (-not $esAdmin) { $msg = "requiere Administrador ($msg)" }
        Res $area $item 'NO VERIFICADO' $msg
        return
    }
    if ("$actual" -eq "$deseado") {
        Res $area $item 'OK'
        return
    }
    if (-not $Aplicar) {
        Res $area $item 'PENDIENTE' "actual: '$actual', deseado: '$deseado'"
        return
    }
    try {
        & $escribir
        Res $area $item 'CAMBIADO' "era '$actual'"
    } catch {
        Res $area $item 'ERROR' $_.Exception.Message
    }
}

function Leer-Registro([string]$ruta, [string]$nombre) {
    $v = Get-ItemProperty -Path $ruta -Name $nombre -ErrorAction SilentlyContinue
    if ($null -eq $v) { return '' }
    return $v.$nombre
}

function Escribir-Registro([string]$ruta, [string]$nombre, $valor) {
    if (-not (Test-Path $ruta)) { New-Item -Path $ruta -Force | Out-Null }
    New-ItemProperty -Path $ruta -Name $nombre -Value $valor -PropertyType DWord -Force | Out-Null
}

# powercfg /qh imprime los indices en el idioma del sistema, pero los valores
# siempre como 0x........ : los dos ultimos son el de corriente alterna (AC) y el
# de bateria (DC). Se toma el anteultimo y no se depende del idioma.
# Es /qh y no /q: /q omite los ajustes ocultos, y varios de los que importan aca
# (boton de encendido, por ejemplo) vienen ocultos de fabrica.
function Leer-Powercfg([string]$sub, [string]$setting) {
    $salida = & powercfg /qh SCHEME_CURRENT $sub $setting 2>&1
    if ($LASTEXITCODE -ne 0) { throw "powercfg no conoce $sub/$setting en este equipo" }
    $valores = @($salida | Select-String -Pattern ':\s*0x([0-9a-fA-F]{8})\s*$' |
                 ForEach-Object { [Convert]::ToInt32($_.Matches[0].Groups[1].Value, 16) })
    if ($valores.Count -lt 2) { throw "no se pudo interpretar powercfg /qh $sub $setting" }
    return $valores[$valores.Count - 2]
}

function Escribir-Powercfg([string]$sub, [string]$setting, [int]$valor) {
    & powercfg /setacvalueindex SCHEME_CURRENT $sub $setting $valor | Out-Null
    & powercfg /setdcvalueindex SCHEME_CURRENT $sub $setting $valor | Out-Null
    & powercfg /setactive SCHEME_CURRENT | Out-Null
}

# Lector minimo de TOML: secciones, y clave = valor simple. Alcanza para site.toml.
function Leer-Toml([string]$ruta) {
    $datos = @{}
    $seccion = ''
    foreach ($linea in Get-Content -Path $ruta -Encoding UTF8) {
        $l = ($linea -replace '#.*$', '').Trim()
        if (-not $l) { continue }
        if ($l -match '^\[(.+)\]$') {
            $seccion = $Matches[1].Trim()
            $datos[$seccion] = @{}
            continue
        }
        if ($seccion -and $l -match '^([A-Za-z0-9_]+)\s*=\s*(.+)$') {
            $datos[$seccion][$Matches[1]] = $Matches[2].Trim().Trim('"')
        }
    }
    return $datos
}

function Probar-Tcp([string]$ip, [int]$puerto, [int]$timeoutMs = 3000) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $ar = $c.BeginConnect($ip, $puerto, $null, $null)
        if (-not $ar.AsyncWaitHandle.WaitOne($timeoutMs)) { return $null }
        $c.EndConnect($ar)
        return $c.Client.LocalEndPoint.Address.ToString()
    } catch {
        return $null
    } finally {
        $c.Close()
    }
}

# ======================================================== precondiciones

$esAdmin = Es-Admin
if (-not $esAdmin -and -not $Verificar) {
    Write-Host 'Hay que correrlo como Administrador (o usar -Verificar para solo mirar).' -ForegroundColor Red
    exit 1
}

# Sirve tanto en el paquete (junto a scadamtto.exe) como en el proyecto de
# desarrollo (dentro de deploy\, un nivel abajo de config\).
if (Test-Path (Join-Path $PSScriptRoot 'scadamtto.exe')) {
    $Raiz = $PSScriptRoot
    $hayExe = $true
} else {
    $Raiz = Split-Path -Parent $PSScriptRoot
    $hayExe = $false
}
$siteToml = Join-Path $Raiz 'config\site.toml'
$watchdog = Join-Path $PSScriptRoot 'watchdog.ps1'
$flag = Join-Path $Raiz 'stop.flag'

$modo = 'APLICAR'
if ($Verificar) { $modo = 'VERIFICAR (solo lectura)' }
if ($Desinstalar) { $modo = 'DESINSTALAR' }
if ($HabilitarUpdates) { $modo = 'HABILITAR UPDATES' }

Write-Host ''
Write-Host '============================================================' -ForegroundColor White
Write-Host ' scadaMtto - preparacion del equipo' -ForegroundColor White
Write-Host ('  equipo : {0}   usuario: {1}   admin: {2}' -f $env:COMPUTERNAME, $env:USERNAME, $esAdmin)
Write-Host ('  raiz   : {0}' -f $Raiz)
Write-Host ('  modo   : {0}' -f $modo)
Write-Host '============================================================' -ForegroundColor White

# ============================================================ desinstalar

if ($Desinstalar) {
    Seccion 'Desinstalar'
    Set-Content -Path $flag -Value (Get-Date -Format 'o') -Encoding ASCII
    $plazo = (Get-Date).AddSeconds(30)
    while ((Get-Process scadamtto -ErrorAction SilentlyContinue) -and ((Get-Date) -lt $plazo)) {
        Start-Sleep -Milliseconds 500
    }
    Get-Process scadamtto -ErrorAction SilentlyContinue | Stop-Process -Force
    Res 'Desinstalar' 'adquisidor detenido' 'OK'
    if (Get-ScheduledTask -TaskName $Tarea -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Tarea -Confirm:$false
        Res 'Desinstalar' "tarea '$Tarea' eliminada" 'CAMBIADO'
    } else {
        Res 'Desinstalar' "tarea '$Tarea'" 'OK' 'no existia'
    }
    try {
        Remove-MpPreference -ExclusionPath $Raiz
        Res 'Desinstalar' 'exclusion de Defender' 'CAMBIADO'
    } catch {
        Res 'Desinstalar' 'exclusion de Defender' 'AVISO' $_.Exception.Message
    }
    Write-Host "`nEnergia, recuperacion y updates quedan como estaban." -ForegroundColor Gray
    exit 0
}

# ======================================================= habilitar updates

if ($HabilitarUpdates) {
    Seccion 'Windows Update a valores de fabrica'
    $pol = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
    foreach ($n in 'NoAutoUpdate', 'NoAutoRebootWithLoggedOnUsers') {
        Remove-ItemProperty -Path $pol -Name $n -ErrorAction SilentlyContinue
    }
    Res 'Updates' 'politicas de Windows Update' 'CAMBIADO' 'eliminadas'
    try {
        Set-Service -Name wuauserv -StartupType Manual
        Res 'Updates' 'servicio wuauserv' 'CAMBIADO' 'Manual (default)'
    } catch { Res 'Updates' 'servicio wuauserv' 'ERROR' $_.Exception.Message }
    try {
        Escribir-Registro 'HKLM:\SYSTEM\CurrentControlSet\Services\UsoSvc' 'Start' 2
        Res 'Updates' 'servicio UsoSvc' 'CAMBIADO' 'Automatico (default)'
    } catch { Res 'Updates' 'servicio UsoSvc' 'AVISO' $_.Exception.Message }
    Write-Host "`nReiniciar para que tome efecto." -ForegroundColor Gray
    exit 0
}

# ============================================================ paquete

Seccion 'Paquete'
if ($hayExe) {
    Res 'Paquete' 'scadamtto.exe' 'OK' (Join-Path $Raiz 'scadamtto.exe')
} elseif ($Aplicar) {
    Res 'Paquete' 'scadamtto.exe' 'ERROR' 'no esta junto a este script: correrlo desde la carpeta del paquete'
    exit 1
} else {
    Res 'Paquete' 'scadamtto.exe' 'AVISO' 'no esta (proyecto de desarrollo): se verifica igual'
}
if (Test-Path $siteToml) {
    Res 'Paquete' 'config\site.toml' 'OK'
} elseif ($Aplicar) {
    Res 'Paquete' 'config\site.toml' 'ERROR' 'copiar config\site.example.toml a config\site.toml y completarlo'
    exit 1
} else {
    Res 'Paquete' 'config\site.toml' 'AVISO' 'no existe'
}
if ($hayExe -and -not (Test-Path $watchdog)) {
    Res 'Paquete' 'watchdog.ps1' 'ERROR' 'falta junto a este script'
    if ($Aplicar) { exit 1 }
}
if ($Raiz -like "$env:SystemDrive\Users\*") {
    Res 'Paquete' 'ubicacion' 'AVISO' 'esta dentro de un perfil de usuario; se recomienda C:\scadaMtto'
} else {
    Res 'Paquete' 'ubicacion' 'OK' $Raiz
}

# Un zip copiado de otro equipo deja todos los archivos marcados como
# "descargados" (stream Zone.Identifier). Al abrirlos a mano (correr.cmd, doble
# clic) Windows pregunta antes de ejecutarlos, y corriendo como SYSTEM esa
# pregunta queda en una pantalla que nadie ve. El watchdog ya no depende de
# esto, pero se desbloquea igual para que nada mas tropiece con la marca.
Asegurar 'Paquete' 'archivos desbloqueados (sin marca de descarga)' 0 {
    @(Get-ChildItem -Path $Raiz -Recurse -File -ErrorAction SilentlyContinue |
      Where-Object { Get-Item -LiteralPath $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue }).Count
} { Get-ChildItem -Path $Raiz -Recurse -File | Unblock-File }

# ============================================================ energia

Seccion 'Energia'

$ALTO_RENDIMIENTO = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'
Asegurar 'Energia' 'plan de energia Alto rendimiento' 'si' {
    $activo = (& powercfg /getactivescheme) -join ' '
    if ($activo -match $ALTO_RENDIMIENTO -or $activo -match '(High performance|Alto rendimiento)') { 'si' } else { $activo.Trim() }
} {
    $lista = (& powercfg /list) -join "`n"
    if ($lista -match $ALTO_RENDIMIENTO) {
        & powercfg /setactive $ALTO_RENDIMIENTO | Out-Null
    } else {
        # Algunas imagenes de Windows 11 no traen el plan visible: se duplica
        # desde la plantilla y se activa la copia.
        $nuevo = (& powercfg -duplicatescheme $ALTO_RENDIMIENTO) -join ' '
        if ($nuevo -match '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})') {
            & powercfg /setactive $Matches[1] | Out-Null
        } else {
            throw "no se pudo crear el plan: $nuevo"
        }
    }
}

# subgrupo, ajuste, valor deseado, descripcion
$ajustes = @(
    @('SUB_SLEEP', 'STANDBYIDLE', 0, 'suspender: nunca'),
    @('SUB_SLEEP', 'HIBERNATEIDLE', 0, 'hibernar: nunca'),
    @('SUB_SLEEP', 'HYBRIDSLEEP', 0, 'suspension hibrida: no'),
    @('SUB_DISK', 'DISKIDLE', 0, 'apagar disco: nunca'),
    @('SUB_VIDEO', 'VIDEOIDLE', 0, 'apagar monitor: nunca'),
    # USB: suspension selectiva deshabilitada
    @('2a737441-1930-4402-8d77-b2bebba308a3', '48e6b7a6-50f5-4782-a5d4-53bb8f07e226', 0, 'USB: suspension selectiva off'),
    # PCI Express: administracion de energia del estado de vinculo (ASPM) off
    @('SUB_PCIEXPRESS', 'ASPM', 0, 'PCIe: ahorro de energia del vinculo off'),
    # Adaptador inalambrico: modo de ahorro = maximo rendimiento
    @('19cbb8fa-5279-450e-9fac-8a3d5fedd0c1', '12bbebe6-58d6-4636-95bb-3217ef867c1a', 0, 'Wi-Fi: maximo rendimiento'),
    # Boton de encendido = apagar (3). Si alguien lo toca, que no lo deje
    # suspendido sin adquirir: apagado, al menos vuelve con el boton.
    @('SUB_BUTTONS', 'PBUTTONACTION', 3, 'boton de encendido: apagar')
)
foreach ($a in $ajustes) {
    $sub = $a[0]; $set = $a[1]; $val = $a[2]
    Asegurar 'Energia' $a[3] $val { Leer-Powercfg $sub $set } { Escribir-Powercfg $sub $set $val }
}

Asegurar 'Energia' 'hibernacion deshabilitada' 0 {
    Leer-Registro 'HKLM:\SYSTEM\CurrentControlSet\Control\Power' 'HibernateEnabled'
} { & powercfg /hibernate off | Out-Null }

# El Inicio rapido es una hibernacion parcial: tras un corte de energia arranca
# con el kernel de una sesion que no termino bien.
Asegurar 'Energia' 'Inicio rapido deshabilitado' 0 {
    Leer-Registro 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' 'HiberbootEnabled'
} { Escribir-Registro 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' 'HiberbootEnabled' 0 }

# ========================================================= recuperacion

Seccion 'Recuperacion ante cortes y fallas'

# Lo mas importante para cortes de luz: sin esto Windows puede quedarse en la
# pantalla de Reparacion automatica esperando a alguien.
Asegurar 'Recuperacion' 'arranque ignora apagados bruscos (bootstatuspolicy)' 'ignoreallfailures' {
    $bcd = (& bcdedit /enum '{current}' 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw 'bcdedit requiere Administrador' }
    if ($bcd -match 'bootstatuspolicy\s+(\S+)') { $Matches[1].ToLower() } else { 'displayallfailures (default)' }
} {
    & bcdedit /set '{current}' bootstatuspolicy ignoreallfailures | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'bcdedit fallo' }
}
Asegurar 'Recuperacion' 'sin Reparacion automatica (recoveryenabled)' 'no' {
    $bcd = (& bcdedit /enum '{current}' 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw 'bcdedit requiere Administrador' }
    if ($bcd -match 'recoveryenabled\s+(\S+)') { $Matches[1].ToLower() } else { 'yes (default)' }
} {
    & bcdedit /set '{current}' recoveryenabled No | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'bcdedit fallo' }
}
Asegurar 'Recuperacion' 'reinicio automatico ante pantallazo azul' 1 {
    Leer-Registro 'HKLM:\SYSTEM\CurrentControlSet\Control\CrashControl' 'AutoReboot'
} { Escribir-Registro 'HKLM:\SYSTEM\CurrentControlSet\Control\CrashControl' 'AutoReboot' 1 }

# Si el exe se cae, que Windows no deje un dialogo "dejo de funcionar" abierto:
# en una sesion sin nadie mirando ese dialogo puede frenar el relanzamiento.
Asegurar 'Recuperacion' 'sin dialogos de error de programas (WER)' 1 {
    Leer-Registro 'HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting' 'DontShowUI'
} { Escribir-Registro 'HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting' 'DontShowUI' 1 }

Res 'Recuperacion' 'BIOS: Restore after AC Power Loss = Power On' 'MANUAL' 'Settings > Advanced > Power Management Setup'
Res 'Recuperacion' 'BIOS: ErP Ready = Disabled' 'MANUAL' 'mismo menu; con ErP activo no vuelve tras un corte'

# ================================================================ red

Seccion 'Red'

$placas = @(Get-NetAdapter -Physical -ErrorAction SilentlyContinue)
if (-not $placas) { Res 'Red' 'placas fisicas' 'AVISO' 'no se encontro ninguna' }

# Claves del driver (RegistryKeyword) que ahorran energia a costa de cortar o
# degradar el enlace. Se usan las claves y no el nombre visible porque este
# cambia segun driver e idioma.
$clavesAhorro = @('*EEE', 'AdvancedEEE', 'EnableGreenEthernet', 'GigaLite', 'PowerSavingMode', '*SelectiveSuspend')

# Clave de registro de clase de las placas de red. Cada placa tiene una subclave
# 00NN cuyo NetCfgInstanceId es el InterfaceGuid de la placa.
$claseRed = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}'

function Clave-Placa([string]$guid) {
    foreach ($sk in Get-ChildItem -Path $claseRed -ErrorAction SilentlyContinue) {
        $id = (Get-ItemProperty -Path $sk.PSPath -Name NetCfgInstanceId -ErrorAction SilentlyContinue).NetCfgInstanceId
        if ($id -eq $guid) { return $sk.PSPath }
    }
    return $null
}

foreach ($p in $placas) {
    $n = $p.Name
    # La casilla "Permitir que el equipo apague este dispositivo para ahorrar
    # energia" se maneja por registro (PnPCapabilities = 24), el metodo que
    # documenta Microsoft. Set-NetAdapterPowerManagement -AllowComputerToTurnOff
    # Device ya no existe en Windows 11 26H2: fallo en arg-scada01.
    $clave = Clave-Placa $p.InterfaceGuid
    if (-not $clave) {
        Res 'Red' "$n : Windows no puede apagarla para ahorrar energia" 'AVISO' 'no se encontro su clave de registro'
    } else {
        Asegurar 'Red' "$n : Windows no puede apagarla para ahorrar energia" 24 {
            Leer-Registro $clave 'PnPCapabilities'
        } { Escribir-Registro $clave 'PnPCapabilities' 24 }
    }

    # -RegistryKeyword acepta comodines y '*EEE' tambien matchearia 'AdvancedEEE':
    # se traen todas y se filtra por igualdad exacta.
    $avanzadas = @(Get-NetAdapterAdvancedProperty -Name $n -AllProperties -ErrorAction SilentlyContinue)
    $encontradas = 0
    foreach ($k in $clavesAhorro) {
        $prop = $avanzadas | Where-Object { $_.RegistryKeyword -eq $k } | Select-Object -First 1
        if (-not $prop) { continue }
        $encontradas++
        Asegurar 'Red' "$n : $($prop.DisplayName) [$k]" '0' {
            "$(@($prop.RegistryValue)[0])"
        } { $prop | Set-NetAdapterAdvancedProperty -RegistryValue 0 -NoRestart -ErrorAction Stop }
    }
    if ($encontradas -eq 0 -and $p.PhysicalMediaType -match '802\.3') {
        # Pasa con el driver Realtek que trae Windows: no publica estas opciones
        # y quedan en el valor de fabrica del driver. Si hubiera cortes de enlace,
        # instalar el driver completo de Realtek/MSI y volver a correr el script.
        Res 'Red' "$n : ahorro de energia del driver (EEE / Green Ethernet)" 'OK' 'el driver no expone estos ajustes'
    }
}

$gateways = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
              Where-Object { (Get-NetAdapter -InterfaceIndex $_.ifIndex -ErrorAction SilentlyContinue).Status -eq 'Up' })
if ($gateways.Count -eq 1) {
    Res 'Red' 'un unico default gateway' 'OK' ("{0} por {1}" -f $gateways[0].NextHop, $gateways[0].InterfaceAlias)
} elseif ($gateways.Count -eq 0) {
    Res 'Red' 'un unico default gateway' 'AVISO' 'no hay ninguno: sin el, la base de datos de IT no es alcanzable'
} else {
    $lista = ($gateways | ForEach-Object { "$($_.NextHop) ($($_.InterfaceAlias))" }) -join ', '
    Res 'Red' 'un unico default gateway' 'AVISO' "hay $($gateways.Count): $lista. La placa al MikroTik va SIN gateway"
}

if (Test-Path $siteToml) {
    $site = Leer-Toml $siteToml
    $plc = $site.Keys | Where-Object { $_ -like 'plc.*' } | Sort-Object |
           Where-Object { $site[$_]['habilitado'] -ne 'false' } | Select-Object -First 1
    if ($plc) {
        $c = $site[$plc]
        if ($c['marca'] -eq 'mock') {
            Res 'Red' "PLC $plc" 'AVISO' 'site.toml tiene marca = "mock": no se va a leer el PLC real'
        } else {
            $ip = $c['ip']; $puerto = [int]$c['puerto']
            $origen = Probar-Tcp $ip $puerto
            if ($origen) {
                Res 'Red' "PLC $plc ($ip`:$puerto)" 'OK' "responde, sale por $origen"
                if ($origen -ne $IpRecoleccion) {
                    Res 'Red' 'IP de origen hacia el MikroTik' 'AVISO' "sale por $origen; la regla NAT del hEX espera $IpRecoleccion"
                }
            } else {
                Res 'Red' "PLC $plc ($ip`:$puerto)" 'AVISO' 'no responde (cable, IP de la placa, o reglas NAT del MikroTik)'
            }
        }
    }
    $db = $site['db']
    if ($db) {
        $puertoDb = 1433
        if ($db['puerto']) { $puertoDb = [int]$db['puerto'] }
        $origen = Probar-Tcp $db['servidor'] $puertoDb
        if ($origen) {
            Res 'Red' ("SQL Server {0}:{1}" -f $db['servidor'], $puertoDb) 'OK' "responde, sale por $origen"
        } else {
            Res 'Red' ("SQL Server {0}:{1}" -f $db['servidor'], $puertoDb) 'AVISO' 'no responde'
        }
    }
}

$local = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object IPAddress -eq $IpRecoleccion)
if ($local) {
    $alias = $local[0].InterfaceAlias
    $gw = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -InterfaceAlias $alias -ErrorAction SilentlyContinue
    if ($gw) {
        Res 'Red' "placa de recoleccion ($alias, $IpRecoleccion)" 'AVISO' 'tiene default gateway: tiene que ir SIN gateway'
    } else {
        Res 'Red' "placa de recoleccion ($alias, $IpRecoleccion)" 'OK' 'sin gateway'
    }
} else {
    Res 'Red' "placa con IP $IpRecoleccion" 'MANUAL' 'ponerle esa IP fija (/24, sin gateway) a la placa que va al MikroTik'
}

# ================================================================ hora

Seccion 'Hora'
# El adquisidor escribe FechaHora y FechaLectura con el reloj de esta PC: si
# atrasa, el SCADA ve datos viejos aunque esten frescos.
Asegurar 'Hora' 'servicio de hora (w32time) automatico' 'Automatic' {
    "$((Get-Service w32time).StartType)"
} { Set-Service -Name w32time -StartupType Automatic }
if ($Aplicar) {
    try {
        Start-Service w32time -ErrorAction SilentlyContinue
        & w32tm /resync /force 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Res 'Hora' 'sincronizacion' 'OK' (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
        } else {
            Res 'Hora' 'sincronizacion' 'AVISO' 'w32tm /resync fallo: revisar que haya un servidor de hora alcanzable'
        }
    } catch { Res 'Hora' 'sincronizacion' 'AVISO' $_.Exception.Message }
}

# ============================================================ updates

Seccion 'Windows Update (desactivado)'
$pol = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
# La politica es lo que realmente sostiene la decision: WaaSMedicSvc esta
# protegido y puede volver a habilitar el servicio por su cuenta.
Asegurar 'Updates' 'politica: sin actualizaciones automaticas' 1 {
    Leer-Registro $pol 'NoAutoUpdate'
} { Escribir-Registro $pol 'NoAutoUpdate' 1 }
Asegurar 'Updates' 'politica: sin reinicio automatico' 1 {
    Leer-Registro $pol 'NoAutoRebootWithLoggedOnUsers'
} { Escribir-Registro $pol 'NoAutoRebootWithLoggedOnUsers' 1 }
Asegurar 'Updates' 'servicio wuauserv deshabilitado' 'Disabled' {
    "$((Get-Service wuauserv).StartType)"
} {
    Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
    Set-Service -Name wuauserv -StartupType Disabled
}
# UsoSvc (Update Orchestrator) va aparte: en algunas compilaciones su clave de
# registro esta protegida y no se deja cambiar ni siendo Administrador. No es
# grave -- la politica NoAutoUpdate ya frena las instalaciones -- asi que un
# rechazo se reporta como AVISO y no como ERROR.
$usoRuta = 'HKLM:\SYSTEM\CurrentControlSet\Services\UsoSvc'
$usoActual = Leer-Registro $usoRuta 'Start'
if ("$usoActual" -eq '4') {
    Res 'Updates' 'servicio UsoSvc deshabilitado' 'OK'
} elseif (-not $Aplicar) {
    Res 'Updates' 'servicio UsoSvc deshabilitado' 'PENDIENTE' "Start actual: '$usoActual'"
} else {
    try {
        Stop-Service -Name UsoSvc -Force -ErrorAction SilentlyContinue
        Escribir-Registro $usoRuta 'Start' 4
        Res 'Updates' 'servicio UsoSvc deshabilitado' 'CAMBIADO' "era '$usoActual'"
    } catch {
        Res 'Updates' 'servicio UsoSvc deshabilitado' 'AVISO' 'Windows protege este servicio; la politica NoAutoUpdate alcanza'
    }
}

# ============================================================ defender

Seccion 'Defender'
Asegurar 'Defender' 'exclusion de la carpeta del adquisidor' 'si' {
    $mp = Get-MpPreference -ErrorAction Stop
    # Sin Administrador, Defender devuelve un texto "N/A: Must be an administrator
    # to view exclusions" en lugar de la lista.
    if (@($mp.ExclusionPath) -match '^N/A') { throw 'ver las exclusiones requiere Administrador' }
    if (@($mp.ExclusionPath) -contains $Raiz) { 'si' } else { 'no' }
} { Add-MpPreference -ExclusionPath $Raiz -ErrorAction Stop }

# ============================================================ tarea

Seccion 'Tarea programada'

function Leer-Tarea {
    $t = Get-ScheduledTask -TaskName $Tarea -ErrorAction SilentlyContinue
    if (-not $t) { return 'no existe' }
    $atStartup = @($t.Triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskBootTrigger' }).Count -gt 0
    # Duracion vacia = la repeticion no termina nunca.
    $repite = @($t.Triggers | Where-Object {
        $_.Repetition.Interval -eq 'PT5M' -and -not $_.Repetition.Duration }).Count -gt 0
    $ok = ($t.Principal.UserId -match 'SYSTEM') -and $atStartup -and $repite -and
          ($t.Settings.ExecutionTimeLimit -eq 'PT0S') -and ($t.Settings.MultipleInstances -eq 'IgnoreNew') -and
          ($t.Settings.Priority -eq 4) -and ($t.Actions[0].Arguments -match [regex]::Escape($watchdog))
    if ($ok) { return 'correcta' }
    return 'desactualizada (ONLOGON vieja o parametros distintos)'
}

Asegurar 'Tarea' "tarea '$Tarea': al encender, como SYSTEM, sin limite de tiempo" 'correcta' {
    Leer-Tarea
} {
    $accion = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdog`"" `
        -WorkingDirectory $Raiz

    $alEncender = New-ScheduledTaskTrigger -AtStartup
    $alEncender.Delay = 'PT30S'    # da tiempo a que levanten las placas de red

    # Relanza el watchdog si el propio watchdog muriera. Con IgnoreNew nunca
    # duplica: si ya esta corriendo, la repeticion no hace nada.
    $repeticion = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5)

    $config = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew `
        -Priority 4
    # ExecutionTimeLimit 0 = sin limite. El default de Windows (72 h) mataria la
    # adquisicion al tercer dia. Priority 4 = normal; el default (7) le da al
    # proceso prioridad de CPU y disco por debajo de lo normal.

    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

    Register-ScheduledTask -TaskName $Tarea -Action $accion -Trigger @($alEncender, $repeticion) `
        -Settings $config -Principal $principal -Force `
        -Description 'scadaMtto: adquisicion PLC -> SQL Server. Lanza watchdog.ps1, que relanza scadamtto.exe si termina.' |
        Out-Null

    $comprobacion = Leer-Tarea
    if ($comprobacion -ne 'correcta') { throw "se registro pero quedo: $comprobacion" }
}

# ============================================================ arranque

if ($Aplicar -and $hayExe -and -not $NoIniciar) {
    Seccion 'Arranque'
    if (Test-Path $flag) {
        Remove-Item -Force $flag
        Res 'Arranque' 'stop.flag' 'CAMBIADO' 'borrado para que el watchdog arranque'
    }
    if (Get-Process scadamtto -ErrorAction SilentlyContinue) {
        Res 'Arranque' 'adquisidor' 'OK' 'ya estaba corriendo'
    } else {
        Start-ScheduledTask -TaskName $Tarea
        $p = $null
        for ($i = 0; $i -lt 20 -and -not $p; $i++) {
            Start-Sleep -Seconds 1
            $p = Get-Process scadamtto -ErrorAction SilentlyContinue
        }
        if ($p) {
            Res 'Arranque' 'adquisidor' 'OK' ("corriendo, PID {0}" -f $p.Id)
        } else {
            Res 'Arranque' 'adquisidor' 'AVISO' 'no aparecio en 20 s: mirar logs\watchdog.log'
        }
    }
}

# ============================================================== resumen

Seccion 'Resumen'
$cuenta = $resultados | Group-Object Estado | Sort-Object Name
foreach ($g in $cuenta) { Write-Host ('  {0,-13} {1}' -f $g.Name, $g.Count) }

$manual = @($resultados | Where-Object Estado -eq 'MANUAL')
$problemas = @($resultados | Where-Object { $_.Estado -in @('ERROR', 'AVISO', 'PENDIENTE') })
if ($manual) {
    Write-Host "`nPendiente a mano:" -ForegroundColor Magenta
    $manual | ForEach-Object { Write-Host "  - $($_.Item)  ($($_.Detalle))" }
}
if ($problemas) {
    Write-Host "`nPara revisar:" -ForegroundColor Yellow
    $problemas | ForEach-Object { Write-Host "  - [$($_.Estado)] $($_.Item)  $($_.Detalle)" }
}
if ($Aplicar) {
    Write-Host "`nReiniciar el equipo para que tomen efecto los cambios de red, hibernacion y arranque." -ForegroundColor Cyan
    Write-Host 'Despues del reinicio, SIN iniciar sesion, el adquisidor tiene que estar corriendo.' -ForegroundColor Cyan
}

# Copia del reporte en logs\, para dejar constancia de como quedo el equipo.
try {
    $dirLog = Join-Path $Raiz 'logs'
    New-Item -ItemType Directory -Force -Path $dirLog | Out-Null
    $archivo = Join-Path $dirLog ('preparar_pc_{0}.txt' -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
    $resultados | Format-Table -AutoSize -Wrap | Out-String -Width 220 | Set-Content -Path $archivo -Encoding UTF8
    Write-Host "`nReporte guardado en $archivo" -ForegroundColor Gray
} catch { }

if (@($resultados | Where-Object Estado -eq 'ERROR').Count -gt 0) { exit 1 }
exit 0
