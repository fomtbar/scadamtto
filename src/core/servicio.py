"""Ciclo de vida del adquisidor y recarga en caliente de la lista de tags.

Existe para que el dashboard pueda agregar o modificar variables sin reiniciar
el proceso. Al recargar se detienen los hilos de scan, se recalculan los grupos
de lectura y se vuelven a levantar; el writer y el buffer no se tocan, asi que
lo que estaba pendiente de enviar a SQL Server sigue su curso.

Todo lo que toca el estado compartido pasa por un lock: recargar_tags() llega
desde el hilo del servidor web, no desde el hilo principal.
"""
from __future__ import annotations

import threading
from pathlib import Path

from loguru import logger

from src.core import tagstore
from src.core.buffer import Buffer
from src.core.config import Config, ErrorConfig, cargar
from src.core.estado import Supervisor
from src.core.models import TagDef
from src.core.poller import Poller
from src.core.scangroups import agrupar, construir_items
from src.db.sqlserver import SqlServerSink
from src.db.writer import DbWriter


class Servicio:
    def __init__(self, raiz: str | Path = "."):
        self.raiz = Path(raiz)
        self.cfg: Config = cargar(self.raiz)
        self.sup = Supervisor()
        self.buffer = Buffer(self.raiz / self.cfg.app.buffer_ruta, self.cfg.app.buffer_max_filas)
        self.sink = SqlServerSink(self.cfg.db)
        self.writer = DbWriter(self.sink, self.buffer, self.cfg.app, self.sup)
        self.pollers: list[Poller] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------ ciclo de vida
    def arrancar(self) -> None:
        pendientes = self.buffer.pendientes()
        if pendientes:
            logger.info(f"El buffer trae {pendientes} muestras del arranque anterior")
        self.sup.pendientes(pendientes)
        logger.info(
            f"modo de escritura: {self.sink.modo} -> {self.sink.destino}"
            + ("  (una fila por tag, se actualiza en el lugar)"
               if self.sink.modo == "actual" else "  (una fila por muestra)")
        )
        with self._lock:
            self._construir_pollers()
            for p in self.pollers:
                p.start()
        self.writer.start()

    def detener(self) -> None:
        with self._lock:
            self._detener_pollers()
        self.writer.parar()
        self.writer.join(timeout=15)
        restantes = self.buffer.pendientes()
        if restantes:
            logger.warning(
                f"Quedan {restantes} muestras en el buffer; se envian al proximo arranque"
            )
        self.buffer.cerrar()

    def vivo(self) -> bool:
        with self._lock:
            return any(p.is_alive() for p in self.pollers)

    # ------------------------------------------------------------------- tags
    def tags(self) -> list[dict]:
        return tagstore.leer(self.raiz)

    def plcs_disponibles(self) -> list[dict]:
        return [
            {"nombre": n, "marca": c["marca"], "habilitado": bool(c.get("habilitado", True))}
            for n, c in self.cfg.plcs.items()
        ]

    def guardar_tags(self, tags: list[dict]) -> list[dict]:
        """Valida, persiste y aplica una nueva lista de tags.

        Si algo no valida no se escribe nada: el archivo en disco y los hilos de
        scan quedan exactamente como estaban.
        """
        validados = tagstore.validar(tags, set(self.cfg.plcs))
        marcas = self.cfg.marca_por_plc
        for t in validados:
            tagstore.validar_direccion(marcas[t["plc"]], t["direccion"], t["tipo"])

        with self._lock:
            # Se prueba a armar los grupos ANTES de escribir el archivo: asi un
            # tag que rompe la agrupacion (por ejemplo mas grande que el tope de
            # una lectura) se rechaza sin dejar el disco en un estado invalido.
            nuevos = [TagDef(**t) for t in validados]
            self._agrupar_todo(nuevos)

            tagstore.escribir(self.raiz, validados)
            self.cfg.tags = nuevos
            self._detener_pollers()
            self._construir_pollers()
            for p in self.pollers:
                p.start()
        logger.info(f"tags recargados: {len(validados)} variables")
        return validados

    # --------------------------------------------------------------- internos
    def _agrupar_todo(self, tags: list[TagDef]) -> dict[str, list]:
        """Calcula los grupos de lectura por PLC. Lanza ValueError si no cierra."""
        habilitados = self.cfg.plcs_habilitados
        items = construir_items([t for t in tags if t.plc in habilitados], self.cfg.marca_por_plc)
        por_plc: dict[str, list] = {}
        for nombre in habilitados:
            propios = [i for i in items if i.clave.plc == nombre]
            if not propios:
                continue
            # Bits y palabras tienen topes distintos, se agrupan por separado.
            bits = [i for i in propios if i.clave.es_bit]
            palabras = [i for i in propios if not i.clave.es_bit]
            por_plc[nombre] = (
                agrupar(palabras, self.cfg.app.max_palabras_por_lectura, self.cfg.app.max_hueco)
                + agrupar(bits, self.cfg.app.max_bits_por_lectura, self.cfg.app.max_hueco)
            )
        return por_plc

    def _construir_pollers(self) -> None:
        from src.plc.factory import crear_plc

        self.pollers = []
        for nombre, grupos in self._agrupar_todo(self.cfg.tags).items():
            cfg_plc = self.cfg.plcs[nombre]
            driver = crear_plc(nombre, cfg_plc)
            self.sup.registrar_plc(nombre, driver.marca, cfg_plc.get("ip", "-"),
                                   int(cfg_plc.get("puerto", 0)))
            self.sup.sincronizar_tags(
                nombre, {i.tag.nombre for g in grupos for i in g.items}
            )
            for g in grupos:
                logger.info(
                    f"[{nombre}] grupo {g.clave.area}{g.inicio} x{g.longitud} "
                    f"cada {g.clave.scan_ms} ms -> {', '.join(i.tag.nombre for i in g.items)}"
                )
            self.pollers.append(Poller(driver, grupos, self.cfg.app, self.buffer, self.sup))

        sobrantes = set(self.sup.plcs) - {p.driver.nombre for p in self.pollers}
        for nombre in sobrantes:
            self.sup.sincronizar_tags(nombre, set())

    def _detener_pollers(self) -> None:
        for p in self.pollers:
            p.parar()
        for p in self.pollers:
            p.join(timeout=10)
            if p.is_alive():
                logger.warning(f"{p.name} no termino a tiempo")
        self.pollers = []
