"""Tests de la agrupacion de lecturas y de la decodificacion de tipos."""
from __future__ import annotations

import pytest

from src.core.models import TagDef
from src.core.scangroups import agrupar, construir_items
from src.plc.mitsubishi import decodificar_palabras

MITSU = {"q": "mitsubishi"}


def tag(nombre, direccion, tipo="int16", scan_ms=1000):
    return TagDef(nombre=nombre, plc="q", direccion=direccion, tipo=tipo, scan_ms=scan_ms)


def armar(tags, max_longitud=480, max_hueco=16):
    return agrupar(construir_items(tags, MITSU), max_longitud, max_hueco)


class TestAgrupacion:
    def test_contiguos_van_en_una_lectura(self):
        g = armar([tag("a", "D100"), tag("b", "D101"), tag("c", "D102")])
        assert len(g) == 1
        assert (g[0].inicio, g[0].longitud) == (100, 3)

    def test_hueco_chico_se_tolera(self):
        g = armar([tag("a", "D100"), tag("b", "D110")], max_hueco=16)
        assert len(g) == 1
        assert g[0].longitud == 11        # 100..110

    def test_hueco_grande_corta_el_bloque(self):
        g = armar([tag("a", "D100"), tag("b", "D200")], max_hueco=16)
        assert len(g) == 2
        assert [x.inicio for x in g] == [100, 200]

    def test_tope_de_longitud_corta_el_bloque(self):
        g = armar([tag("a", "D0"), tag("b", "D50")], max_longitud=10, max_hueco=100)
        assert len(g) == 2

    def test_bits_y_palabras_no_se_mezclan(self):
        g = armar([tag("w", "D100"), tag("b", "M100", "bit")])
        assert len(g) == 2
        assert {x.clave.es_bit for x in g} == {True, False}

    def test_familias_distintas_no_se_mezclan(self):
        g = armar([tag("a", "D100"), tag("b", "R100")])
        assert len(g) == 2

    def test_scan_distinto_no_se_mezcla(self):
        # Agruparlos obligaria a leer el lento al ritmo del rapido.
        g = armar([tag("a", "D100", scan_ms=500), tag("b", "D101", scan_ms=5000)])
        assert len(g) == 2

    def test_int32_ocupa_dos_palabras(self):
        g = armar([tag("a", "D100", "int32")])
        assert g[0].longitud == 2

    def test_int32_se_solapa_con_el_siguiente(self):
        # D100 int32 ocupa D100 y D101; con D101 aparte el bloque sigue siendo 2.
        g = armar([tag("a", "D100", "int32"), tag("b", "D101")])
        assert len(g) == 1 and g[0].longitud == 2

    def test_offset_dentro_del_grupo(self):
        g = armar([tag("a", "D100"), tag("b", "D103")])
        por_nombre = {i.tag.nombre: g[0].offset_de(i) for i in g[0].items}
        assert por_nombre == {"a": 0, "b": 3}

    def test_tag_mas_grande_que_el_tope(self):
        with pytest.raises(ValueError, match="tope"):
            armar([tag("a", "D100", "int32")], max_longitud=1)

    def test_plc_inexistente(self):
        with pytest.raises(ValueError, match="no esta en site.toml"):
            construir_items([TagDef("x", "otro", "D1")], MITSU)

    def test_tipo_bit_con_direccion_de_palabra(self):
        with pytest.raises(ValueError, match="palabra"):
            construir_items([tag("x", "D100", "bit")], MITSU)

    def test_tipo_palabra_con_direccion_de_bit(self):
        with pytest.raises(ValueError, match="bit"):
            construir_items([tag("x", "M100", "int16")], MITSU)


class TestDecodificacion:
    """Mitsubishi entrega palabras de 16 bits con signo, la baja primero."""

    def test_int16(self):
        assert decodificar_palabras([1234], 0, "int16") == 1234
        assert decodificar_palabras([-1], 0, "int16") == -1

    def test_uint16(self):
        assert decodificar_palabras([-1], 0, "uint16") == 65535

    def test_bit(self):
        assert decodificar_palabras([1], 0, "bit") == 1.0
        assert decodificar_palabras([0], 0, "bit") == 0.0

    def test_int32_palabra_baja_primero(self):
        # 0x00010000 = 65536 -> baja 0x0000, alta 0x0001
        assert decodificar_palabras([0, 1], 0, "int32") == 65536

    def test_int32_negativo(self):
        assert decodificar_palabras([-1, -1], 0, "int32") == -1

    def test_uint32(self):
        assert decodificar_palabras([-1, -1], 0, "uint32") == 4294967295

    def test_float32(self):
        # 1.0 en IEEE 754 es 0x3F800000 -> baja 0x0000, alta 0x3F80
        assert decodificar_palabras([0, 0x3F80], 0, "float32") == pytest.approx(1.0)

    def test_respeta_el_offset(self):
        assert decodificar_palabras([11, 22, 33], 2, "int16") == 33

    def test_tipo_desconocido(self):
        with pytest.raises(ValueError, match="Tipo no soportado"):
            decodificar_palabras([0], 0, "double")
