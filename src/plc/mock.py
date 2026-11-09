"""PLC simulado.

Sirve para dos cosas:

- Probar toda la cadena (scan -> buffer -> SQL Server -> dashboard) sin PLC,
  que es la unica forma de avanzar desde una PC que no esta en la red de planta.
- Reproducir fallas a pedido (timeouts, desconexiones) para verificar que el
  store-and-forward y la reconexion hacen lo que dicen.

La memoria simulada usa la misma convencion que Mitsubishi: palabras de 16 bits
con signo indexadas por numero de dispositivo.
"""
from __future__ import annotations

import math
import random
import time

from src.core.scangroups import GrupoLectura, ItemLectura
from src.plc.base import ErrorPlc, PlcDriver
from src.plc.mitsubishi import decodificar_palabras


class MockPlc(PlcDriver):
    marca = "mock"

    def __init__(self, nombre: str, cfg: dict):
        super().__init__(nombre, cfg)
        self._t0 = time.monotonic()
        # Probabilidad de que una lectura falle, para ejercitar la reconexion.
        self._prob_falla = float(cfg.get("mock_prob_falla", 0.0))
        self._escrituras: dict[str, float] = {}

    def conectar(self) -> None:
        if random.random() < self._prob_falla:
            raise ErrorPlc(f"[mock] {self.nombre}: falla de conexion simulada")
        self._conectado = True

    def desconectar(self) -> None:
        self._conectado = False

    def _valor_palabra(self, familia: str, numero: int) -> int:
        """Genera un valor determinista pero variable en el tiempo."""
        t = time.monotonic() - self._t0
        if familia == "D":
            # Onda senoidal con una fase distinta por registro, para que se vea
            # movimiento y que cada tag tenga su propia serie.
            v = 1000 + 500 * math.sin(t / 10.0 + numero * 0.37)
            return int(v) % 32768
        return (numero + int(t)) % 32768

    def _valor_bit(self, familia: str, numero: int) -> int:
        t = time.monotonic() - self._t0
        # Cada bit alterna con un periodo propio (M1000 cada ~5 s, M1001 ~5.1 s...).
        periodo = 5.0 + (numero % 7) * 0.1
        return int((t % (periodo * 2)) < periodo)

    def leer_grupo(self, grupo: GrupoLectura) -> list[int]:
        if not self._conectado:
            raise ErrorPlc(f"[mock] {self.nombre} no conectado")
        if random.random() < self._prob_falla:
            self._conectado = False
            raise ErrorPlc(f"[mock] {self.nombre}: timeout de lectura simulado")
        familia = grupo.clave.area
        if grupo.clave.es_bit:
            return [self._valor_bit(familia, grupo.inicio + i) for i in range(grupo.longitud)]
        return [self._valor_palabra(familia, grupo.inicio + i) for i in range(grupo.longitud)]

    def decodificar(self, grupo: GrupoLectura, crudo: list[int], item: ItemLectura) -> float:
        return decodificar_palabras(crudo, grupo.offset_de(item), item.tag.tipo)

    def escribir_bit(self, direccion: str, valor: bool) -> None:
        self._escrituras[direccion.upper()] = float(valor)

    def escribir_palabra(self, direccion: str, valor: int) -> None:
        self._escrituras[direccion.upper()] = float(valor)
