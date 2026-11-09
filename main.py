"""Adquisidor scadaMtto: lee tags de PLC y los registra en SQL Server.

Uso:
    scadamtto                   arranca el servicio (equivale a 'scadamtto servicio')
    scadamtto probe             diagnostica la conexion con el PLC
    scadamtto leer              lee los tags una vez y los imprime
    scadamtto testdb            verifica la conexion a SQL Server
    scadamtto --config RUTA     raiz alternativa (donde esta config/)

En desarrollo se invoca igual con 'python main.py <subcomando>'.

Los diagnosticos van como subcomandos del mismo binario en vez de ejecutables
aparte: en la PC de planta no hay Python instalado, y son justo las herramientas
que hacen falta cuando algo no anda.

El servicio se detiene con Ctrl+C o creando el archivo stop.flag en la raiz (eso
hace detener.cmd, que es la unica forma cuando corre oculto como SYSTEM). En los
dos casos el apagado cierra los sockets del PLC de forma limpia -- importante en
el Q, donde cada entrada MC Protocol del Open Setting acepta un solo cliente: si
queda colgada, el proximo arranque no puede entrar hasta que expire en el PLC.

Solo puede correr una instancia por maquina; una segunda sale con codigo 3.
"""
from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger

from src.core.config import ErrorConfig, raiz_por_defecto
from src.core.servicio import Servicio
from src.utils.logger import configurar
from src.utils.proceso import (
    InstanciaUnica,
    ParadaPorArchivo,
    YaCorriendo,
    esperar_si_interactivo,
)
from src.web.server import ServidorWeb

# Codigos de salida. El watchdog los anota en logs/watchdog.log.
SALIDA_OK = 0              # parada pedida (stop.flag o Ctrl+C)
SALIDA_FALLA = 1           # se murieron los hilos de scan
SALIDA_CONFIG = 2          # configuracion invalida: reintentar no lo arregla
SALIDA_YA_CORRIENDO = 3    # hay otra instancia en esta maquina


def correr_servicio() -> int:
    ap = argparse.ArgumentParser(prog="scadamtto", description="Adquisidor PLC -> SQL Server")
    ap.add_argument("--config", default=str(raiz_por_defecto()),
                    help="raiz del proyecto (donde esta config/)")
    args = ap.parse_args()
    raiz = Path(args.config)

    configurar(raiz / "logs")
    cerrojo = InstanciaUnica()
    try:
        cerrojo.adquirir()
    except YaCorriendo as e:
        logger.error(str(e))
        esperar_si_interactivo()
        return SALIDA_YA_CORRIENDO
    try:
        return _correr(raiz)
    finally:
        cerrojo.liberar()


def _correr(raiz: Path) -> int:
    parada = ParadaPorArchivo(raiz)
    if parada.existia_al_arrancar():
        logger.warning(
            f"Existe {parada.ruta}: el servicio esta detenido a proposito. Esta instancia "
            "corre igual, pero el watchdog no lo va a relanzar hasta usar iniciar.cmd."
        )

    try:
        servicio = Servicio(raiz)
    except ErrorConfig as e:
        logger.error(f"Configuracion invalida: {e}")
        esperar_si_interactivo()
        return SALIDA_CONFIG
    except ValueError as e:
        logger.error(f"No se pudieron armar los grupos de lectura: {e}")
        esperar_si_interactivo()
        return SALIDA_CONFIG

    configurar(raiz / "logs", servicio.cfg.app.nivel_log)
    logger.info(f"scadaMtto arrancando ({len(servicio.cfg.tags)} tags configurados)")

    fin = threading.Event()

    def apagar(signum, _frame):
        logger.info(f"senal {signum} recibida, apagando")
        fin.set()

    # Python solo deja instalar manejadores de senales desde el hilo principal.
    # Fuera de el (tests) la parada llega igual por stop.flag.
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, apagar)
        signal.signal(signal.SIGTERM, apagar)

    servicio.arrancar()

    web = None
    if servicio.cfg.app.web_habilitado:
        web = ServidorWeb(servicio.cfg.app.web_host, servicio.cfg.app.web_puerto, servicio)
        try:
            web.arrancar()
        except OSError as e:
            logger.error(
                f"No se pudo abrir el dashboard en el puerto "
                f"{servicio.cfg.app.web_puerto}: {e}"
            )
            web = None

    codigo = SALIDA_OK
    try:
        while not fin.wait(1.0):
            if parada.pedida():
                logger.info(f"{parada.ruta.name} detectado, apagando de forma ordenada")
                break
            if not servicio.vivo():
                logger.error("Todos los hilos de scan murieron, saliendo")
                # Distinto de 0 para que el watchdog lo registre como falla.
                codigo = SALIDA_FALLA
                break
    except KeyboardInterrupt:
        pass

    logger.info("deteniendo...")
    if web:
        web.parar()
    servicio.detener()
    logger.info("scadaMtto detenido")
    return codigo


def _sub_probe() -> int:
    from scripts.probe_plc import main as m
    return m()


def _sub_leer() -> int:
    from scripts.read_once import main as m
    return m()


def _sub_testdb() -> int:
    from scripts.test_db import main as m
    return m()


SUBCOMANDOS = {
    "servicio": correr_servicio,
    "probe": _sub_probe,
    "leer": _sub_leer,
    "testdb": _sub_testdb,
}


def main() -> int:
    argv = sys.argv[1:]
    if argv:
        if argv[0] in ("-h", "--help", "ayuda") and len(argv) == 1:
            print(__doc__)
            return 0
        if argv[0] in SUBCOMANDOS:
            sub = argv[0]
            # El subcomando se saca de argv para que el argparse de cada script
            # vea solo sus propias opciones.
            sys.argv = [f"scadamtto {sub}", *argv[1:]]
            return SUBCOMANDOS[sub]()
    return correr_servicio()


if __name__ == "__main__":
    raise SystemExit(main())
