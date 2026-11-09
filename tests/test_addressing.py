"""Tests del parseo de direcciones.

Es logica pura, se testea sin PLC. Y es donde un error no se nota: una base
equivocada lee otra direccion y devuelve un numero perfectamente plausible.
"""
from __future__ import annotations

import pytest

from src.core.addressing import parsear, parsear_mitsubishi, parsear_siemens


class TestMitsubishi:
    @pytest.mark.parametrize("texto, familia, numero, es_bit", [
        ("D5002", "D", 5002, False),
        ("M1000", "M", 1000, True),
        ("d5002", "D", 5002, False),      # se normaliza a mayusculas
        (" M1000 ", "M", 1000, True),
        ("R100", "R", 100, False),
        ("SD200", "SD", 200, False),      # familia de 2 letras, no 'S' + 'D200'
        ("SM400", "SM", 400, True),
        ("TN10", "TN", 10, False),
    ])
    def test_decimales(self, texto, familia, numero, es_bit):
        d = parsear_mitsubishi(texto)
        assert (d.familia, d.numero, d.es_bit) == (familia, numero, es_bit)
        assert d.base == 10

    @pytest.mark.parametrize("texto, numero", [
        ("W1A0", 0x1A0), ("WA0", 0xA0), ("X1F", 0x1F), ("Y20", 0x20), ("B100", 0x100),
    ])
    def test_hexadecimales(self, texto, numero):
        d = parsear_mitsubishi(texto)
        assert d.numero == numero
        assert d.base == 16

    def test_render_decimal_ida_y_vuelta(self):
        assert parsear_mitsubishi("D5002").render() == "D5002"

    def test_render_hex_antepone_cero_si_arranca_con_letra(self):
        # pymcprotocol parte el string con re.search(r"\D+"): si el numero
        # empieza con letra se come un digito y lee otra direccion en silencio.
        assert parsear_mitsubishi("WA0").render() == "W0A0"
        assert parsear_mitsubishi("WFFFF").render() == "W0FFFF"

    def test_render_hex_no_toca_lo_que_ya_arranca_con_digito(self):
        assert parsear_mitsubishi("W1A0").render() == "W1A0"

    def test_render_conserva_el_valor(self):
        for texto in ("WA0", "W1A0", "WFFFF", "B100", "D5002", "M1000"):
            d = parsear_mitsubishi(texto)
            assert parsear_mitsubishi(d.render()).numero == d.numero

    def test_desplazada(self):
        d = parsear_mitsubishi("D5002").desplazada(3)
        assert d.numero == 5005 and d.render() == "D5005"

    @pytest.mark.parametrize("texto", ["", "5002", "Z100", "D", "D-1", "DFFF"])
    def test_invalidas(self, texto):
        # DFFF entra aparte: D es decimal, asi que 'FFF' no es un numero valido.
        with pytest.raises(ValueError):
            parsear_mitsubishi(texto)


class TestSiemens:
    @pytest.mark.parametrize("texto, area, db, byte, bit, ancho", [
        ("DB1.DBX0.0", "DB", 1, 0, 0, 1),
        ("DB8.DBX5.7", "DB", 8, 5, 7, 1),
        ("DB1.DBW10", "DB", 1, 10, None, 2),
        ("DB1.DBD4", "DB", 1, 4, None, 4),
        ("DB1.DBB2", "DB", 1, 2, None, 1),
        ("MW100", "MK", 0, 100, None, 2),
        ("MD100", "MK", 0, 100, None, 4),
        ("M100.3", "MK", 0, 100, 3, 1),
        ("I0.0", "PE", 0, 0, 0, 1),
        ("IW4", "PE", 0, 4, None, 2),
        ("Q0.1", "PA", 0, 0, 1, 1),
        ("QW2", "PA", 0, 2, None, 2),
        ("E0.0", "PE", 0, 0, 0, 1),        # nomenclatura alemana
        ("A0.0", "PA", 0, 0, 0, 1),
    ])
    def test_validas(self, texto, area, db, byte, bit, ancho):
        d = parsear_siemens(texto)
        assert (d.area, d.db, d.byte, d.bit, d.ancho) == (area, db, byte, bit, ancho)

    def test_es_bit(self):
        assert parsear_siemens("DB1.DBX0.0").es_bit
        assert not parsear_siemens("DB1.DBW0").es_bit

    @pytest.mark.parametrize("texto", [
        "DB1.DBX0.8",     # bit fuera de rango
        "DB1.DBX0",       # DBX sin bit
        "DB1.DBW0.1",     # solo DBX lleva bit
        "M100",           # falta bit o tipo
        "DB1",
        "",
        "XW0",
    ])
    def test_invalidas(self, texto):
        with pytest.raises(ValueError):
            parsear_siemens(texto)


class TestDespacho:
    def test_por_marca(self):
        assert parsear("mitsubishi", "D5002").familia == "D"
        assert parsear("mock", "M1000").familia == "M"
        assert parsear("siemens", "DB1.DBW0").area == "DB"

    def test_marca_desconocida(self):
        with pytest.raises(ValueError):
            parsear("allen-bradley", "N7:0")
