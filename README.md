# scadaMtto

Adquisidor de datos de PLC hacia SQL Server. Corre 24/7 en una PC de planta con
dos placas de red: una a la red del PLC y otra a la red de la base de datos.

Soporta **Mitsubishi** (MC Protocol 3E, ASCII o binario) y **Siemens**
(S7-1200/1500/300/400 via snap7). La lista de tags es configuración, no código.

## Arranque rápido

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy config\site.example.toml config\site.toml    # y completar IPs y credenciales
.venv\Scripts\python.exe scripts\test_db.py       # verifica la base
.venv\Scripts\python.exe scripts\read_once.py     # verifica el PLC
.venv\Scripts\python.exe main.py                  # arranca el servicio
```

Dashboard en <http://localhost:8080>: pestaña **Monitor** para el estado en vivo y
pestaña **Variables** para dar de alta, editar o borrar tags sin reiniciar el
proceso. Se detiene con Ctrl+C.

## Configuración

| Archivo | Qué tiene | ¿Se versiona? |
|---|---|---|
| `config/app.default.toml` | Semilla de los parámetros de la app | sí |
| `config/app.toml` | Copia editable, se crea sola en el 1er arranque | no |
| `config/site.toml` | IPs, puertos y credenciales de **esta** máquina | **no** |
| `config/tags.toml` | La tabla de tags | sí |

Para **ampliar la lista de datos a recolectar solo se edita `tags.toml`**:

```toml
[[tag]]
nombre    = "D5002"      # va literal a RegistroPLC.NombreTag (máx. 50 caracteres)
plc       = "mitsu_q1"   # clave del PLC en site.toml
direccion = "D5002"      # D5002 / M1000 / W1A0 | DB1.DBW0 / M100.0
tipo      = "int16"      # bit | int16 | uint16 | int32 | uint32 | float32
escala    = 1.0          # valor_final = crudo * escala + offset
offset    = 0.0
scan_ms   = 1000
registro  = "intervalo"  # "intervalo" graba cada scan
                         # "cambio"    graba solo si cambió más que banda_muerta
banda_muerta = 0.0
heartbeat_s  = 0         # fuerza una fila cada N s aunque no cambie (0 = nunca)
```

También se editan desde la pestaña **Variables** del dashboard, que reescribe este
mismo archivo (deja copia en `tags.toml.bak`) y recarga los hilos de scan en
caliente. Si algo no valida, no se escribe nada.

En `modo = "historial"` conviene `registro = "cambio"` con `banda_muerta` y
`heartbeat_s`: es lo que evita que la tabla crezca con filas idénticas. En
`modo = "actual"` da igual, porque la fila se pisa.

La password de la base puede ir en `site.toml` o en la variable de entorno
`SCADAMTTO_DB_PASSWORD`, que tiene prioridad.

**Reloj:** con `hora_servidor = true` (el valor por defecto), `FechaHora` y
`FechaLectura` salen del reloj del **SQL Server**. El adquisidor manda cuánto
hace que leyó cada muestra y el servidor lo resta de `SYSDATETIME()`. Así una
PC de adquisición con la hora corrida no afecta la base, y las muestras que
quedaron en el buffer durante un corte conservan su hora real. Con `false` se
usa el reloj de esta PC, que era el comportamiento anterior.

## Cómo escribe en la base

Hay dos modos, en `[db].modo` de `site.toml`.

### `modo = "actual"` (por defecto)

Una fila **por variable** en `test.ValorActual`, actualizada en el lugar. La tabla
no crece. Es lo que lee el SCADA. Crearla con `scripts/sql/crear_valoractual.sql`.

| Columna | Contenido |
|---|---|
| `NombreTag` | **PK** — el campo `nombre` del tag |
| `Valor` | Valor escalado. `NULL` si la lectura falló |
| `Estado` | Calidad: `1` lectura buena, `0` error/timeout |
| `FechaHora` | Cuándo **cambió** el valor por última vez |
| `FechaLectura` | Cuándo se **leyó** por última vez, aunque no cambiara |

Los dos timestamps existen para que el SCADA distinga *"esta variable no se mueve"*
de *"el adquisidor está caído"*: con uno solo las dos situaciones se ven igual.
Si `FechaLectura` tiene más de N segundos, nadie está leyendo ese tag.

### `modo = "historial"`

Una fila por muestra en `test.RegistroPLC`. Sirve para análisis, pero crece sin
límite; conviene usarlo con `registro = "cambio"` y `banda_muerta`.

| Columna | Contenido |
|---|---|
| `FechaHora` | Momento del **scan**, no del INSERT (ver store-and-forward) |
| `NombreTag` | El campo `nombre` del tag |
| `Valor` | Valor escalado. `NULL` si la lectura falló |
| `Estado` | Calidad: `1` lectura buena, `0` error/timeout |

`Valor` es `real` (float32), exacto hasta 2^24. Alcanza para `int16`, `uint16` y
`bit`. Si más adelante entran contadores `int32` grandes, hay que migrar esa
columna a `float`.

Ante una falla de lectura se graba **una** fila con `Estado = 0`, en la
transición de buena a mala. No se repite en cada scan: una caída de media hora
metería miles de filas idénticas y lo que importa es cuándo se cortó y cuándo
volvió.

## Arquitectura

```
PLC ──► Poller (1 hilo por PLC) ──► buffer.sqlite ──► DbWriter ──► SQL Server
                                          │
                                          └────────► dashboard web (:8080)
