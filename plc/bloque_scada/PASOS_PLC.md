# Trabajo en el PLC: celda FCA 02/03 (Q03UDE)

Guía para tener a mano frente al PLC. Son dos tareas independientes:

- **A. Cargar la sección de fallas** del bloque SCADA. No requiere reset de la CPU.
- **B. Poner el PLC en hora**: B1 a mano (*Set clock*) hoy; B2 (SNTP) cuando se decida, porque requiere reset.

El adquisidor, las tags y la web ya están listos.

**Si la web ya muestra fallas en "Últimas fallas", la sección A ya está cargada en el PLC.** En ese caso solo queda B, y de A conviene hacer la verificación A7.

---

## Qué llevar

De la carpeta `plc/bloque_scada/` del repo:

| Archivo | Para qué |
|---|---|
| `SCADA.csv` | Programa SCADA completo, con la sección 10 de fallas incluida |
| `SCADA_sin_pasos.csv` | Lo mismo sin números de paso, por si el anterior da error al importar |
| `COMMENT_con_SCADA.csv` | Todos los comentarios: los originales (`COMMENT_bk.csv`) más los del SCADA |
| `SCADA_lista.txt` | El listado legible, para consultar |
| `fallas.py` | Tabla de códigos de falla: qué bit es cada F001…F103 |
| `LEEME.md` | Mapa de memoria completo |

Y además:
- la PC con GX Works2 y el cable o la red al PLC;
- **una parada de producción acordada**: para A alcanza con unos minutos; para B2, un poco más por el reset.

---

## A. Cargar la sección de fallas

### A1. Backup (obligatorio)

1. *Online → Read from PLC*: todo (parámetros, programas, comentarios, device memory).
2. *Project → Save As* con fecha en el nombre, por ejemplo `FCA0203_2026-11-xx_antes_fallas`.

### A2. Comprobar que hay memoria

La sección agrega unos **1900 pasos**: el programa SCADA pasa de ~206 a ~2100 pasos.

- *Online → Read from PLC* y mirar el panel de capacidad, o *Tool → Check Program*, o la cuenta de pasos de cada programa en el árbol del proyecto.
- El Q03UDE tiene **30 k pasos**. Si quedan menos de 3000 libres, **no seguir** y avisar.

### A3. Comprobar que los registros están libres

*Find/Replace → Find Device* en **todo el proyecto**:

| Buscar | Debe aparecer |
|---|---|
| `D6300` … `D6659` | En ningún lado (todavía) |
| `D6800` … `D6859` | En ningún lado |

- Revisé los PDF del programa y el export de comentarios, y no aparecen.
- **Falta revisar la Proface** (GP-Pro EX): que ninguna pantalla lea ni escriba en esos D.
- Si algo está ocupado, **no seguir** y avisar: se mueve el rango en `fallas.py` y se regenera.

### A4. Importar el programa

1. En el árbol del proyecto, seleccionar el programa **SCADA**.
2. *Project → Read from CSV File* → `SCADA.csv`.
   - Reemplaza el contenido del programa SCADA entero. Los demás programas no se tocan.
   - Si da error de pasos, repetir con `SCADA_sin_pasos.csv`.
3. **Convertir** (`F4`). No tiene que dar errores.
4. Controlar a ojo que al final del programa aparezca la sección 10: bloques que empiezan con `LDP M1840`, `INC D6301`, `BMOV D6800 D6803 K57`, etc.

### A5. Importar los comentarios

1. *Project → Read from CSV File* → **Device Comment** → `COMMENT_con_SCADA.csv`.
2. Reemplaza **todos** los comentarios. Está bien, porque el archivo ya trae los 2884 originales más los del SCADA (3433 en total).
3. Controlar, por ejemplo, que `M1840` siga diciendo "Air Low" y que `D6301` diga "SCADA F001 veces M1840".

### A6. Escribir al PLC

1. *Online → Write to PLC*: marcar **solo el programa SCADA** y los **comentarios**. **No** los parámetros.
2. Con el PLC en RUN, GX Works2 pregunta si escribe en RUN. Se puede, pero mejor hacerlo con la celda parada.
3. **No hace falta reset** de la CPU: no se cambian parámetros y el programa SCADA ya está en la lista de ejecución.
4. Si estaba en STOP, pasar a RUN.

### A7. Verificar

Con *Online → Monitor → Device/Buffer Memory Batch*:

| Mirar | Qué tiene que pasar |
|---|---|
| `D6000` | Sigue subiendo 1 por segundo: el bloque SCADA corre |
| `D6301`…`D6403` | En 0, salvo fallas que hayan aparecido desde la carga |
| `D6800` | 0 hasta la primera falla |

**Prueba con una falla real**, en manual y sin riesgo. Por ejemplo, una que se resetee fácil: cortina, clamp o shift pin.

1. Provocar la falla y mirar su bit. Por ejemplo, `M3841` (JIG2 shift pin) = **F073**.
2. Tiene que subir `D6300 + código` (para F073, `D6373`).
3. En `D6800` tiene que aparecer el código, y en `D6801`/`D6802` la fecha MMDD y la hora HHMM del PLC.
4. Mientras la falla está activa, `D6420 + 2×código` suma 1 por segundo (para F073, `D6566`).
5. Resetear (`M1006`): el bit vuelve a 0 y los contadores quedan.
6. En la web, a los pocos segundos, la falla aparece en *Últimas fallas* y en *Más frecuentes*.

**Opcional: dejar los contadores en cero** después de las pruebas. Con el PLC en línea, *Debug → Modify Value*, o temporalmente en un programa de prueba:

