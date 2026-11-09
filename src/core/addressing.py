"""Parseo de direcciones de PLC.

Mitsubishi (MC Protocol) y Siemens (S7) tienen sintaxis distintas; cada una
tiene su parser y su dataclass. Lo que comparten es que el resultado sabe si la
direccion es de bit o de palabra, y en que numero arranca, que es lo que
core/scangroups.py necesita para agrupar lecturas contiguas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- Mitsubishi

# familia -> (base de numeracion, es_bit)
# La base importa: 'W1A0' es hexadecimal, 'D5002' es decimal. Equivocarla
# devuelve datos de otra direccion sin que nada falle.
FAMILIAS_MITSUBISHI: dict[str, tuple[int, bool]] = {
    # bits
    "X": (16, True), "Y": (16, True), "M": (10, True), "L": (10, True),
    "F": (10, True), "V": (10, True), "B": (16, True), "S": (10, True),
    "SM": (10, True), "SB": (16, True), "TS": (10, True), "TC": (10, True),
    "CS": (10, True), "CC": (10, True), "SS": (10, True), "SC": (10, True),
    "DX": (16, True), "DY": (16, True),
    # palabras
    "D": (10, False), "W": (16, False), "R": (10, False), "ZR": (16, False),
    "SD": (10, False), "SW": (16, False), "TN": (10, False), "CN": (10, False),
    "SN": (10, False),
}

# Familias de 2 letras primero, para que 'SD100' no matchee como 'S' + 'D100'.
_RE_MITSU = re.compile(
    r"^(" + "|".join(sorted(FAMILIAS_MITSUBISHI, key=len, reverse=True)) + r")([0-9A-F]+)$"
)


@dataclass(frozen=True)
class DireccionMitsubishi:
    familia: str
    numero: int
    base: int
    es_bit: bool

    def render(self, numero: int | None = None) -> str:
        r"""Devuelve la direccion como string seguro para pymcprotocol.

        pymcprotocol parte el string con re.search(r"\D+") para la familia y
        re.search(r"\d.*") para el numero. Con una direccion hexadecimal que
        empieza con letra ('WA0') la primera regex se come la 'A' y la segunda
        devuelve '0': lee la direccion equivocada en silencio. Por eso las
        familias hex se renderizan con un cero adelante cuando hace falta.
        """
        n = self.numero if numero is None else numero
        if self.base == 16:
            s = format(n, "X")
            if not s[0].isdigit():
                s = "0" + s
        else:
            s = str(n)
        return f"{self.familia}{s}"

    def desplazada(self, delta: int) -> "DireccionMitsubishi":
        return DireccionMitsubishi(self.familia, self.numero + delta, self.base, self.es_bit)


def parsear_mitsubishi(direccion: str) -> DireccionMitsubishi:
    texto = direccion.strip().upper().replace(" ", "")
    m = _RE_MITSU.match(texto)
    if not m:
        raise ValueError(
            f"Direccion Mitsubishi invalida: {direccion!r}. "
            f"Familias validas: {', '.join(sorted(FAMILIAS_MITSUBISHI))}"
        )
    familia, crudo = m.group(1), m.group(2)
    base, es_bit = FAMILIAS_MITSUBISHI[familia]
    try:
        numero = int(crudo, base)
    except ValueError:
        raise ValueError(
            f"Direccion Mitsubishi invalida: {direccion!r}. La familia {familia} "
            f"usa numeracion {'hexadecimal' if base == 16 else 'decimal'} y "
            f"{crudo!r} no lo es."
        ) from None
    return DireccionMitsubishi(familia, numero, base, es_bit)


# ------------------------------------------------------------------- Siemens

# area -> (codigo snap7, admite DB)
AREAS_SIEMENS = {"DB": "DB", "M": "MK", "I": "PE", "E": "PE", "Q": "PA", "A": "PA"}

# DB1.DBX0.0 / DB1.DBW0 / DB1.DBD0 / DB1.DBB0
_RE_S7_DB = re.compile(r"^DB(\d+)\.DB([XWDB])(\d+)(?:\.(\d+))?$")
# MW100 / MD100 / MB100 / M100.0 / IW0 / I0.0 / QW0 / Q0.0
_RE_S7_AREA = re.compile(r"^([MIEQA])([XWDB]?)(\d+)(?:\.(\d+))?$")

_ANCHO = {"X": 1, "B": 1, "W": 2, "D": 4}


@dataclass(frozen=True)
class DireccionSiemens:
    area: str          # codigo snap7: DB, MK, PE, PA
    db: int            # 0 cuando el area no es DB
    byte: int
    bit: int | None    # None cuando es palabra/doble palabra/byte
    ancho: int         # bytes a leer: 1, 2 o 4

    @property
    def es_bit(self) -> bool:
        return self.bit is not None


def parsear_siemens(direccion: str) -> DireccionSiemens:
    texto = direccion.strip().upper().replace(" ", "")

    m = _RE_S7_DB.match(texto)
    if m:
        db, letra, byte, bit = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
        if letra == "X":
            if bit is None:
                raise ValueError(f"{direccion!r}: DBX requiere el bit (ej: DB1.DBX0.0)")
            if not 0 <= int(bit) <= 7:
                raise ValueError(f"{direccion!r}: el bit debe estar entre 0 y 7")
            return DireccionSiemens("DB", db, byte, int(bit), 1)
        if bit is not None:
            raise ValueError(f"{direccion!r}: solo DBX lleva numero de bit")
        return DireccionSiemens("DB", db, byte, None, _ANCHO[letra])

    m = _RE_S7_AREA.match(texto)
    if m:
        letra_area, letra_tipo, byte, bit = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        area = AREAS_SIEMENS[letra_area]
        if bit is not None:          # M100.0 / I0.0 / Q0.0
            if letra_tipo not in ("", "X"):
                raise ValueError(f"{direccion!r}: no se puede pedir un bit de {letra_tipo}")
            if not 0 <= int(bit) <= 7:
                raise ValueError(f"{direccion!r}: el bit debe estar entre 0 y 7")
            return DireccionSiemens(area, 0, byte, int(bit), 1)
        if letra_tipo in ("", "X"):
            raise ValueError(
                f"{direccion!r}: falta el bit o el tipo (ej: M100.0, MW100, MD100)"
            )
        return DireccionSiemens(area, 0, byte, None, _ANCHO[letra_tipo])

    raise ValueError(
        f"Direccion Siemens invalida: {direccion!r}. "
        "Formatos: DB1.DBX0.0, DB1.DBW0, DB1.DBD0, MW100, M100.0, IW0, I0.0, QW0, Q0.0"
    )


def parsear(marca: str, direccion: str):
    """Despacha al parser segun la marca del PLC."""
    marca = marca.lower()
    if marca in ("mitsubishi", "mock"):
        return parsear_mitsubishi(direccion)
    if marca == "siemens":
        return parsear_siemens(direccion)
    raise ValueError(f"Marca de PLC desconocida: {marca!r}")
