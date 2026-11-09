"""Construccion de drivers por marca.

Los imports son lazy a proposito: si falta la DLL de snap7 en una maquina que
solo usa Mitsubishi, no tiene que romper el arranque.
"""
from __future__ import annotations

from src.plc.base import PlcDriver

MARCAS = ("mitsubishi", "siemens", "mock")


def crear_plc(nombre: str, cfg: dict) -> PlcDriver:
    marca = str(cfg.get("marca", "")).lower()
    if marca == "mitsubishi":
        from src.plc.mitsubishi import MitsubishiPlc
        return MitsubishiPlc(nombre, cfg)
    if marca == "siemens":
        from src.plc.siemens import SiemensPlc
        return SiemensPlc(nombre, cfg)
    if marca == "mock":
        from src.plc.mock import MockPlc
        return MockPlc(nombre, cfg)
    raise ValueError(
        f"PLC {nombre!r}: marca {marca!r} no soportada. Validas: {', '.join(MARCAS)}"
    )