```
FMOV K0 D6300 K360    ; veces y segundos de todas las fallas
FMOV K0 D6800 K60     ; registro de ultimas 20
```

### Si algo sale mal

Escribir el backup de A1 (solo el programa SCADA y los comentarios). El resto del programa nunca se tocó.

---

## B. Poner el PLC en hora

Hoy el reloj del PLC está **~3 h 30 min atrasado** respecto del servidor de base. Eso corre la tabla de producción por hora y la hora de las fallas.

**El programa productivo no usa el reloj:** no hay `DATERD`, `SD210`–`SD216` ni `SM213`. El salto de hora solo afecta al bloque SCADA.

### B0. Antes: ver si la Proface toca el reloj del PLC

En GP-Pro EX, en la configuración de la pantalla (*System Settings → Display Unit*, sección de reloj / *Time Update*), ver si la pantalla **escribe la hora al PLC**.

- Si la escribe, la pantalla le va a volver a poner la hora mal al PLC. Hay que dejarla en *tomar la hora del PLC* o corregir la hora de la pantalla.
- Es una causa probable del desfase actual.

### B1. Corrección a mano (sin reset, se puede hacer hoy)

1. Tomar la hora de una fuente confiable: el servidor de base o una PC ya corregida, **no** la de la Proface.
2. GX Works2 → *Online → Set Clock* → poner fecha y hora actuales → *Execute*.
3. Verificar en el monitor: `D6093`/`D6094` (hora y minuto del bloque SCADA) correctos.
4. En la web, *Enlace → Reloj del PLC* ya no tiene que mostrar diferencia en minutos.

Al corregir la hora, el bloque SCADA ve un "cambio de hora" y abre el renglón de la hora nueva. Ese día la tabla por hora va a mostrar un salto. Se normaliza solo en 24 h.

### B2. SNTP, para que no se vuelva a correr (requiere reset)

**Configuración actual** (según `hard.pdf`):

| Parámetro | Hoy | Cambiar a |
|---|---|---|
| Time settings (SNTP) | Not used | **Use** |
| SNTP server IP address | (vacío) | IP de la **MikroTik del lado del PLC** (red 192.168.0.x) |
| Time zone | GMT+09:00 (valor de fábrica japonés) | **GMT−03:00** |
| At turn ON/reset | Not execute | **Execute** |
| At error occurrence | Continue | Continue (dejarlo así: si no hay servidor NTP, el PLC sigue andando) |
| Execution interval | Execution time 12:00 | Cada 60 min, o una hora fija |

El *Default router IP* está vacío, así que el servidor NTP **tiene que estar en la misma red que el PLC**. Por eso se usa la MikroTik.

**Paso 1: MikroTik.** Se puede hacer con la celda andando.

```
/ip address print                          # anotar la IP del lado PLC (192.168.0.x)
/system ntp client set enabled=yes servers=IP_NTP_EMPRESA
/system ntp server set enabled=yes
/system ntp client print                   # tiene que quedar "synchronized"
```

- En RouterOS v6 hace falta el paquete `ntp`.
- Si el firewall filtra `input`, permitir UDP 123 desde 192.168.0.101.

**Paso 2: PLC.** En una parada.

1. Backup (como en A1).
2. *PLC Parameter → Built-in Ethernet Port Setting → Time Setting*: cargar la tabla de arriba. **Revisar dos veces la zona GMT−03:00.**
3. *Write to PLC*: **parámetros**.
4. **Reset de la CPU:** llave STOP → RESET → RUN, o *Online → Remote Operation → Reset*. Los parámetros de Ethernet solo se aplican con el reset.
5. Verificar con *Online → Set Clock* (solo mirar) que la hora sea la real.
6. Esperar el intervalo configurado y volver a verificar.

**Riesgos de B2:**

| Riesgo | Nivel | Mitigación |
|---|---|---|
| Reset de la CPU: salidas en OFF unos segundos y la celda se detiene | Medio | Hacerlo en una parada acordada |
| Salto de hora en el primer sincronismo | Bajo | Solo afecta a la tabla horaria y a las fechas de fallas de ese día. Se evita haciendo antes B1 |
| Zona horaria mal (queda en GMT+9) | Medio | Revisar el paso 2 antes de escribir |
| Servidor NTP caído o inalcanzable | Bajo | Con "Continue" el PLC sigue con su reloj y no entra en error |
| La Proface pisa la hora | Medio | Ver B0 |
| Volver atrás | Bajo | Time settings: Not used, escribir parámetros, reset |

---

## Después, en la web

- **Mantenimiento → Enlace → Reloj del PLC:** sin diferencia en minutos.
- **Fallas:** se llenan "Últimas fallas" y "Más frecuentes".
- **Producción:** la hora en curso (recuadro punteado) coincide con la hora real.

## Referencia rápida de códigos

Algunos códigos frecuentes. La lista completa está en `fallas.py` (`python fallas.py` la imprime).

| Código | Bit | Falla |
|---|---|---|
| F001 | M1840 | Celda: aire bajo |
| F004 | M1843 | Celda: parada de emergencia |
| F023 / F037 | M1866 / M1882 | RB1 / RB2: falta de gas |
| F024 / F038 | M1867 / M1883 | RB1 / RB2: falta de alambre |
| F025 / F039 | M1868 / M1884 | RB1 / RB2: alambre pegado |
| F049 | M2840 | JIG1: cilindro change |
| F072 | M3840 | JIG2: cilindro change |
| F073 | M3841 | JIG2: shift pin |

Contadores: veces en `D6300 + código`, segundos en `D6420 + 2×código`.
