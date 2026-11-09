# scadaMtto web: tablero de celdas

Web de **solo lectura** con el estado de las celdas de soldadura, para producción y para mantenimiento. Tiene una solapa por celda.

Lee `Mantenimiento.test.ValorActual`, la tabla que el adquisidor (`scadaMtto.exe`) mantiene con los datos del bloque `SCADA` del PLC. Ver `../plc/bloque_scada/LEEME.md`.

- **Stack:** Next.js 16 + React 19 + TypeScript + Tailwind 4 + `mssql`. Son los mismos patrones que examenesWeb.
- **Puerto:** 3108.
- **Sin login:** no escribe nada en la base.

## Desplegar en el servidor

Copiar la carpeta `web/` al servidor y, desde Git Bash:

```bash
./deploy.sh
```

La primera vez pide los datos de la base y genera `infraestructura/.env`. Después:

1. comprueba que la base sea alcanzable desde el host y desde un contenedor;
2. construye la imagen;
3. levanta el contenedor `scadamttoweb-web` con `restart: always`;
4. espera que esté sano;
5. prueba `/api/health` y `/api/celda/fca0203`.

Queda en `http://<ip-del-servidor>:3108`. Para cambiar la configuración: `./deploy.sh --setup`.

## Agregar una celda

1. En el adquisidor, generar sus tags con el prefijo de la celda:
   ```
   python plc/bloque_scada/generar_tags.py FCA0405
   ```
   y cargarlas en `tags.toml`.
2. Sumar una línea en `src/lib/celdas.ts`.
3. `./deploy.sh`.

## Qué muestra

- **Estado:**
  - la celda: produciendo, auto en espera, manual, falla o emergencia;
  - cada jig, con su tiempo entre piezas.
- **Producción de hoy:** piezas de JIG1 y JIG2, tiempo produciendo y en falla, y piezas por hora de las últimas 24 h. Sale de la tabla horaria que arma el PLC.
- **Mantenimiento:** emergencia, fallas, alarma, teach y servo de los robots, CC-Link y batería, y los contadores de puntas y toberas.
- **Avisos:**
  - **dato desactualizado:** el adquisidor no lee hace más de 60 s;
  - **PLC sin vida:** el contador `Vida` no cambia, así que el bloque SCADA no corre;
  - **reloj del PLC corrido:** más de 5 min de diferencia con el servidor.

### Diseño

Sigue el criterio de pantallas de planta ISA-101: la base es gris y **el color queda solo para lo anormal**. Hay tema claro y oscuro; arranca con el del sistema y se cambia con el botón.

## Desarrollo

```bash
npm install
DATOS_DEMO=si npm run dev      # datos de ejemplo, sin base (también: falla | viejo)
npm run test                   # reglas de src/lib/dominio.ts
npm run typecheck && npm run lint && npm run build
./dev.sh build                 # en Docker, con recarga automática
```
