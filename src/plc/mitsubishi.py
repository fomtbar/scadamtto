"""Driver Mitsubishi MC Protocol 3E sobre TCP.

Envuelve pymcprotocol 0.3.0 y corrige dos problemas de esa libreria que para un
proceso 24/7 no son aceptables:

1. Modo ASCII. Hay que inicializarlo con setaccessopt(commtype="ascii"), que es
   lo unico que ajusta _wordsize a 4. Asignar .commtype = "ascii" a mano (como
   hace visionMantev2/src/plc/mitsubishi.py:21) deja _wordsize en 2 y todas las
   lecturas de palabra se decodifican con el largo equivocado.

2. Rearmado del frame. pymcprotocol._recv() es un unico sock.recv(4096) sin
   bucle, y batchread_wordunits rebana ese buffer a ciegas. Si TCP fragmenta la
   respuesta -- cosa que pasa con bloques grandes, y mas en ASCII que ocupa 4
   caracteres por palabra -- devuelve valores incorrectos sin fallar. Aca se
   sobreescribe _recv() para leer el header, sacar el campo de longitud y leer
   exactamente esa cantidad de bytes.
"""
from __future__ import annotations

import socket
import struct

import pymcprotocol
from pymcprotocol import mcprotocolconst as const

from src.core.addressing import FAMILIAS_MITSUBISHI, DireccionMitsubishi, parsear_mitsubishi
from src.core.scangroups import GrupoLectura, ItemLectura
from src.plc.base import ErrorPlc, PlcDriver

# Largo del encabezado de respuesta 3E, antes del endcode.
#   binario: subheader(2) + red(1) + pc(1) + io(2) + estacion(1) + longitud(2) = 9
#   ascii:   subheader(4) + red(2) + pc(2) + io(4) + estacion(2) + longitud(4) = 18
_HEADER_BIN = 9
_HEADER_ASCII = 18


def decodificar_palabras(crudo: list[int], off: int, tipo: str) -> float:
    """Decodifica un tag desde una lista de palabras de 16 bits con signo.

    Es el formato que devuelve pymcprotocol tanto en binario como en ASCII. Lo
    usa tambien el driver mock, que simula la misma memoria.
    """
    if tipo == "bit":
        return float(crudo[off] & 1)
    if tipo == "int16":
        return float(crudo[off])
    if tipo == "uint16":
        return float(crudo[off] & 0xFFFF)
    # El tipo se valida antes de tocar crudo[off + 1]: si no, un tipo escrito mal
    # en tags.toml estallaria con un IndexError que no dice nada.
    fmt = {"int32": "<i", "uint32": "<I", "float32": "<f"}.get(tipo)
    if fmt is None:
        raise ValueError(f"Tipo no soportado: {tipo!r}")
    # 32 bits: en Mitsubishi la palabra baja va primero (D5002 baja, D5003 alta).
    b = struct.pack("<hh", crudo[off], crudo[off + 1])
    return float(struct.unpack(fmt, b)[0])


class _Type3ERobusto(pymcprotocol.Type3E):
    """Type3E con recepcion de frame completa."""

    def _recv(self) -> bytes:
        ascii_ = self.commtype == const.COMMTYPE_ASCII
        largo_header = _HEADER_ASCII if ascii_ else _HEADER_BIN
        header = self._recv_exacto(largo_header)
        if ascii_:
            # Los ultimos 4 caracteres del header son la longitud, en hex ASCII.
            try:
                faltan = int(header[14:18].decode("ascii"), 16)
            except ValueError:
                raise ErrorPlc(f"Header ASCII ilegible del PLC: {header!r}") from None
        else:
            faltan = int.from_bytes(header[7:9], "little")
        return header + self._recv_exacto(faltan)

    def _recv_exacto(self, n: int) -> bytes:
        """Lee exactamente n bytes o falla. recv() puede devolver de a pedazos."""
        trozos = bytearray()
        while len(trozos) < n:
            try:
                trozo = self._sock.recv(n - len(trozos))
            except socket.timeout:
                raise ErrorPlc(
                    f"Timeout esperando respuesta del PLC "
                    f"(recibidos {len(trozos)} de {n} bytes)"
                ) from None
            if not trozo:
                raise ErrorPlc("El PLC cerro la conexion mientras se leia la respuesta")
            trozos += trozo
        return bytes(trozos)


