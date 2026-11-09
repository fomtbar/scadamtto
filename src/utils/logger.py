"""Configuracion de logging con loguru."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger

_configurado = False

# Librerias que usan el logging de la stdlib y son mas ruidosas que utiles.
# pytds loguea un WARNING por cada reintento interno de conexion ("Work attempt
# exceeded it's allocated time"); la falla ya la reportamos nosotros con un
# mensaje que dice servidor, base y usuario, asi que sus reintentos solo tapan
# el log durante una caida de red.
_RUIDOSAS = {"pytds": logging.ERROR}


class _ADLoguru(logging.Handler):
    """Redirige el logging de la stdlib hacia loguru.

    Sin esto, lo que logueen las dependencias se escribe directo a stderr y
    nunca llega al archivo rotativo: justo lo que haria falta al diagnosticar
    una falla de la madrugada anterior.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            nivel = logger.level(record.levelname).name
        except ValueError:
            nivel = record.levelno
        marco, profundidad = logging.currentframe(), 2
        while marco and marco.f_code.co_filename == logging.__file__:
            marco = marco.f_back
            profundidad += 1
        logger.opt(depth=profundidad, exception=record.exc_info).log(
            nivel, record.getMessage()
        )


def configurar(directorio: str | Path = "logs", nivel_consola: str = "INFO") -> None:
    """Consola + archivo rotativo.

    sys.stderr puede ser None si en algun momento se empaqueta con PyInstaller
    en modo --noconsole, asi que el sink de consola se agrega solo si existe.
    """
    global _configurado
    if _configurado:
        return
    logger.remove()
    if sys.stderr is not None:
        logger.add(
            sys.stderr, level=nivel_consola,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | "
                   "<cyan>{name}</cyan> - <level>{message}</level>",
        )
    d = Path(directorio)
    d.mkdir(parents=True, exist_ok=True)
    logger.add(
        d / "scadamtto.log", level="DEBUG", rotation="5 MB", retention="30 days",
        encoding="utf-8", enqueue=True,   # enqueue: seguro entre hilos
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{line} - {message}",
    )
    logging.basicConfig(handlers=[_ADLoguru()], level=logging.INFO, force=True)
    for nombre, nivel in _RUIDOSAS.items():
        logging.getLogger(nombre).setLevel(nivel)
    _configurado = True
