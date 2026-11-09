"""Agrupacion de tags en lecturas batch.

Leer tag por tag cuesta un round-trip TCP cada uno. Con dos tags da igual, pero
la lista real va a tener decenas o cientos y a 1 segundo de scan eso no cierra.
Este modulo junta los tags contiguos de la misma familia en una sola lectura
(batchread_wordunits / batchread_bitunits en Mitsubishi, read_area en Siemens) y
despues cada tag saca su dato por offset dentro del bloque leido.

El criterio es el clasico de SCADA: se toleran huecos chicos (leer 3 registros
de mas es mas barato que un round-trip extra) pero no huecos grandes, y el
bloque tiene un tope de tamano.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.core.addressing import DireccionMitsubishi, DireccionSiemens, parsear
from src.core.models import TagDef


@dataclass(frozen=True)
class ClaveGrupo:
    """Lo que tiene que coincidir para que dos tags entren en la misma lectura."""
    plc: str
    area: str          # familia Mitsubishi ('D') o area snap7 ('DB','MK',...)
    db: int            # numero de DB en Siemens; 0 en Mitsubishi
    es_bit: bool
    scan_ms: int       # tags con distinto periodo no comparten lectura


@dataclass(frozen=True)
class ItemLectura:
    tag: TagDef
    clave: ClaveGrupo
    inicio: int        # nro de dispositivo (Mitsubishi) o byte (Siemens)
    longitud: int      # palabras (Mitsubishi) o bytes (Siemens)
    bit: int | None = None   # bit dentro del byte, solo Siemens


@dataclass
class GrupoLectura:
    """Un bloque contiguo que se lee de una sola vez."""
    clave: ClaveGrupo
    inicio: int
    longitud: int
    items: list[ItemLectura] = field(default_factory=list)

    @property
    def fin(self) -> int:
        return self.inicio + self.longitud

    def offset_de(self, item: ItemLectura) -> int:
        """Posicion del item dentro del bloque leido."""
        return item.inicio - self.inicio


def construir_items(tags: list[TagDef], marca_por_plc: dict[str, str]) -> list[ItemLectura]:
    """Traduce cada TagDef a coordenadas de lectura segun la marca de su PLC."""
    items: list[ItemLectura] = []
    for tag in tags:
        marca = marca_por_plc.get(tag.plc)
        if marca is None:
            raise ValueError(f"El tag {tag.nombre!r} apunta al PLC {tag.plc!r}, que no esta en site.toml")
        dir_ = parsear(marca, tag.direccion)

        if isinstance(dir_, DireccionMitsubishi):
            if tag.es_bit and not dir_.es_bit:
                raise ValueError(f"{tag.nombre}: {tag.direccion} es de palabra pero el tipo es 'bit'")
            if not tag.es_bit and dir_.es_bit:
                raise ValueError(f"{tag.nombre}: {tag.direccion} es de bit pero el tipo es {tag.tipo!r}")
            clave = ClaveGrupo(tag.plc, dir_.familia, 0, dir_.es_bit, tag.scan_ms)
            longitud = 1 if dir_.es_bit else tag.palabras
            items.append(ItemLectura(tag, clave, dir_.numero, longitud))

        elif isinstance(dir_, DireccionSiemens):
            if tag.es_bit != dir_.es_bit:
                raise ValueError(
                    f"{tag.nombre}: {tag.direccion} y el tipo {tag.tipo!r} no concuerdan "
                    "(usa DBX/M0.0 para 'bit', DBW/DBD/MW/MD para palabras)"
                )
            # En Siemens todo se lee en bytes, incluso los bits.
            longitud = dir_.ancho if dir_.es_bit else max(dir_.ancho, tag.palabras * 2)
            clave = ClaveGrupo(tag.plc, dir_.area, dir_.db, False, tag.scan_ms)
            items.append(ItemLectura(tag, clave, dir_.byte, longitud, dir_.bit))
        else:
            raise TypeError(f"Direccion no reconocida para {tag.nombre}")
    return items


def agrupar(items: list[ItemLectura], max_longitud: int, max_hueco: int) -> list[GrupoLectura]:
    """Junta items contiguos de la misma clave en grupos de lectura.

    max_longitud: tope de palabras/bits/bytes por lectura.
    max_hueco:    cuantas unidades sin usar se toleran entre dos tags antes de
                  cortar el bloque y hacer una lectura aparte.
    """
    grupos: list[GrupoLectura] = []
    por_clave: dict[ClaveGrupo, list[ItemLectura]] = {}
    for item in items:
        por_clave.setdefault(item.clave, []).append(item)

    for clave, lista in por_clave.items():
        lista.sort(key=lambda i: (i.inicio, i.longitud))
        actual: GrupoLectura | None = None
        for item in lista:
            fin_item = item.inicio + item.longitud
            if actual is not None:
                hueco = item.inicio - actual.fin
                nueva_long = max(actual.fin, fin_item) - actual.inicio
                if hueco <= max_hueco and nueva_long <= max_longitud:
                    actual.longitud = nueva_long
                    actual.items.append(item)
                    continue
            if item.longitud > max_longitud:
                raise ValueError(
                    f"El tag {item.tag.nombre!r} necesita {item.longitud} unidades, "
                    f"mas que el tope de {max_longitud} por lectura"
                )
            actual = GrupoLectura(clave, item.inicio, item.longitud, [item])
            grupos.append(actual)

    grupos.sort(key=lambda g: (g.clave.plc, g.clave.scan_ms, g.clave.area, g.inicio))
    return grupos
