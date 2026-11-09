"""Driver Siemens S7 (S7-1200 / S7-1500 / S7-300 / S7-400) via snap7.

Queda implementado y probado contra el simulador pero deshabilitado por config
(habilitado = false en site.toml): se enciende cuando aparezca el PLC Siemens.

Respecto del driver de visionMantev2, que solo sabe leer bits de DB con
db_read(), aca se usa read_area() y estan soportadas las areas DB / M / I / Q y
los anchos byte, word y dword. S7 es big-endian, a diferencia de Mitsubishi.
"""
from __future__ import annotations

import struct

from src.core.addressing import parsear_siemens
from src.core.scangroups import GrupoLectura, ItemLectura
from src.plc.base import ErrorPlc, PlcDriver

# Mensaje que se repite en cada fallo de conexion. La lista de causas viene de
# visionMantev2/src/plc/siemens.py, donde esta bien peleada contra el hierro.
_AYUDA = (
    "Verifica: 1) que la PC este en la misma subred que el PLC y el ping ande; "
    "2) que en TIA Portal el CPU tenga habilitado 'Permitir acceso via "
    "comunicacion PUT/GET del interlocutor remoto' (Propiedades del CPU -> "
    "Proteccion y seguridad -> Mecanismos de conexion); "
    "3) que el DB a leer tenga 'Acceso optimizado al bloque' DESACTIVADO; "
    "4) que para S7-1200/1500 sea rack=0 slot=1 (probar slot=0 si no conecta)."
)


def _area_snap7(codigo: str):
    import snap7
    return {
        "DB": snap7.type.Area.DB,
        "MK": snap7.type.Area.MK,
        "PE": snap7.type.Area.PE,
        "PA": snap7.type.Area.PA,
    }[codigo]


class SiemensPlc(PlcDriver):
    marca = "siemens"

    def __init__(self, nombre: str, cfg: dict):
        super().__init__(nombre, cfg)
        self._cli = None

    # --- ciclo de vida ---------------------------------------------------
    def conectar(self) -> None:
        ip = self.cfg["ip"]
        rack = int(self.cfg.get("rack", 0))
        slot = int(self.cfg.get("slot", 1))
        self.desconectar()
        try:
            import snap7
            cli = snap7.client.Client()
            cli.connect(ip, rack, slot)
            if not cli.get_connected():
                raise ErrorPlc("snap7 conecto pero get_connected() da False")
            self._cli = cli
            self._conectado = True
        except Exception as e:
            self._cli = None
            self._conectado = False
            raise ErrorPlc(
                f"No se pudo conectar a {ip} (rack={rack}, slot={slot}) -- "
                f"{type(e).__name__}: {e}. {_AYUDA}"
            ) from e

    def desconectar(self) -> None:
        if self._cli is not None:
            try:
                self._cli.disconnect()
            except Exception:
                pass
            self._cli = None
        self._conectado = False

    @property
    def conectado(self) -> bool:
        # snap7 sabe de verdad si el socket sigue vivo; se le pregunta a el en
        # lugar de confiar en un flag cacheado.
        if self._cli is not None:
            try:
                self._conectado = self._cli.get_connected()
            except Exception:
                self._conectado = False
        return self._conectado

    # --- lectura ---------------------------------------------------------
    def leer_grupo(self, grupo: GrupoLectura) -> bytes:
        if self._cli is None:
            raise ErrorPlc(f"PLC {self.nombre} no conectado")
        try:
            datos = self._cli.read_area(
                _area_snap7(grupo.clave.area), grupo.clave.db, grupo.inicio, grupo.longitud
            )
        except Exception as e:
            raise ErrorPlc(
                f"Error leyendo {grupo.clave.area}{grupo.clave.db} "
                f"byte {grupo.inicio} x{grupo.longitud}: {type(e).__name__}: {e}"
            ) from e
        if len(datos) < grupo.longitud:
            raise ErrorPlc(
                f"Respuesta corta: se esperaban {grupo.longitud} bytes y "
                f"llegaron {len(datos)}"
            )
        return bytes(datos)

    def decodificar(self, grupo: GrupoLectura, crudo: bytes, item: ItemLectura) -> float:
        off = grupo.offset_de(item)
        tipo = item.tag.tipo
        if tipo == "bit":
            return float((crudo[off] >> (item.bit or 0)) & 1)
        fmt = {"int16": ">h", "uint16": ">H", "int32": ">i",
               "uint32": ">I", "float32": ">f"}.get(tipo)
        if fmt is None:
            raise ValueError(f"Tipo no soportado: {tipo!r}")
        return float(struct.unpack_from(fmt, crudo, off)[0])

    # --- escritura -------------------------------------------------------
    def escribir_bit(self, direccion: str, valor: bool) -> None:
        if self._cli is None:
            raise ErrorPlc(f"PLC {self.nombre} no conectado")
        d = parsear_siemens(direccion)
        if not d.es_bit:
            raise ValueError(f"{direccion} no es una direccion de bit")
        try:
            # Lectura-modificacion-escritura de un byte. Es intrinsecamente
            # sujeto a carrera si el PLC toca otro bit del mismo byte entre las
            # dos operaciones; por eso conviene reservar bytes enteros por
            # sentido de escritura.
            area = _area_snap7(d.area)
            datos = bytearray(self._cli.read_area(area, d.db, d.byte, 1))
            if valor:
                datos[0] |= 1 << d.bit
            else:
                datos[0] &= ~(1 << d.bit) & 0xFF
            self._cli.write_area(area, d.db, d.byte, datos)
        except Exception as e:
            self._conectado = False
            raise ErrorPlc(f"Error escribiendo {direccion}: {type(e).__name__}: {e}") from e

    def escribir_palabra(self, direccion: str, valor: int) -> None:
        if self._cli is None:
            raise ErrorPlc(f"PLC {self.nombre} no conectado")
        d = parsear_siemens(direccion)
        if d.es_bit:
            raise ValueError(f"{direccion} es una direccion de bit")
        fmt = {2: ">h", 4: ">i"}[d.ancho]
        try:
            self._cli.write_area(
                _area_snap7(d.area), d.db, d.byte, bytearray(struct.pack(fmt, int(valor)))
            )
        except Exception as e:
            self._conectado = False
            raise ErrorPlc(f"Error escribiendo {direccion}: {type(e).__name__}: {e}") from e