class MitsubishiPlc(PlcDriver):
    marca = "mitsubishi"

    def __init__(self, nombre: str, cfg: dict):
        super().__init__(nombre, cfg)
        self._plc: _Type3ERobusto | None = None

    # --- ciclo de vida ---------------------------------------------------
    def conectar(self) -> None:
        ip = self.cfg["ip"]
        puerto = int(self.cfg["puerto"])
        commtype = self.cfg.get("commtype", "binary")
        timeout = float(self.cfg.get("timeout_s", 5.0))
        self.desconectar()
        try:
            plc = _Type3ERobusto(plctype=self.cfg.get("plctype", "Q"))
            # setaccessopt es la unica via soportada: ademas del commtype ajusta
            # _wordsize, el timer del MC y los numeros de red/estacion.
            plc.setaccessopt(
                commtype=commtype,
                network=int(self.cfg.get("network", 0)),
                pc=int(self.cfg.get("pc", 0xFF)),
                # timer_sec TIENE que ser int: adentro hace 4 * timer_sec y
                # despues .to_bytes() sobre el resultado. Con un float explota
                # en un except pelado que reporta "timer_sec must be 0 <= ...
                # <= 16383", un error de rango que no tiene nada que ver.
                timer_sec=max(1, int(timeout)),
            )
            # soc_timeout se lee dentro de connect() al crear el socket, asi que
            # tiene que quedar seteado antes.
            plc.soc_timeout = timeout
            plc.connect(ip, puerto)
            self._plc = plc
            self._conectado = True
        except Exception as e:
            self._plc = None
            self._conectado = False
            raise ErrorPlc(
                f"No se pudo conectar a {ip}:{puerto} [{commtype}] -- "
                f"{type(e).__name__}: {e}. Verifica: "
                "1) que la PC tenga una placa en la misma subred que el PLC "
                "(el PLC no tiene default router, no se lo puede rutear); "
                "2) que el puerto coincida con el Open Setting -- GX Works lo "
                "muestra en HEX, un 2000 en la tabla es 8192 decimal; "
                "3) que el Communication data code del PLC (ASCII/binario) "
                "coincida con commtype; "
                "4) que ningun otro cliente tenga tomada la unica conexion MC."
            ) from e

    def desconectar(self) -> None:
        if self._plc is not None:
            try:
                self._plc.close()
            except Exception:
                pass
            # Se descarta el objeto: conectar() arma uno limpio. Reusarlo
            # despues de un error deja el socket en estado inconsistente.
            self._plc = None
        self._conectado = False

    # --- lectura ---------------------------------------------------------
    def _cabeza(self, grupo: GrupoLectura) -> str:
        base, es_bit = FAMILIAS_MITSUBISHI[grupo.clave.area]
        return DireccionMitsubishi(grupo.clave.area, grupo.inicio, base, es_bit).render()

    def leer_grupo(self, grupo: GrupoLectura) -> list[int]:
        if self._plc is None:
            raise ErrorPlc(f"PLC {self.nombre} no conectado")
        cabeza = self._cabeza(grupo)
        try:
            if grupo.clave.es_bit:
                datos = self._plc.batchread_bitunits(
                    headdevice=cabeza, readsize=grupo.longitud
                )
            else:
                datos = self._plc.batchread_wordunits(
                    headdevice=cabeza, readsize=grupo.longitud
                )
        except ErrorPlc:
            raise
        except Exception as e:
            raise ErrorPlc(
                f"Error leyendo {cabeza} x{grupo.longitud}: {type(e).__name__}: {e}"
            ) from e
        if len(datos) < grupo.longitud:
            raise ErrorPlc(
                f"Respuesta corta leyendo {cabeza}: se esperaban {grupo.longitud} "
                f"valores y llegaron {len(datos)}"
            )
        return datos

    def decodificar(self, grupo: GrupoLectura, crudo: list[int], item: ItemLectura) -> float:
        return decodificar_palabras(crudo, grupo.offset_de(item), item.tag.tipo)

    # --- escritura -------------------------------------------------------
    def escribir_bit(self, direccion: str, valor: bool) -> None:
        if self._plc is None:
            raise ErrorPlc(f"PLC {self.nombre} no conectado")
        d = parsear_mitsubishi(direccion)
        try:
            self._plc.batchwrite_bitunits(headdevice=d.render(), values=[1 if valor else 0])
        except Exception as e:
            # A diferencia de visionMantev2, un fallo de escritura tambien
            # invalida la conexion: si no, un socket muerto queda 'conectado'
            # hasta que falle la proxima lectura.
            self._conectado = False
            raise ErrorPlc(f"Error escribiendo {direccion}: {type(e).__name__}: {e}") from e

    def escribir_palabra(self, direccion: str, valor: int) -> None:
        if self._plc is None:
            raise ErrorPlc(f"PLC {self.nombre} no conectado")
        d = parsear_mitsubishi(direccion)
        try:
            self._plc.batchwrite_wordunits(headdevice=d.render(), values=[int(valor)])
        except Exception as e:
            self._conectado = False
            raise ErrorPlc(f"Error escribiendo {direccion}: {type(e).__name__}: {e}") from e
