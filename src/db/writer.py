"""Hilo que drena el buffer local hacia SQL Server.

Es el unico que habla con la DB. Toma un lote, lo inserta en una transaccion y
recien cuando el commit volvio bien borra esas filas del buffer. Si algo falla,
las filas siguen en el buffer y se reintentan: no se pierde nada y tampoco se
duplica, porque el borrado va despues del commit.
"""
from __future__ import annotations

import threading

from loguru import logger

from src.core.buffer import Buffer
from src.core.config import ConfigApp
from src.core.estado import Supervisor
from src.core.models import Muestra
from src.db.sqlserver import ErrorDb, SqlServerSink


def _ultima_por_tag(muestras: list[Muestra]) -> list[Muestra]:
    """Deja una sola muestra por tag: la mas reciente.

    En modo 'actual' la tabla tiene una fila por variable, asi que reproducir
    contra ella todas las muestras acumuladas no aporta nada: al terminar queda
    el ultimo valor igual. Tras una caida de red de una hora eso serian miles de
    UPDATE sobre las mismas dos filas.

    El buffer entrega en orden de id, o sea cronologico, asi que quedarse con la
    ultima aparicion de cada nombre alcanza.
    """
    por_tag: dict[str, Muestra] = {}
    for m in muestras:
        por_tag[m.nombre_tag] = m
    return list(por_tag.values())


class DbWriter(threading.Thread):
    def __init__(self, sink: SqlServerSink, buffer: Buffer, app: ConfigApp, sup: Supervisor):
        super().__init__(name="db-writer", daemon=True)
        self.sink = sink
        self.buffer = buffer
        self.app = app
        self.sup = sup
        self._parar = threading.Event()
        self._espera = app.reconexion_min_s

    def parar(self) -> None:
        self._parar.set()

    def run(self) -> None:
        logger.info("writer iniciado")
        try:
            while not self._parar.is_set():
                if not self.sink.conectado and not self._reconectar():
                    continue
                if not self._drenar_un_lote():
                    # Buffer vacio: no hay nada que hacer hasta el proximo scan.
                    self._parar.wait(0.5)
        finally:
            self._vaciar_al_salir()
            self.buffer.cerrar_hilo()
            self.sink.desconectar()
            self.sup.db(False)
            logger.info("writer detenido")

    def _reconectar(self) -> bool:
        try:
            self.sink.conectar()
        except ErrorDb as e:
            self.sup.db(False, str(e))
            logger.warning(str(e))
            self._parar.wait(self._espera)
            self._espera = min(self._espera * 2, self.app.reconexion_max_s)
            return False
        self._espera = self.app.reconexion_min_s
        self.sup.db(True)
        return True

    def _drenar_un_lote(self) -> bool:
        """Envia un lote. Devuelve False si no habia nada pendiente."""
        podadas = self.buffer.podar()
        if podadas:
            logger.error(
                f"Buffer lleno: se descartaron {podadas} muestras viejas. "
                "La DB lleva demasiado tiempo inaccesible."
            )
        lote = self.buffer.tomar(self.app.lote_db)
        self.sup.pendientes(self.buffer.pendientes())
        if not lote:
            return False
        ids = [i for i, _ in lote]
        muestras = [m for _, m in lote]
        if self.sink.modo == "actual":
            muestras = _ultima_por_tag(muestras)
        try:
            n = self.sink.escribir(muestras)
        except ErrorDb as e:
            self.sup.db(False, str(e))
            logger.warning(str(e))
            return True   # hay pendientes; reintenta tras reconectar
        self.buffer.confirmar(ids)
        self.sup.db(True, filas=n)
        self.sup.pendientes(self.buffer.pendientes())
        logger.debug(f"{n} filas enviadas a SQL Server")
        return True

    def _vaciar_al_salir(self) -> None:
        """Intenta un ultimo drenaje al apagar, para no dejar cola innecesaria."""
        if not self.sink.conectado:
            return
        try:
            for _ in range(20):    # tope, para no colgar el apagado
                if not self._drenar_un_lote():
                    break
        except Exception as e:
            logger.warning(f"No se pudo vaciar el buffer al salir: {e}")
