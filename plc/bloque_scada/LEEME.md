# Bloque SCADA para el PLC de la celda (Q03UDE)

Programa aparte que junta en un rango propio los datos de producción y mantenimiento. El adquisidor los lee y los lleva a `test.ValorActual`.

**No modifica la lógica existente:** solo lee sus contactos y escribe en dispositivos que el programa actual no usa.

| Archivo | Para qué |
|---|---|
| `SCADA_lista.txt` | El programa en modo Lista, para tipear en GX Developer |
| `tags_scada.toml` | Las 153 tags para agregar al final de `config/tags.toml`. Llevan el prefijo de la celda: `FCA0203.Celda.Estado` |
| `generar_tags.py` | Regenera `tags_scada.toml`; para otra celda: `python generar_tags.py FCA0405` |
| `consultas_web.sql` | Estado en vivo y tabla de 24 horas, solo lectura |

## Mapa de memoria

En las tablas, el nombre de tag va sin el prefijo de la celda; en la base es `FCA0203.<tag>`.

### Palabras en vivo y totales

`D6000`–`D6027`. Están dentro del latch `D0`–`D7000` del parámetro, así que no se borran con un corte de luz.

| Dirección | Tag | Significado |
|---|---|---|
| D6000 | Celda.Vida | +1 por segundo. Si no cambia, el PLC no está corriendo el programa |
| D6001 | Celda.Estado | 0 sin modo · 1 manual · 2 auto esperando · 3 produciendo · 4 falla · 5 emergencia |
| D6002 | JIG1.Estado | ídem celda, más 6 = dry run |
| D6003 | JIG2.Estado | ídem JIG1 |
| D6004 | Celda.TipoAuto | copia de `D44` |
| D6005 | JIG1.TiempoEntrePiezas_ds | décimas de segundo entre las dos últimas piezas |
| D6006 | JIG2.TiempoEntrePiezas_ds | ídem |
| D6007 | PLC.FechaMMDD | fecha del reloj del PLC (1031 = 31/10) |
| D6008 | PLC.HoraHHMM | hora del reloj del PLC (1415 = 14:15) |
| D6010/11 | JIG1.PiezasTotal | 32 bits, nadie lo resetea |
| D6012/13 | JIG2.PiezasTotal | |
| D6014/15 | Celda.SegProduciendoTotal | segundos con algún jig en auto running |
| D6016/17 | Celda.SegFallaTotal | segundos con `M1980` o `M1843` activos |
| D6018/19 | Celda.FallasTotal | flancos de `M1980` |
| D6020/23 | RB1/RB2.CambiosPuntaTotal | flancos de `B0C3` / `B1C3` |
| D6024/27 | RB1/RB2.LimpiezasToberaTotal | flancos de `B0C1` / `B1C1` |

**Uso interno, no se leen:** `D6040`–`D6041` (cronómetros), `D6090`–`D6099` (reloj y auxiliares), `M6000`–`M6005`, `Z10`.

### Bits de mantenimiento

`M6010`–`M6024`, copias en vivo.

| Bit | Tag | Origen |
|---|---|---|
| M6010 | Celda.Emergencia | M1843 |
| M6011 | Celda.FallaGeneral | M1980 |
| M6012 / M6013 | JIG1 / JIG2.Falla | M1974 / M1975 |
| M6014 / M6015 | RB1 / RB2.Falla | M1977 / M1978 |
| M6016 / M6017 | RB1 / RB2.Alarma | B83 / B183 |
| M6018 / M6019 | RB1 / RB2.ModoTeach | B87 / B187 |
| M6020 / M6021 | RB1 / RB2.ServoOn | B81 / B181 |
| M6022 | PLC.FallaCCLink | M3979 |
| M6023 | PLC.BateriaBaja | M3978 (SM52) |
| M6024 | Celda.Auto | M1000 |

### Tabla de 24 horas

`D6100`–`D6219`. Cada hora `h` (0–23) ocupa 5 palabras desde `D6100 + h*5`:

| +0 | +1 | +2 | +3 | +4 |
|---|---|---|---|---|
| fecha MMDD | piezas JIG1 | piezas JIG2 | seg produciendo | seg en falla |

Al empezar cada hora, el PLC limpia ese renglón y le pone la fecha. El renglón de la hora en curso se va llenando en vivo.

Los renglones que quedaron de días anteriores (por ejemplo, si el PLC estuvo apagado) se reconocen por la fecha. La consulta `consultas_web.sql` los descarta.

## Cómo cargarlo (en una parada de producción)

1. **Backup:** leer el proyecto del PLC y guardarlo con otro nombre antes de tocar nada.
2. **Confirmar que el rango está libre.** Revisé los PDF y no aparecen `D6000`–`D6219`, `M6000`–`M6024` ni `Z0`–`Z15`. El programa solo usa `Z16` y `Z18`. Igual hay que confirmarlo:
   - GX Developer → *Find/Replace → Device* (o *Cross reference list*) con `D6000` a `D6219`, `M6000` a `M6024` y `Z10`;
   - el proyecto de la **Proface**: el HMI puede escribir en D/M que no aparecen en la escalera.

   Si algo está ocupado, avisar y se mueve el rango.
3. *Project → Edit data → New*: tipo Program, nombre `SCADA`.
4. Modo Lista (`Alt+F1`): tipear las instrucciones de `SCADA_lista.txt`, sin las líneas `;`. Convertir (`F4`).
5. *PLC Parameter → Program*: agregar `SCADA` al final de la lista, con tipo **Scan**.
6. *Online → Write to PLC*: parámetros + programa `SCADA`. Como cambian los parámetros, hacer **reset del CPU** (STOP → RESET → RUN).
7. **Poner en hora el reloj del PLC:** *Online → Set clock*. El SNTP del PLC está en "Not used". Si el reloj está corrido, la tabla horaria queda corrida.

## Verificar en línea (monitor de GX Developer)

- `D6000` sube 1 por segundo.
- Con la celda en auto, `D6001` = 2, y al soldar = 3.
- Al terminar una pieza de JIG1, `D6010` y `D6100 + hora*5 + 1` suben 1.

  **Esto es lo más importante a confirmar:** que `M2230` da un pulso por pieza buena. Lo deduje de los comentarios del programa ("JIG1 Cycle_End"), igual que la lógica del contador de dry run que ya existe.

## Del lado del adquisidor

1. `detener.cmd` en arg-scada01.
2. Agregar el contenido de `tags_scada.toml` al final de `C:\scadaMtto\config\tags.toml`.
3. `iniciar.cmd`.

Son 6 lecturas en bloque por segundo y una cada 5 s para la tabla horaria: carga despreciable para el PLC.

Si se cargan las tags antes que el bloque, leen 0 y no pasa nada.
