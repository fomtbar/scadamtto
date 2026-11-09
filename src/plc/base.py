"""Interfaz comun de los drivers de PLC.

A diferencia de la abstraccion de visionMantev2 (que expone read_trigger_bit /
write_result, o sea el caso de uso de vision metido dentro del driver), esta
interfaz esta orientada a tags: el driver sabe leer un bloque y decodificar un
tag de ese bloque, y nada mas. El scheduling, la politica de registro y la
persistencia viven afuera.

El crudo que devuelve leer_grupo() es opaco a proposito: Mitsubishi entrega
palabras de 16 bits little-endian y Siemens bytes big-endian, asi que cada
driver se encarga de decodificar lo que el mismo leyo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.core.scangroups import GrupoLectura, ItemLectura


class ErrorPlc(Exception):
    """Falla de comunicacion con el PLC. Siempre invalida la conexion."""


class PlcDriver(ABC):
    marca: str = "?"

    def __init__(self, nombre: str, cfg: dict):
        self.nombre = nombre
        self.cfg = cfg
        self._conectado = False

    # --- ciclo de vida ---------------------------------------------------
    @abstractmethod
    def conectar(self) -> None:
        """Abre la conexion. Lanza ErrorPlc si no puede."""

    @abstractmethod
    def desconectar(self) -> None:
        """Cierra la conexion. Nunca lanza."""

    @property
    def conectado(self) -> bool:
        return self._conectado

    # --- lectura ---------------------------------------------------------
    @abstractmethod
    def leer_grupo(self, grupo: GrupoLectura) -> Any:
        """Lee un bloque contiguo. Lanza ErrorPlc si falla."""

    @abstractmethod
    def decodificar(self, grupo: GrupoLectura, crudo: Any, item: ItemLectura) -> float:
        """Extrae el valor de un tag del crudo devuelto por leer_grupo()."""

    # --- escritura (no se usa en esta etapa, el servicio es solo lectura) --
    def escribir_bit(self, direccion: str, valor: bool) -> None:
        raise NotImplementedError(f"{type(self).__name__} no implementa escribir_bit")

    def escribir_palabra(self, direccion: str, valor: int) -> None:
        raise NotImplementedError(f"{type(self).__name__} no implementa escribir_palabra")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.nombre} conectado={self._conectado}>"
