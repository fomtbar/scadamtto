"""Hilo de scan: un Poller por PLC.

El hilo es dueno exclusivo del socket del PLC. Ni pymcprotocol ni snap7 son
thread-safe, y ademas el Q tiene una sola conexion MC disponible, asi que toda
la E/S de un PLC tiene que pasar por aca.

El hilo no habla con SQL Server: deja las muestras en el buffer local y sigue
escaneando. Esa separacion es la que hace que una DB caida no desordene las
series temporales.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

from loguru import logger

from src.core.buffer import Buffer
from src.core.config import ConfigApp
from src.core.estado import Supervisor
from src.core.models import Muestra
from src.core.scangroups import GrupoLectura
from src.plc.base import ErrorPlc, PlcDriver


class _EstadoRegistro:
    """Lo que hay que recordar por tag para decidir si se graba una muestra."""

    __slots__ = ("ultimo_valor", "ultimo_registro_mono", "era_buena")

    def __init__(self):
        self.ultimo_valor: float | None = None
        self.ultimo_registro_mono: float | None = None
        self.era_buena: bool = True   # arranca en True: el primer fallo se graba


class Poller(threading.Thread):
    def __init__(self, driver: PlcDriver, grupos: list[GrupoLectura], app: ConfigApp,
                 buffer: Buffer, sup: Supervisor):
        super().__init__(name=f"poller-{driver.nombre}", daemon=True)
        self.driver = driver
        self.grupos = grupos
        self.app = app
        self.buffer = buffer
        self.sup = sup
        self._parar = threading.Event()
        self._espera_reconexion = app.reconexion_min_s
        # Vencimiento de cada grupo, en reloj monotonico.
        self._vence: list[float] = [0.0] * len(grupos)
        self._reg: dict[str, _EstadoRegistro] = {}
        for g in grupos:
            for item in g.items:
                self._reg[item.tag.nombre] = _EstadoRegistro()

    def parar(self) -> None:
        self._parar.set()

    # ------------------------------------------------------------------ run
    def run(self) -> None:
        logger.info(
            f"[{self.driver.nombre}] scan iniciado: {len(self.grupos)} grupos, "
            f"{sum(len(g.items) for g in self.grupos)} tags"
        )
        try:
            while not self._parar.is_set():
                if not self.driver.conectado:
                    if not self._reconectar():
                        continue
                self._ciclo()
        finally:
            self.driver.desconectar()
            self.buffer.cerrar_hilo()
            self.sup.plc_conectado(self.driver.nombre, False, "detenido")
            logger.info(f"[{self.driver.nombre}] scan detenido")

    def _reconectar(self) -> bool:
        try:
            self.driver.conectar()
        except ErrorPlc as e:
            self.sup.plc_conectado(self.driver.nombre, False, str(e))
            logger.warning(f"[{self.driver.nombre}] {e}")
            # Backoff exponencial: no tiene sentido martillar un PLC apagado
            # cada segundo, y ademas llena el log.
            self._parar.wait(self._espera_reconexion)
            self._espera_reconexion = min(self._espera_reconexion * 2, self.app.reconexion_max_s)
            return False
        self._espera_reconexion = self.app.reconexion_min_s
        self.sup.plc_conectado(self.driver.nombre, True)
        logger.info(f"[{self.driver.nombre}] conectado")
        # Al reconectar todos los grupos vencen ya, para tener datos frescos.
        self._vence = [0.0] * len(self.grupos)
        return True

    def _ciclo(self) -> None:
        ahora = time.monotonic()
        muestras: list[Muestra] = []
        proximo = ahora + 1.0

        for i, grupo in enumerate(self.grupos):
            if self._vence[i] > ahora:
                proximo = min(proximo, self._vence[i])
                continue
            periodo = grupo.clave.scan_ms / 1000.0
            # Se reprograma desde ahora y no desde el vencimiento anterior: si
            # una lectura tardo mas que el periodo, no se acumula deuda.
            self._vence[i] = ahora + periodo
            proximo = min(proximo, self._vence[i])

            momento = datetime.now()
            try:
                crudo = self.driver.leer_grupo(grupo)
            except ErrorPlc as e:
                self.sup.lectura(self.driver.nombre, False, str(e))
                logger.warning(f"[{self.driver.nombre}] {e}")
                muestras += self._marcar_malos(grupo, momento, str(e))
                self.driver.desconectar()
                self.sup.plc_conectado(self.driver.nombre, False, str(e))
                break
            self.sup.lectura(self.driver.nombre, True)
            muestras += self._procesar(grupo, crudo, momento, ahora)

        if muestras:
            self.buffer.guardar(muestras)

        dormir = max(0.0, proximo - time.monotonic())
        if dormir:
            self._parar.wait(dormir)

    # ---------------------------------------------------------- decisiones
    def _procesar(self, grupo: GrupoLectura, crudo, momento: datetime,
                  ahora: float) -> list[Muestra]:
        salida: list[Muestra] = []
        for item in grupo.items:
            tag = item.tag
            reg = self._reg[tag.nombre]
            try:
                bruto = self.driver.decodificar(grupo, crudo, item)
            except Exception as e:
                msg = f"{tag.nombre}: no se pudo decodificar -- {type(e).__name__}: {e}"
                logger.warning(f"[{self.driver.nombre}] {msg}")
                if reg.era_buena:
                    reg.era_buena = False
                    salida.append(Muestra(momento, tag.nombre, None, False))
                self.sup.tag(self.driver.nombre, tag.nombre, None, False, momento, True, msg)
                continue

            valor = bruto * tag.escala + tag.offset
            grabar = self._corresponde_grabar(tag, reg, valor, ahora)
            if grabar:
                salida.append(Muestra(momento, tag.nombre, valor, True))
                reg.ultimo_registro_mono = ahora
            reg.ultimo_valor = valor
            reg.era_buena = True
            self.sup.tag(self.driver.nombre, tag.nombre, valor, True, momento, grabar)
        return salida

    def _corresponde_grabar(self, tag, reg: _EstadoRegistro, valor: float, ahora: float) -> bool:
        if not reg.era_buena:
            return True          # vuelve la lectura buena: se deja constancia
        if tag.registro == "intervalo":
            return True
        if reg.ultimo_valor is None:
            return True          # primera lectura del tag
        if abs(valor - reg.ultimo_valor) > tag.banda_muerta:
            return True
        if tag.heartbeat_s > 0 and reg.ultimo_registro_mono is not None:
            if ahora - reg.ultimo_registro_mono >= tag.heartbeat_s:
                return True
        return False

    def _marcar_malos(self, grupo: GrupoLectura, momento: datetime, error: str) -> list[Muestra]:
        """Graba una fila con Valor NULL y Estado 0 por cada tag del grupo.

        Solo en la transicion de buena a mala. Si se grabara en cada scan, una
        caida de media hora meteria miles de filas identicas sin informacion
        nueva; lo que importa es cuando se corto y cuando volvio.
        """
        salida = []
        for item in grupo.items:
            reg = self._reg[item.tag.nombre]
            if reg.era_buena:
                reg.era_buena = False
                salida.append(Muestra(momento, item.tag.nombre, None, False))
            self.sup.tag(self.driver.nombre, item.tag.nombre, None, False, momento, False, error)
        return salida