```

- **Poller**: dueño exclusivo del socket del PLC. Ni pymcprotocol ni snap7 son
  thread-safe, y el Q tiene **una sola conexión MC** disponible. Agrupa los tags
  contiguos en lecturas batch y reconecta con backoff exponencial.
- **buffer.sqlite** (WAL): store-and-forward. Si se cae la DB o la red, el scan
  sigue y no se pierde ninguna muestra; tampoco se pierde ante un corte de luz,
  porque es durable en disco. Al superar `buffer_max_filas` se descarta lo más
  viejo.
- **DbWriter**: único que habla con SQL Server. Inserta un lote por transacción y
  recién borra del buffer **después** del commit: no se pierde ni se duplica.

## Scripts de diagnóstico

```powershell
.venv\Scripts\python.exe scripts\test_db.py      # conecta, inserta, lee y borra
.venv\Scripts\python.exe scripts\read_once.py    # lee los tags una vez
.venv\Scripts\python.exe scripts\probe_plc.py    # diagnóstico de conexión al PLC
.venv\Scripts\python.exe scripts\probe_plc.py --barrer   # busca el puerto MC
.venv\Scripts\python.exe -m pytest               # tests unitarios
```

## Notas de PLC

### Mitsubishi Q (Ethernet incorporado)

- **El puerto del Open Setting se muestra en HEX.** Un `2000` en esa tabla es
  **8192 decimal**. Es el error más fácil de cometer.
- El `commtype` de `site.toml` tiene que coincidir con el *Communication data
  code* del PLC (ASCII o binario).
- Si el PLC no tiene *Subnet mask* ni *Default router IP* cargados, **solo se lo
  alcanza desde su misma subred**: no se puede rutear ni llegar por VPN.
- Cada entrada *MC Protocol* del Open Setting acepta **un solo cliente TCP**.
  GX Works **no** la ocupa (usa las entradas *MELSOFT connection*), pero un HMI sí
  puede. Si hay que compartir, se abre una segunda entrada en otro puerto.
- ⚠️ El *Communication data code* del proyecto de GX Works puede **no coincidir**
  con lo que está escrito en el PLC. Verificalo siempre con `probe_plc.py`, que
  prueba ASCII y binario y te dice cuál responde. Si bajás el proyecto con el
  valor equivocado, se cae la comunicación de todos los clientes, HMI incluido.

### Siemens S7-1200 / S7-1500

Viene implementado pero con `habilitado = false`. Al encenderlo, revisar:

1. Habilitar *"Permitir acceso vía comunicación PUT/GET del interlocutor
   remoto"* (Propiedades del CPU → Protección y seguridad → Mecanismos de
   conexión).
2. Desactivar *"Acceso optimizado al bloque"* en los DB a leer.
3. `rack = 0`, `slot = 1` (probar `slot = 0` si no conecta).

## Red: la PC de recolección y las celdas

Cada celda tiene un **MikroTik hEX** que aísla su red interna. Todas las celdas
usan `192.168.0.0/24` puertas adentro, y se distinguen por la IP del hEX en la
red de recolección:

```
PC recoleccion                hEX celda1                   PLC
192.168.30.10/24  ──ether1──► 192.168.30.101/24            192.168.0.101
   (sin gateway)              192.168.0.254/24 ──bridge──►  (sin gateway)
        │
        └── Wi-Fi 172.17.x (con gateway) ──► SQL Server 172.17.132.153
```

**La app le habla al hEX, no al PLC.** En `site.toml` va `ip = "192.168.30.101"`;
el `dst-nat` del MikroTik lo lleva a `192.168.0.101`. La IP real del PLC nunca
aparece en la PC — así no choca con la otra red `192.168.0.0/24` que existe en la
red corporativa.

Reglas necesarias en cada hEX, una vez por puerto de PLC:

```
/ip firewall nat add chain=dstnat action=dst-nat protocol=tcp   in-interface=ether1 src-address=192.168.30.10 dst-address=192.168.30.101   dst-port=8192-8193 to-addresses=192.168.0.101   comment="MC Protocol Mitsubishi Q"

