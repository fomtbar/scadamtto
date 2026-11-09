"""Control del proceso: instancia unica, parada por archivo y pausa ante error.

Instancia unica
    El Q acepta un solo cliente por entrada MC Protocol del Open Setting. Si dos
    adquisidores corren a la vez (el de la tarea programada y uno lanzado a mano
    con correr.cmd) se pelean esa conexion y ninguno lee bien.

    Se usa como cerrojo un puerto TCP en 127.0.0.1 abierto con
    SO_EXCLUSIVEADDRUSE, y no un mutex 'Global\\...': crear objetos en el espacio
    Global exige SeCreateGlobalPrivilege, que un usuario sin privilegios no tiene,
    y eso daria un falso "ya esta corriendo". El puerto, en cambio, funciona entre
    sesiones y usuarios sin privilegios, y el sistema operativo lo libera aunque
    el proceso muera de un taskkill /F.

Parada por archivo
    Corriendo como SYSTEM sin ventana no hay Ctrl+C, y matar el proceso deja
    colgada la conexion MC en el PLC. Para pedir una parada limpia se crea
    <raiz>/stop.flag; el bucle principal lo ve y hace el apagado ordenado.

    Solo cuenta un stop.flag creado DESPUES de arrancar. Si ya existia (el
    servicio fue detenido a proposito y alguien corre el exe a mano para mirar),
    no lo frena: el archivo sigue cumpliendo su otra funcion, que es que el
    watchdog no vuelva a levantar el servicio.
"""
from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

PUERTO_CERROJO = 47821
ARCHIVO_STOP = "stop.flag"
ENV_WATCHDOG = "SCADAMTTO_WATCHDOG"


class YaCorriendo(Exception):
    """Hay otra instancia del adquisidor en esta maquina."""


class InstanciaUnica:
    def __init__(self, puerto: int = PUERTO_CERROJO):
        self.puerto = puerto
        self._sock: socket.socket | None = None

    def adquirir(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Sin esto, en Windows otro proceso podria hacer bind al mismo puerto con
        # SO_REUSEADDR y el cerrojo no protegeria nada.
        exclusivo = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusivo is not None:
            s.setsockopt(socket.SOL_SOCKET, exclusivo, 1)
        try:
            s.bind(("127.0.0.1", self.puerto))
            s.listen(1)
        except OSError:
            s.close()
            raise YaCorriendo(
                f"Ya hay un adquisidor corriendo en esta maquina (cerrojo en el puerto "
                f"{self.puerto}). Si es el servicio, detenelo con detener.cmd antes de "
                "correrlo a mano."
            ) from None
        self._sock = s

    def liberar(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> "InstanciaUnica":
        self.adquirir()
        return self

    def __exit__(self, *_exc) -> None:
        self.liberar()


class ParadaPorArchivo:
    """Detecta un stop.flag creado despues del arranque."""

    def __init__(self, raiz: str | Path):
        self.ruta = Path(raiz) / ARCHIVO_STOP
        # Margen de un segundo por la resolucion de mtime en algunos sistemas de
        # archivos: un flag creado justo al arrancar tiene que contar.
        self._inicio = time.time() - 1.0

    def pedida(self) -> bool:
        try:
            return self.ruta.stat().st_mtime >= self._inicio
        except FileNotFoundError:
            return False

    def existia_al_arrancar(self) -> bool:
        try:
            return self.ruta.stat().st_mtime < self._inicio
        except FileNotFoundError:
            return False


def bajo_watchdog() -> bool:
    return bool(os.environ.get(ENV_WATCHDOG))


def esperar_si_interactivo(mensaje: str = "Presione Enter para cerrar...") -> None:
    """Frena antes de salir si el exe se abrio a mano con doble clic.

    Sin esto, un error de configuracion cierra la ventana de golpe y nadie llega
    a leer por que. Solo aplica al ejecutable congelado, con consola real y fuera
    del watchdog: corriendo como servicio no hay nadie mirando y frenar colgaria
    el proceso para siempre.
    """
    if not getattr(sys, "frozen", False) or bajo_watchdog():
        return
    try:
        if sys.stdin is None or not sys.stdin.isatty():
            return
        input(f"\n{mensaje}")
    except (EOFError, OSError, KeyboardInterrupt):
        pass