/ip firewall nat add chain=srcnat action=masquerade protocol=tcp   dst-address=192.168.0.101 dst-port=8192-8193 out-interface=bridge-celda   comment="MC Mitsubishi sin gateway"
```

El `masquerade` **no es opcional**: el PLC no tiene *default router*, así que sin
él contesta al hEX y nunca a `192.168.30.10`.

En la PC: la placa de la **DB** lleva el **único** default gateway; la placa de
recolección va **sin gateway**.

```powershell
Get-NetRoute -AddressFamily IPv4 | Where-Object DestinationPrefix -eq '0.0.0.0/0'
Test-NetConnection 192.168.30.101 -Port 8192   # SourceAddress = 192.168.30.10
```

Diagnóstico si algo no responde: `/ip firewall nat print stats` en el hEX. Si el
contador del `dstnat` está en 0, el tráfico no llega a matchear la regla.

## Despliegue en la PC de adquisición

### Construir el paquete

Desde Git Bash, en la raíz del proyecto:

```bash
./build.sh --con-credenciales
```

Corre los tests, compila `scadamtto.exe`, valida los `.ps1` y deja
`release/scadaMtto_vN.zip`. Sin `--con-credenciales` el paquete no incluye
`config/site.toml`, que lleva la password de la base.

### Instalar

1. Descomprimir en `C:\scadaMtto`: fuera del perfil de usuario, porque el
   servicio corre como SYSTEM.
2. PowerShell **como Administrador**:
   ```powershell
   cd C:\scadaMtto
   powershell -ExecutionPolicy Bypass -File .\preparar_pc.ps1
   ```
3. BIOS (no lo puede hacer ningún script): *Restore after AC Power Loss = Power On*
   y *ErP Ready = Disabled*. En la MSI PRO Cubi: *Settings → Advanced → Power
   Management Setup*.
4. Reiniciar: **sin iniciar sesión**, el adquisidor tiene que estar corriendo.

`preparar_pc.ps1` es idempotente y muestra un reporte OK / CAMBIADO / AVISO / MANUAL:

| Área | Qué deja |
|---|---|
| Energía | Plan Alto rendimiento; nunca suspende, hiberna ni apaga disco; sin Inicio rápido; sin ahorro en USB ni PCIe; botón de encendido = apagar |
| Recuperación | Sin pantalla de *Reparación automática* tras un corte (`bcdedit`); reinicio solo ante pantallazo azul; sin diálogos de error que frenen el relanzamiento |
| Red | Sin ahorro de energía en las placas (EEE, Green Ethernet…); valida un único gateway, el PLC y la DB |
| Hora | `w32time` automático y sincronizado (los timestamps salen de esta PC) |
| Windows Update | Desactivado (`-HabilitarUpdates` lo revierte) |
| Defender | Excluye la carpeta del adquisidor |
| Tarea | `scadaMtto`: al encender, como SYSTEM, sin límite de tiempo, prioridad normal; repite cada 5 min por si muere el watchdog |

Opciones: `-Verificar` (solo lectura), `-Desinstalar`, `-HabilitarUpdates`,
`-NoIniciar`, `-IpRecoleccion`.

Dos detalles de la tarea que no son los de fábrica y que importan: Windows **mata
cualquier tarea programada a las 72 h** si no se le dice lo contrario, y la corre
con **prioridad baja** de CPU y disco.

### Cómo se mantiene vivo

```
Tarea (al encender + cada 5 min) ──► watchdog.ps1 ──► scadamtto.exe
                                         │  si termina: lo relanza (5 s → 60 s si
                                         │  entra en crash-loop)
                                         └─ si existe stop.flag: no relanza
```

- **Instancia única**: un cerrojo en el puerto local 47821. Una segunda instancia
  sale con código 3, así nunca hay dos procesos peleándose la conexión MC del PLC.
- **Parada limpia**: crear `stop.flag` en la raíz. El adquisidor cierra el socket
  del PLC y drena el buffer. Matar el proceso deja la conexión MC ocupada en el
  PLC hasta que expira.

### Operación

| Acceso | Qué hace |
|---|---|
| `iniciar.cmd` | Borra `stop.flag` y arranca la tarea |
| `detener.cmd` | Parada limpia; queda detenido hasta `iniciar.cmd` |
| `estado.cmd` | Proceso, tarea, últimas líneas del watchdog, PLC y DB |
| `ver_log.cmd` | `logs\scadamtto.log` en vivo |
| `diagnostico.cmd` | `testdb` + `probe` + `leer` |
| `correr.cmd` | Arranque manual con consola, para depurar (detener el servicio antes) |

Códigos de salida, anotados en `logs\watchdog.log`: `0` parada pedida, `1` se
murieron los hilos de scan, `2` configuración inválida, `3` ya había otra instancia.

## Dependencias

Todo el árbol es Python puro o ctypes: **no requiere compilador ni driver ODBC**,
lo que evita tener que instalar Visual C++ Build Tools en la PC de planta.

- `python-tds` — SQL Server (protocolo TDS en Python puro, en lugar de pyodbc)
- `pymcprotocol` — Mitsubishi MC Protocol 3E
- `python-snap7` — Siemens S7
- `loguru` — logging rotativo (`logs/scadamtto.log`, 5 MB, 30 días)

El dashboard usa `http.server` de la stdlib en vez de FastAPI por la misma
razón: FastAPI arrastra pydantic, cuyo núcleo es una extensión en Rust.
